import inspect
import json
from pathlib import Path
from typing import Any

import pytest

import ai_legacy_last_mile.stateful_baseline as stateful_module
from ai_legacy_last_mile.datasets import (
    load_ground_truth_updates,
    load_incoming_events,
    load_patient_records,
    load_schemas,
    load_stateful_schema_extensions,
    load_update_cases,
)
from ai_legacy_last_mile.llm import LLMCompletion
from ai_legacy_last_mile.models import StatefulUpdateResponse
from ai_legacy_last_mile.run_stateful_baseline import execute
from ai_legacy_last_mile.stateful_baseline import run_stateful_baseline


class FakeLLMClient:
    def __init__(self, responses: list[Any] | None = None) -> None:
        self.responses = iter(responses) if responses is not None else None
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_model: type[Any]) -> LLMCompletion:
        self.prompts.append(prompt)
        response = (
            next(self.responses)
            if self.responses is not None
            else StatefulUpdateResponse.from_proposed_updates([])
        )
        if isinstance(response, Exception):
            raise response
        raw_text = response.model_dump_json() if hasattr(response, "model_dump_json") else str(response)
        return LLMCompletion(parsed=response, raw_text=raw_text)


def inputs_for(case_count: int = 1):
    return (
        load_patient_records(),
        load_incoming_events(),
        load_update_cases()[:case_count],
        load_schemas(),
        load_stateful_schema_extensions(),
    )


def updates_for(case_id: str):
    return [update for update in load_ground_truth_updates() if update.case_id == case_id]


def test_exactly_one_request_per_case() -> None:
    client = FakeLLMClient()
    cases = load_update_cases()

    result = run_stateful_baseline(
        load_patient_records(),
        load_incoming_events(),
        cases,
        load_schemas(),
        load_stateful_schema_extensions(),
        client,
    )

    assert len(client.prompts) == len(cases) == 40
    assert len(result.raw_responses) == 40
    assert result.failures == []


def test_prompt_contains_complete_case_inputs_but_no_evaluation_inputs() -> None:
    case = load_update_cases()[0]
    client = FakeLLMClient()

    run_stateful_baseline(*inputs_for(), client)

    prompt = client.prompts[0]
    record = next(record for record in load_patient_records() if record.patient_id == case.patient_id)
    event = next(event for event in load_incoming_events() if event.event_id == case.event_id)
    schema = next(schema for schema in load_schemas() if schema.id == case.target_schema_id)
    extension = next(
        item for item in load_stateful_schema_extensions() if item.target_schema_id == case.target_schema_id
    )
    assert record.demographics.full_name in prompt
    assert event.summary in prompt
    assert event.source.author in prompt
    assert event.facts[0].id in prompt
    assert str(event.facts[0].value) in prompt
    assert schema.name in prompt
    assert extension.fields[0].path in prompt
    assert "ground_truth" not in prompt
    assert "evaluator" not in prompt.lower()
    assert "metrics" not in prompt.lower()
    source = inspect.getsource(stateful_module)
    assert "load_ground_truth_updates" not in source
    assert "update_evaluator" not in source


def test_multi_action_structured_response_is_preserved() -> None:
    case = next(case for case in load_update_cases() if case.event_id == "event-02")
    expected = updates_for(case.case_id)
    client = FakeLLMClient([StatefulUpdateResponse.from_proposed_updates(expected)])

    result = run_stateful_baseline(
        load_patient_records(),
        load_incoming_events(),
        [case],
        load_schemas(),
        load_stateful_schema_extensions(),
        client,
    )

    assert result.predictions == expected
    assert len(result.predictions) == 3
    assert result.failures == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"target_path": "not.in.destination"}, "target paths"),
        ({"source_fact_ids": ["unknown-fact"]}, "source fact IDs"),
        ({"case_id": "wrong-case"}, "identity"),
    ],
)
def test_invalid_model_update_is_rejected(change, message) -> None:
    case = load_update_cases()[0]
    invalid = updates_for(case.case_id)[0].model_copy(update=change)
    client = FakeLLMClient([StatefulUpdateResponse.from_proposed_updates([invalid])])

    result = run_stateful_baseline(*inputs_for(), client)

    assert result.predictions == []
    assert len(client.prompts) == 1
    assert message in result.failures[0].message


def test_malformed_response_becomes_recorded_failure() -> None:
    client = FakeLLMClient([{"unexpected": []}])

    result = run_stateful_baseline(*inputs_for(), client)

    assert result.predictions == []
    assert result.failures[0].error_type == "ValidationError"


def test_duplicate_update_objects_are_rejected() -> None:
    case = load_update_cases()[0]
    update = updates_for(case.case_id)[0]
    client = FakeLLMClient(
        [StatefulUpdateResponse.from_proposed_updates([update, update])]
    )

    result = run_stateful_baseline(*inputs_for(), client)

    assert result.predictions == []
    assert "duplicate update objects" in result.failures[0].message


def test_api_failure_is_recorded_without_retry() -> None:
    client = FakeLLMClient([RuntimeError("service unavailable")])

    result = run_stateful_baseline(*inputs_for(), client)

    assert len(client.prompts) == 1
    assert result.failures[0].error_type == "RuntimeError"
    assert result.raw_responses[0].error == "service unavailable"


def test_output_artifacts_are_written_with_required_names(tmp_path: Path) -> None:
    output = tmp_path / "results" / "stateful_baseline_predictions.json"
    client = FakeLLMClient()

    failures = execute(
        Path("data/patient_records.json"),
        Path("data/incoming_events.json"),
        Path("data/stateful_cases.json"),
        Path("data/target_schemas.json"),
        Path("data/stateful_schema_extensions.json"),
        output,
        client,
    )

    assert failures == 0
    assert json.loads(output.read_text()) == []
    raw = output.parent / "stateful_baseline_raw.json"
    failure_path = output.parent / "stateful_baseline_failures.json"
    assert len(json.loads(raw.read_text())) == 40
    assert json.loads(failure_path.read_text()) == []
