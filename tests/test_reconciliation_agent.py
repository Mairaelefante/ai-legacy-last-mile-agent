import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_legacy_last_mile.canonical_update_compiler import compile_plan
from ai_legacy_last_mile.llm import LLMCompletion
from ai_legacy_last_mile.reconciliation_models import (
    CanonicalAction,
    EntityType,
    IdentityRelationship,
    PlanItem,
    ReconciliationPlan,
    TemporalRelationship,
)
from ai_legacy_last_mile.reconciliation_planner import build_reconciliation_prompt
from ai_legacy_last_mile.run_reconciliation_agent import run_experiment
from ai_legacy_last_mile.stress_evaluator import DATA


def item(
    relationship: IdentityRelationship,
    action: CanonicalAction,
    *,
    entity: EntityType = EntityType.RESULT,
    source_ids: list[str] | None = None,
    record_id: str | None = "old-1",
    encounter_id: str | None = "enc-1",
    temporal: TemporalRelationship = TemporalRelationship.SAME_MEASUREMENT,
) -> PlanItem:
    ids = source_ids or ["f1"]
    return PlanItem(
        source_fact_ids=ids,
        entity_type=entity,
        matched_record_id=record_id,
        matched_encounter_id=encounter_id,
        proposed_record_id=None,
        identity_relationship=relationship,
        temporal_relationship=temporal,
        new_write_needed=action not in {CanonicalAction.NO_OP},
        intended_action=action,
        target_collection="encounters[].results[]",
        provenance_fact_ids=ids,
        reason="fixture evidence",
        evidence=["same identity"],
        human_approval_required=action not in {CanonicalAction.NO_OP, CanonicalAction.LINK},
    )


def compile_one(plan_item: PlanItem, facts: list[dict[str, Any]], *, existing: dict[str, Any] | None = None, fields: list[str] | None = None):
    collection = {EntityType.RESULT: "results", EntityType.REQUEST: "requests", EntityType.DOCUMENT: "documents"}[plan_item.entity_type]
    encounter = {"id": "enc-1", collection: [existing] if existing else []}
    record = {"patient_id": "p1", "active_encounter_id": "enc-1", "encounters": [encounter]}
    event = {"patient_id": "p1", "event_id": "e1", "facts": facts}
    schema = {"id": "ehr", "fields": fields or ["encounters[].results[]", "encounters[].requests[]", "encounters[].documents[]", "workflow.review"]}
    plan = ReconciliationPlan(case_id="c1", items=[plan_item], summary="test")
    return compile_plan(plan, record, event, schema)


def test_planner_schema_is_strict_structured_and_transport_safe() -> None:
    schema = ReconciliationPlan.model_json_schema()
    assert schema["additionalProperties"] is False
    plan_item = schema["$defs"]["PlanItem"]
    assert plan_item["additionalProperties"] is False
    assert set(plan_item["required"]) == set(plan_item["properties"])
    assert plan_item["properties"]["identity_relationship"]["$ref"].endswith("IdentityRelationship")
    assert "Any" not in json.dumps(schema)
    with pytest.raises(ValidationError):
        ReconciliationPlan.model_validate({"case_id": "c", "items": [], "summary": "x", "payload": {}})


def test_semantic_duplicate_is_no_op_without_new_external_identity() -> None:
    result = compile_one(
        item(IdentityRelationship.SEMANTIC_DUPLICATE, CanonicalAction.NO_OP),
        [{"id": "f1", "kind": "result", "test_name": "sodium", "value": "140", "unit": "mmol/L", "timestamp": "t", "institution": "B"}],
        existing={"id": "old-1", "test_name": "sodium", "value": "140", "unit": "mmol/L", "timestamp": "t"},
    )
    assert result.updates[0].action_type == "NO_OP"
    assert result.updates[0].record_id == "old-1"


def test_semantic_duplicate_links_only_a_new_external_identity() -> None:
    plan_item = item(IdentityRelationship.SEMANTIC_DUPLICATE, CanonicalAction.LINK, entity=EntityType.REQUEST)
    result = compile_one(
        plan_item,
        [{"id": "f1", "kind": "request", "description": "CT head", "status": "active", "external_id": "R1", "institution": "B"}],
        existing={"id": "old-1", "description": "CT head", "status": "active"},
    )
    assert result.updates[0].action_type == "LINK"
    assert result.updates[0].value["external_id"] == "R1"


def test_equivalent_unit_duplicate_preserves_canonical_existing_value() -> None:
    result = compile_one(
        item(IdentityRelationship.EQUIVALENT_UNIT_DUPLICATE, CanonicalAction.NO_OP),
        [{"id": "f1", "kind": "result", "test_name": "creatinine", "value": "88.4", "unit": "umol/L", "timestamp": "t", "institution": "C"}],
        existing={"id": "old-1", "test_name": "creatinine", "value": "1.0", "unit": "mg/dL", "timestamp": "t"},
    )
    assert result.updates[0].value == {"test_name": "creatinine", "value": "1.0", "unit": "mg/dL"}
    assert result.updates[0].reconciliation_kind == "equivalent_duplicate"


@pytest.mark.parametrize(
    ("relationship", "planned", "expected"),
    [
        (IdentityRelationship.PARTIAL_DUPLICATE, CanonicalAction.UPDATE, "UPDATE"),
        (IdentityRelationship.TRUE_CONFLICT, CanonicalAction.FLAG_CONFLICT, "FLAG_CONFLICT"),
        (IdentityRelationship.MISSING_CONTEXT, CanonicalAction.FLAG_MISSING_CONTEXT, "FLAG_MISSING_CONTEXT"),
    ],
)
def test_relationship_deterministically_controls_action(relationship, planned, expected) -> None:
    facts = [{"id": "f1", "kind": "result", "test_name": "x", "value": "1", "unit": "u", "timestamp": "t", "institution": "B"}]
    result = compile_one(item(relationship, planned), facts, existing={"id": "old-1", "test_name": "x", "value": "0", "unit": "u"})
    assert result.updates[0].action_type == expected


