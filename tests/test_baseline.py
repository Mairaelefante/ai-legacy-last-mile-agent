import json
from pathlib import Path
from typing import Any

import pytest

from ai_legacy_last_mile.baseline import run_baseline
from ai_legacy_last_mile.datasets import load_documents, load_schemas
from ai_legacy_last_mile.llm import LLMCompletion
from ai_legacy_last_mile.models import MappingResponse, MappingResult
from ai_legacy_last_mile.run_baseline import execute


class FakeLLMClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str, response_model: type[Any]) -> LLMCompletion:
        self.prompts.append(prompt)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        raw_text = response.model_dump_json() if hasattr(response, "model_dump_json") else str(response)
        return LLMCompletion(parsed=response, raw_text=raw_text)


def valid_response() -> MappingResponse:
    document = load_documents()[0]
    schema = load_schemas()[0]
    return MappingResponse(
        mappings=[
            MappingResult(
                source_fact_id=fact.id,
                target_field_path=field.path,
                value=fact.value,
            )
            for fact, field in zip(document.facts, schema.fields, strict=True)
        ]
    )


def test_baseline_makes_exactly_one_isolated_request_per_pair() -> None:
    document = load_documents()[0]
    schema = load_schemas()[0]
    client = FakeLLMClient([valid_response()])

    result = run_baseline([document], [schema], client)

    assert len(client.prompts) == 1
    assert document.text in client.prompts[0]
    assert schema.fields[0].path in client.prompts[0]
    assert "ground_truth" not in client.prompts[0]
    assert len(result.predictions[0].mappings) == len(document.facts)
    assert result.failures == []


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (MappingResponse(mappings=[]), "missing mappings"),
        (
            MappingResponse(
                mappings=[
                    MappingResult(
                        source_fact_id=fact.id,
                        target_field_path="not.a.real.path",
                        value=fact.value,
                    )
                    for fact in load_documents()[0].facts
                ]
            ),
            "nonexistent target fields",
        ),
    ],
)
def test_invalid_response_records_empty_failed_case(response: MappingResponse, message: str) -> None:
    result = run_baseline(
        [load_documents()[0]], [load_schemas()[0]], FakeLLMClient([response])
    )

    assert result.predictions[0].mappings == []
    assert message in result.failures[0].message


def test_api_failure_is_recorded_without_retry() -> None:
    client = FakeLLMClient([RuntimeError("service unavailable")])

    result = run_baseline([load_documents()[0]], [load_schemas()[0]], client)

    assert len(client.prompts) == 1
    assert result.failures[0].error_type == "RuntimeError"
    assert result.predictions[0].mappings == []


def test_malformed_structured_response_is_recorded() -> None:
    result = run_baseline(
        [load_documents()[0]], [load_schemas()[0]], FakeLLMClient([{"unexpected": []}])
    )

    assert result.failures[0].error_type == "ValidationError"
    assert result.predictions[0].mappings == []


def test_execute_saves_validated_raw_and_failure_files(tmp_path: Path) -> None:
    output = tmp_path / "results" / "predictions.json"
    failures = execute(
        Path("data/clinical_documents.json"),
        Path("data/target_schemas.json"),
        output,
        FakeLLMClient([RuntimeError("failed")] * 20),
    )

    assert failures == 20
    assert len(json.loads(output.read_text())) == 20
    assert len(json.loads((output.parent / "predictions.raw.json").read_text())) == 20
    assert len(json.loads((output.parent / "predictions.failures.json").read_text())) == 20
