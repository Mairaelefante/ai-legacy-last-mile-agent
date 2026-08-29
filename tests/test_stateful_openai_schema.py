from typing import Any

from ai_legacy_last_mile.datasets import load_ground_truth_updates
from ai_legacy_last_mile.models import StatefulUpdateResponse


def _assert_no_typeless_properties(schema: dict[str, Any]) -> None:
    """Mirror the endpoint's requirement that every property has an explicit shape."""

    for name, property_schema in schema.get("properties", {}).items():
        assert property_schema, f"property {name!r} has an empty schema"
        assert any(
            keyword in property_schema
            for keyword in ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")
        ), f"property {name!r} has no explicit JSON Schema type or composition"
    for definition in schema.get("$defs", {}).values():
        _assert_no_typeless_properties(definition)


def test_stateful_response_schema_is_openai_strict_compatible() -> None:
    # This is the exact Pydantic model passed as text_format to responses.parse;
    # the OpenAI SDK derives its response_format JSON schema from this schema.
    schema = StatefulUpdateResponse.model_json_schema()
    update_schema = schema["$defs"]["StatefulOutputUpdate"]
    properties = update_schema["properties"]

    assert properties["current_value"]["type"] == "string"
    assert properties["proposed_value"]["type"] == "string"
    assert "current_value" in update_schema["required"]
    assert "proposed_value" in update_schema["required"]
    assert update_schema["additionalProperties"] is False
    assert schema["additionalProperties"] is False
    _assert_no_typeless_properties(schema)


def test_response_boundary_round_trips_all_flexible_benchmark_values() -> None:
    expected = load_ground_truth_updates()

    response = StatefulUpdateResponse.from_proposed_updates(expected)
    decoded = response.to_proposed_updates()

    assert decoded == expected
    assert len(decoded) == 52


def test_response_boundary_preserves_multi_action_sets() -> None:
    expected = [
        update
        for update in load_ground_truth_updates()
        if update.case_id == "patient-01:event-02:ehr_alpha"
    ]

    decoded = StatefulUpdateResponse.from_proposed_updates(expected).to_proposed_updates()

    assert decoded == expected
    assert len(decoded) == 3
