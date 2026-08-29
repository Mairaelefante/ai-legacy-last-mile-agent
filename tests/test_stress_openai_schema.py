import json
from typing import Any

from ai_legacy_last_mile.llm import LLMCompletion
from ai_legacy_last_mile.stress_baseline import (
    StressResponse,
    StressUpdate,
    run,
)


def _assert_no_typeless_properties(schema: dict[str, Any]) -> None:
    """Reproduce the API rule that rejected the original ``Any`` property."""

    for name, property_schema in schema.get("properties", {}).items():
        assert property_schema, f"property {name!r} has an empty schema"
        assert any(
            keyword in property_schema
            for keyword in ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")
        ), f"property {name!r} has no explicit JSON Schema type or composition"
    for definition in schema.get("$defs", {}).values():
        _assert_no_typeless_properties(definition)


def _update(value: Any, *, case_id: str = "case-1", source_ids: list[str] | None = None) -> StressUpdate:
    return StressUpdate(
        case_id=case_id,
        action_type="ADD",
        target_path="encounters[].results[]",
        record_id="record-1",
        encounter_id="encounter-1",
        value=value,
        timestamp="2026-01-01T00:00:00Z",
        provenance={"institution": "Synthetic A", "sequence": 1},
        source_fact_ids=source_ids or ["fact-1"],
        reconciliation_kind="new_observation",
        temporal_classification="distinct_time",
    )


def test_stress_response_schema_has_no_prior_typeless_value_failure() -> None:
    schema = StressResponse.model_json_schema()
    update_schema = schema["$defs"]["StressOutputUpdate"]
    assert update_schema["properties"]["value"]["type"] == "string"
    assert update_schema["properties"]["provenance"]["type"] == "string"
    assert "value" in update_schema["required"]
    assert "provenance" in update_schema["required"]
    assert update_schema["additionalProperties"] is False
    assert schema["additionalProperties"] is False
    _assert_no_typeless_properties(schema)


def test_flexible_values_round_trip_losslessly() -> None:
    values = [None, "text", 7, 3.25, True, {"nested": [1, None, False]}, ["a", 2, {}]]
    expected = [_update(value, case_id=f"case-{index}") for index, value in enumerate(values)]
    assert StressResponse.from_stress_updates(expected).to_stress_updates() == expected


def test_multi_action_wire_round_trip_preserves_identity_fields() -> None:
    expected = [
        _update({"value": "first"}, source_ids=["fact-a"]),
        _update(["second"], source_ids=["fact-b", "fact-c"]),
    ]
    decoded = StressResponse.from_stress_updates(expected).to_stress_updates()
    assert decoded == expected
    assert [(row.case_id, row.action_type, row.target_path, row.source_fact_ids) for row in decoded] == [
        (row.case_id, row.action_type, row.target_path, row.source_fact_ids) for row in expected
    ]


def test_runner_never_reads_ground_truth(monkeypatch) -> None:
    from pathlib import Path

    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        assert path.name != "ground_truth_updates.json"
        return original_read_text(path, *args, **kwargs)

    class EmptyClient:
        def complete(self, prompt: str, response_model: type[StressResponse]) -> LLMCompletion:
            parsed = StressResponse(updates=[])
            return LLMCompletion(parsed=parsed, raw_text=json.dumps({"updates": []}))

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    predictions, raw, failures = run(EmptyClient())
    assert predictions == []
    assert len(raw) == 20
    assert failures == []
