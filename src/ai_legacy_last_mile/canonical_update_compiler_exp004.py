"""Narrow Experiment 004 canonicalization over the Experiment 003 compiler."""

from typing import Any

from .canonical_update_compiler import (
    CompilationResult,
    _facts,
    _find_existing,
    compile_plan,
)
from .reconciliation_models import (
    CanonicalAction,
    EntityType,
    PlanItem,
    ReconciliationPlan,
    TemporalRelationship,
)


def _missing_dimensions(item: PlanItem, facts: list[dict[str, Any]]) -> list[str]:
    if item.entity_type is EntityType.RESULT:
        dimensions = (("test identity", "test_name"), ("unit", "unit"), ("timestamp", "timestamp"))
        return [label for label, key in dimensions if not any(fact.get(key) for fact in facts)]
    if item.entity_type is EntityType.DOCUMENT:
        stable_keys = ("accession", "external_document_id", "external_id")
        return [] if any(fact.get(key) for fact in facts for key in stable_keys) else ["document identity"]
    return []


def _joined_dimensions(dimensions: list[str]) -> str:
    if len(dimensions) == 1:
        return dimensions[0]
    if len(dimensions) == 2:
        return " and ".join(dimensions)
    return f"{', '.join(dimensions[:-1])}, and {dimensions[-1]}"


def _missing_value_exp004(
    item: PlanItem, facts: list[dict[str, Any]], record: dict[str, Any]
) -> dict[str, Any]:
    dimensions = _missing_dimensions(item, facts)
    incoming = next((fact for fact in facts if fact.get("kind") != "identity"), facts[0])
    if item.entity_type is EntityType.DOCUMENT and dimensions:
        return {
            "reason": "document accession or external identifier missing",
            "title": incoming.get("title"),
        }
    if dimensions:
        return {
            "reason": f"{_joined_dimensions(dimensions)} missing",
            "value": incoming.get("value"),
        }
    if item.temporal_relationship is TemporalRelationship.AMBIGUOUS:
        timestamp = next((fact.get("timestamp") for fact in facts if fact.get("timestamp")), None)
        date = timestamp[:10] if timestamp else None
        candidates = [
            encounter["id"]
            for encounter in record.get("encounters", [])
            if not date or encounter.get("date") == date
        ]
        return {"reason": "encounter ambiguous", "candidate_encounters": candidates}
    return {"reason": item.reason}


def _temporal_exp004(item: PlanItem) -> str | None:
    """Emit time only when it materially distinguishes a result reconciliation."""
    if item.entity_type is not EntityType.RESULT:
        return None
    material = {
        TemporalRelationship.SAME_MEASUREMENT: "same_measurement",
        TemporalRelationship.DISTINCT_LATER: "distinct_time",
        TemporalRelationship.HISTORICAL: "historical_encounter",
        TemporalRelationship.AMBIGUOUS: "ambiguous",
    }
    return material.get(item.temporal_relationship)


def _conflict_value_exp004(
    item: PlanItem, facts: list[dict[str, Any]], existing: dict[str, Any] | None
) -> dict[str, Any]:
    incoming = next((fact for fact in facts if fact.get("kind") != "identity"), facts[0])
    if item.entity_type is EntityType.RESULT:
        values = [fact.get("value") for fact in facts if fact.get("kind") != "identity"]
        if existing is not None and len(values) == 1 and existing.get("value") != values[0]:
            values.insert(0, existing.get("value"))
        return {
            "test_name": incoming.get("test_name") or (existing or {}).get("test_name"),
            "values": values,
            "unit": incoming.get("unit") or (existing or {}).get("unit"),
        }
    if item.entity_type is EntityType.REQUEST and existing is not None:
        return {
            "external_id": incoming.get("external_id") or existing.get("external_id"),
            "existing_status": existing.get("status"),
            "incoming_status": incoming.get("status"),
        }
    if item.entity_type is EntityType.DOCUMENT and existing is not None:
        from .canonical_update_compiler import _side

        return {
            "accession": incoming.get("accession") or existing.get("accession"),
            "incoming_side": _side(str(incoming.get("title", ""))),
            "existing_side": _side(str(existing.get("title", ""))),
        }
    return {
        key: value
        for key, value in incoming.items()
        if key not in {"id", "kind", "institution", "encounter_id", "timestamp"}
    }


def compile_plan_exp004(
    plan: ReconciliationPlan,
    record: dict[str, Any],
    event: dict[str, Any],
    schema: dict[str, Any],
) -> CompilationResult:
    """Compile with Experiment 003 invariants, then narrowly canonicalize payloads."""
    compiled = compile_plan(plan, record, event, schema)
    items_by_facts = {tuple(item.source_fact_ids): item for item in plan.items}
    updates = []
    for update in compiled.updates:
        item = items_by_facts[tuple(update.source_fact_ids)]
        facts = _facts(item, event)
        existing, _ = _find_existing(item, record)
        changes: dict[str, Any] = {"temporal_classification": _temporal_exp004(item)}
        if update.action_type == CanonicalAction.FLAG_MISSING_CONTEXT.value:
            changes["value"] = _missing_value_exp004(item, facts, record)
        elif update.action_type == CanonicalAction.FLAG_CONFLICT.value:
            changes["value"] = _conflict_value_exp004(item, facts, existing)
        updates.append(update.model_copy(update=changes))
    return CompilationResult(
        updates=updates,
        decisions=compiled.decisions,
        execution_policy=compiled.execution_policy,
    )
