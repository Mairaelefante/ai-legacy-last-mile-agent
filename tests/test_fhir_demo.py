import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import BaseModel

from ai_legacy_last_mile.canonical_update_compiler_exp004 import compile_plan_exp004
from ai_legacy_last_mile.fhir_demo import (
    FhirDemoValidationError,
    ReplayPlanClient,
    apply_approved_proposal,
    canonical_update_to_fhir_proposal,
    event_to_internal_input,
    validate_bundle,
)
from ai_legacy_last_mile.llm import LLMCompletion
from ai_legacy_last_mile.reconciliation_planner_exp004 import plan_case_exp004
from ai_legacy_last_mile.run_fhir_demo import run_demo

DATA = Path("data/fhir_demo")


def load(name: str):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_fhir_tool_validates_and_adapts_the_supported_subset() -> None:
    bundle = load("patient_bundle.json")
    index = validate_bundle(bundle)
    assert set(resource["resourceType"] for resource in index.values()) == {
        "Patient",
        "Encounter",
        "Observation",
        "DiagnosticReport",
    }
    case, record, event, schema = event_to_internal_input(load("events.json")[0], bundle)
    assert case == {
        "case_id": "patient-demo-001:demo-event-01:fhir_demo",
        "patient_id": "patient-demo-001",
        "event_id": "demo-event-01",
        "target_schema_id": "fhir_demo",
    }
    assert record["active_encounter_id"] == "encounter-demo-001"
    assert event["facts"][0]["test_name"] == "sodium"
    assert schema["fields"] == [
        "encounters[].results[]",
        "encounters[].documents[]",
        "workflow.review",
    ]


@pytest.mark.parametrize("mutation", ["marker", "external", "cross_patient", "unsupported"])
def test_fhir_tool_fails_closed_before_planning(mutation: str) -> None:
    bundle = load("patient_bundle.json")
    event = deepcopy(load("events.json")[0])
    if mutation == "marker":
        event["resource"]["meta"]["tag"] = []
    elif mutation == "external":
        event["resource"]["encounter"]["reference"] = "https://ehr.invalid/Encounter/encounter-demo-001"
    elif mutation == "cross_patient":
        event["resource"]["subject"]["reference"] = "Patient/someone-else"
    else:
        event["resource"]["resourceType"] = "Condition"
    with pytest.raises(FhirDemoValidationError):
        event_to_internal_input(event, bundle)


def test_all_replay_plans_use_actual_exp004_validation_and_compiler() -> None:
    bundle = load("patient_bundle.json")
    plans = {plan["case_id"]: plan for plan in load("replay_plans.json")}
    expected = [
        ("ADD", "new_observation", None),
        ("NO_OP", "equivalent_duplicate", "same_measurement"),
        ("FLAG_CONFLICT", "true_conflict", None),
        ("ADD", "new_observation", "distinct_time"),
    ]
    for event, expected_update in zip(load("events.json"), expected, strict=True):
        case, record, incoming, schema = event_to_internal_input(event, bundle)
        client = ReplayPlanClient(plans[case["case_id"]])
        plan, raw = plan_case_exp004(client, case, record, incoming, schema)
        compiled = compile_plan_exp004(plan, record, incoming, schema)
        update = compiled.updates[0]
        assert (update.action_type, update.reconciliation_kind, update.temporal_classification) == expected_update
        assert client.calls == 1
        assert raw.startswith("offline replay fixture:")
        proposal = canonical_update_to_fhir_proposal(update, event["resource"])
        if update.action_type == "ADD":
            bundle = apply_approved_proposal(
                bundle, proposal, "APPROVED_FOR_SYNTHETIC_SIMULATION"
            )


def test_application_independently_rejects_nonapproved_and_nonwrite_actions() -> None:
    bundle = load("patient_bundle.json")
    no_op = {
        "canonical_action": "NO_OP",
        "fhir_entry": None,
    }
    with pytest.raises(FhirDemoValidationError, match="not approved"):
        apply_approved_proposal(bundle, no_op, "NOT_APPLICABLE")
    with pytest.raises(FhirDemoValidationError, match="only approved ADD"):
        apply_approved_proposal(bundle, no_op, "APPROVED_FOR_SYNTHETIC_SIMULATION")


def test_replay_demo_evolves_only_the_approved_in_memory_state(capsys) -> None:
    result = run_demo("replay")
    output = capsys.readouterr().out
    assert "MODE: OFFLINE RECORDED-PLAN REPLAY" in output
    assert "No model API will be called." in output
    assert output.count("EVENT ") == 4
    assert "written to EHR" not in output
    assert "external writes performed: 0" in output
    assert result["summary"] == {
        "observations_added": 2,
        "duplicates_avoided": 1,
        "conflicts_awaiting_review": 1,
        "external_writes_performed": 0,
        "clinical_recommendations_made": 0,
    }
    index = validate_bundle(result["bundle"])
    observations = [resource for resource in index.values() if resource["resourceType"] == "Observation"]
    assert len(observations) == 4
    assert {resource["id"] for resource in observations} >= {
        "incoming-sodium-001",
        "incoming-potassium-002",
    }
    report = index["DiagnosticReport/report-knee-001"]
    assert report["code"]["text"] == "Right knee report"


def test_live_mode_uses_exactly_one_configured_client_call_per_event(capsys) -> None:
    class SequencedClient:
        def __init__(self, plans):
            self.plans = iter(plans)
            self.calls = 0

        def complete(self, prompt: str, response_model: type[BaseModel]) -> LLMCompletion:
            self.calls += 1
            parsed = response_model.model_validate(next(self.plans))
            return LLMCompletion(parsed=parsed, raw_text="test live completion")

    client = SequencedClient(load("replay_plans.json"))
    result = run_demo("live", live_client=client)
    output = capsys.readouterr().out
    assert client.calls == 4
    assert "MODE: LIVE MODEL INFERENCE" in output
    assert "OFFLINE RECORDED-PLAN REPLAY" not in output
    assert result["summary"]["observations_added"] == 2