def test_distinct_later_observation_adds_and_preserves_encounter_and_provenance() -> None:
    plan_item = item(IdentityRelationship.NEW, CanonicalAction.ADD, record_id=None, encounter_id="enc-1", temporal=TemporalRelationship.DISTINCT_LATER)
    plan_item.proposed_record_id = "new-1"
    result = compile_one(plan_item, [{"id": "f1", "kind": "result", "test_name": "K", "value": "4.8", "unit": "mmol/L", "timestamp": "later", "institution": "B", "external_id": "B-k"}])
    update = result.updates[0]
    assert (update.action_type, update.record_id, update.encounter_id) == ("ADD", "new-1", "enc-1")
    assert update.provenance == {"institution": "B", "external_id": "B-k"}
    assert update.temporal_classification == "distinct_time"


def test_ambiguous_encounter_is_not_guessed() -> None:
    plan_item = item(IdentityRelationship.MISSING_CONTEXT, CanonicalAction.FLAG_MISSING_CONTEXT, record_id=None, encounter_id=None, temporal=TemporalRelationship.AMBIGUOUS)
    result = compile_one(plan_item, [{"id": "f1", "kind": "result", "test_name": "hgb", "value": "12", "unit": "g/dL", "timestamp": "2026-01-01T10:00:00Z", "institution": "B"}])
    assert result.updates[0].encounter_id is None
    assert result.updates[0].temporal_classification == "ambiguous"


def test_duplicate_plan_items_do_not_generate_duplicate_updates_or_review_actions() -> None:
    plan_item = item(IdentityRelationship.PARTIAL_DUPLICATE, CanonicalAction.UPDATE, entity=EntityType.REQUEST)
    plan = ReconciliationPlan(case_id="c1", items=[plan_item, plan_item.model_copy(deep=True)], summary="duplicate")
    record = {"active_encounter_id": "enc-1", "encounters": [{"id": "enc-1", "requests": [{"id": "old-1", "description": "MRI", "status": "ordered"}]}]}
    event = {"facts": [{"id": "f1", "kind": "request", "description": "MRI", "status": "scheduled", "institution": "B"}]}
    schema = {"fields": ["encounters[].requests[]", "workflow.review"]}
    result = compile_plan(plan, record, event, schema)
    assert len(result.updates) == 1
    assert result.updates[0].target_path != "workflow.review"
    assert result.execution_policy == {"human_approval_required": True}


def test_multi_fact_and_multi_action_compilation() -> None:
    conflict = item(IdentityRelationship.TRUE_CONFLICT, CanonicalAction.FLAG_CONFLICT, source_ids=["f1", "f2"], record_id=None)
    add = item(IdentityRelationship.NEW, CanonicalAction.ADD, source_ids=["f3"], record_id=None, temporal=TemporalRelationship.DISTINCT_LATER)
    add.proposed_record_id = "new-3"
    plan = ReconciliationPlan(case_id="c1", items=[conflict, add], summary="two independent actions")
    record = {"active_encounter_id": "enc-1", "encounters": [{"id": "enc-1", "results": []}]}
    event = {"facts": [
        {"id": "f1", "kind": "result", "test_name": "K", "value": "3", "unit": "u", "timestamp": "t", "institution": "A"},
        {"id": "f2", "kind": "result", "test_name": "K", "value": "4", "unit": "u", "timestamp": "t", "institution": "B"},
        {"id": "f3", "kind": "result", "test_name": "Na", "value": "140", "unit": "u", "timestamp": "t2", "institution": "B"},
    ]}
    result = compile_plan(plan, record, event, {"fields": ["encounters[].results[]", "workflow.review"]})
    assert [update.action_type for update in result.updates] == ["FLAG_CONFLICT", "ADD"]
    assert result.updates[0].source_fact_ids == ["f1", "f2"]


def test_prompt_and_inference_runner_do_not_read_ground_truth(monkeypatch) -> None:
    cases = json.loads((DATA / "cases.json").read_text())
    records = json.loads((DATA / "patient_records.json").read_text())
    events = json.loads((DATA / "incoming_events.json").read_text())
    schemas = json.loads((DATA / "target_schemas.json").read_text())
    prompt = build_reconciliation_prompt(cases[0], records[0], events[0], schemas[0])
    assert "categories" not in prompt and "ground_truth" not in prompt and "expected_updates" not in prompt

    original = Path.read_text
    def guarded(path: Path, *args: Any, **kwargs: Any) -> str:
        assert path.name != "ground_truth_updates.json"
        return original(path, *args, **kwargs)

    class EmptyClient:
        def complete(self, prompt: str, response_model: type[ReconciliationPlan]) -> LLMCompletion:
            case_id = json.loads(prompt.split("CASE INPUT:\n", 1)[1])["case"]["case_id"]
            parsed = ReconciliationPlan(case_id=case_id, items=[], summary="none")
            return LLMCompletion(parsed=parsed, raw_text=parsed.model_dump_json())

    monkeypatch.setattr(Path, "read_text", guarded)
    predictions, plans, raw, failures = run_experiment(EmptyClient())
    assert predictions == [] and len(plans) == len(raw) == 20 and failures == []
