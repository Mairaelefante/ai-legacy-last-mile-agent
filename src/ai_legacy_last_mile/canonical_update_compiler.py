"""Deterministically compile reconciliation decisions into canonical updates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .reconciliation_models import (
    CanonicalAction,
    EntityType,
    IdentityRelationship,
    PlanItem,
    ReconciliationPlan,
    TemporalRelationship,
)
from .stress_baseline import StressUpdate


@dataclass(frozen=True)
class CompilationResult:
    updates: list[StressUpdate]
    decisions: list[dict[str, Any]]
    execution_policy: dict[str, Any]


RELATIONSHIP_ACTION = {
    IdentityRelationship.NEW: CanonicalAction.ADD,
    IdentityRelationship.EXACT_DUPLICATE: CanonicalAction.NO_OP,
    IdentityRelationship.SEMANTIC_DUPLICATE: CanonicalAction.NO_OP,
    IdentityRelationship.EQUIVALENT_UNIT_DUPLICATE: CanonicalAction.NO_OP,
    IdentityRelationship.PARTIAL_DUPLICATE: CanonicalAction.UPDATE,
    IdentityRelationship.TRUE_CONFLICT: CanonicalAction.FLAG_CONFLICT,
    IdentityRelationship.MISSING_CONTEXT: CanonicalAction.FLAG_MISSING_CONTEXT,
}
RECONCILIATION_KIND = {
    IdentityRelationship.NEW: {
        EntityType.RESULT: "new_observation",
        EntityType.REQUEST: "new_request",
        EntityType.DOCUMENT: "new_document",
    },
    IdentityRelationship.EXACT_DUPLICATE: "semantic_duplicate",
    IdentityRelationship.SEMANTIC_DUPLICATE: "semantic_duplicate",
    IdentityRelationship.EQUIVALENT_UNIT_DUPLICATE: "equivalent_duplicate",
    IdentityRelationship.PARTIAL_DUPLICATE: "partial_duplicate",
    IdentityRelationship.TRUE_CONFLICT: "true_conflict",
    IdentityRelationship.MISSING_CONTEXT: "missing_context",
}
TEMPORAL_CLASSIFICATION = {
    TemporalRelationship.SAME_EVENT: "same_event",
    TemporalRelationship.SAME_MEASUREMENT: "same_measurement",
    TemporalRelationship.DISTINCT_LATER: "distinct_time",
    TemporalRelationship.HISTORICAL: "historical_encounter",
    TemporalRelationship.AMBIGUOUS: "ambiguous",
    TemporalRelationship.NOT_APPLICABLE: None,
}
ENTITY_SUFFIX = {
    EntityType.RESULT: ("results[]", "observations[]"),
    EntityType.REQUEST: ("requests[]", "orders[]"),
    EntityType.DOCUMENT: ("documents[]",),
}
NON_VALUE_KEYS = {"id", "kind", "institution", "encounter_id", "timestamp"}


def _facts(item: PlanItem, event: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {fact["id"]: fact for fact in event["facts"]}
    return [by_id[fact_id] for fact_id in item.source_fact_ids]


def _target_path(item: PlanItem, schema: dict[str, Any], action: CanonicalAction) -> str:
    fields = schema["fields"]
    if action in {CanonicalAction.FLAG_MISSING_CONTEXT, CanonicalAction.FLAG_CONFLICT}:
        # A conflict tied to an existing entity stays on that entity; otherwise review.
        if action is CanonicalAction.FLAG_CONFLICT and item.matched_record_id:
            candidates = [f for f in fields if f.endswith(ENTITY_SUFFIX[item.entity_type])]
            if candidates:
                return candidates[0]
        review = next((f for f in fields if f in {"workflow.review", "review_queue"}), None)
        if review:
            return review
    candidates = [f for f in fields if f.endswith(ENTITY_SUFFIX[item.entity_type])]
    if not candidates:
        raise ValueError(f"schema has no collection for {item.entity_type}")
    return candidates[0]


def _find_existing(
    item: PlanItem, record: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    if not item.matched_record_id:
        return None, None
    for encounter in record.get("encounters", []):
        for collection in ("results", "requests", "documents"):
            for existing in encounter.get(collection, []):
                if existing.get("id") == item.matched_record_id:
                    return existing, encounter.get("id")
    raise ValueError(f"matched record {item.matched_record_id!r} is absent")


def _encounter(
    item: PlanItem,
    facts: list[dict[str, Any]],
    record: dict[str, Any],
    existing_encounter: str | None,
) -> str | None:
    if item.identity_relationship is IdentityRelationship.MISSING_CONTEXT and item.temporal_relationship is TemporalRelationship.AMBIGUOUS:
        return None
    explicit = {f["encounter_id"] for f in facts if f.get("encounter_id")}
    if len(explicit) > 1:
        raise ValueError("fact group contains incompatible encounter identities")
    return item.matched_encounter_id or existing_encounter or next(iter(explicit), None) or record.get("active_encounter_id")


def _external_id(facts: list[dict[str, Any]]) -> Any:
    for key in ("external_id", "external_document_id", "accession"):
        for fact in facts:
            if fact.get(key) is not None:
                return fact[key]
    return None


def _provenance(facts: list[dict[str, Any]]) -> dict[str, Any]:
    institutions = list(dict.fromkeys(f["institution"] for f in facts if f.get("institution")))
    result: dict[str, Any]
    if len(institutions) > 1:
        result = {"institutions": institutions}
    else:
        result = {"institution": institutions[0] if institutions else None}
    result["external_id"] = _external_id(facts)
    return result


def _incoming_value(facts: list[dict[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for fact in facts:
        if fact.get("kind") == "identity":
            continue
        value.update({k: v for k, v in fact.items() if k not in NON_VALUE_KEYS})
    for fact in facts:
        if fact.get("kind") == "identity":
            value.update({k: v for k, v in fact.items() if k not in NON_VALUE_KEYS})
    return value


def _side(title: str) -> str | None:
    match = re.search(r"\b(left|right)\b", title, re.IGNORECASE)
    return match.group(1).lower() if match else None


def _conflict_value(
    item: PlanItem, facts: list[dict[str, Any]], existing: dict[str, Any] | None
) -> dict[str, Any]:
    if item.entity_type is EntityType.RESULT:
        return {
            "test_name": facts[0].get("test_name"),
            "values": [fact.get("value") for fact in facts],
            "unit": facts[0].get("unit"),
        }
    incoming = next((f for f in facts if f.get("kind") != "identity"), facts[0])
    if item.entity_type is EntityType.DOCUMENT and existing:
        return {
            "accession": incoming.get("accession"),
            "incoming_side": _side(str(incoming.get("title", ""))),
            "existing_side": _side(str(existing.get("title", ""))),
        }
    if item.entity_type is EntityType.REQUEST and existing:
        return {
            "external_id": incoming.get("external_id"),
            "existing_status": existing.get("status"),
            "incoming_status": incoming.get("status"),
        }
    return _incoming_value(facts)


def _missing_value(
    item: PlanItem, facts: list[dict[str, Any]], record: dict[str, Any]
) -> dict[str, Any]:
    incoming = _incoming_value(facts)
    if item.temporal_relationship is TemporalRelationship.AMBIGUOUS:
        timestamp = next((f.get("timestamp") for f in facts if f.get("timestamp")), None)
        date = timestamp[:10] if timestamp else None
        candidates = [e["id"] for e in record.get("encounters", []) if not date or e.get("date") == date]
        return {"reason": "encounter ambiguous", "candidate_encounters": candidates}
    if item.entity_type is EntityType.RESULT:
        missing = [name for name, key in (("test identity", "test_name"), ("unit", "unit"), ("timestamp", "timestamp")) if not any(f.get(key) for f in facts)]
        if not missing:
            return {"reason": item.reason, "value": incoming.get("value")}
        if len(missing) == 1:
            missing_text = missing[0]
        elif len(missing) == 2:
            missing_text = " and ".join(missing)
        else:
            missing_text = f"{', '.join(missing[:-1])}, and {missing[-1]}"
        return {"reason": f"{missing_text} missing", "value": incoming.get("value")}
    if item.entity_type is EntityType.DOCUMENT:
        return {"reason": "document accession or external identifier missing", "title": incoming.get("title")}
    return {"reason": item.reason}


def _value(
    item: PlanItem,
    action: CanonicalAction,
    facts: list[dict[str, Any]],
    existing: dict[str, Any] | None,
    record: dict[str, Any],
) -> dict[str, Any] | None:
    if action is CanonicalAction.FLAG_CONFLICT:
        return _conflict_value(item, facts, existing)
    if action is CanonicalAction.FLAG_MISSING_CONTEXT:
        return _missing_value(item, facts, record)
    if item.identity_relationship in {
        IdentityRelationship.EXACT_DUPLICATE,
        IdentityRelationship.SEMANTIC_DUPLICATE,
        IdentityRelationship.EQUIVALENT_UNIT_DUPLICATE,
    } and existing:
        value = {k: v for k, v in existing.items() if k not in {"id", "institution", "timestamp"}}
        if action is CanonicalAction.LINK and item.entity_type is EntityType.REQUEST:
            value["external_id"] = _external_id(facts)
        return value
    return _incoming_value(facts)


def _canonical_action(item: PlanItem, facts: list[dict[str, Any]], existing: dict[str, Any] | None) -> CanonicalAction:
    action = RELATIONSHIP_ACTION[item.identity_relationship]
    if item.identity_relationship in {
        IdentityRelationship.EXACT_DUPLICATE,
        IdentityRelationship.SEMANTIC_DUPLICATE,
        IdentityRelationship.EQUIVALENT_UNIT_DUPLICATE,
    } and existing and _external_id(facts):
        existing_ids = {existing.get("external_id"), existing.get("external_document_id"), existing.get("accession")}
        if _external_id(facts) not in existing_ids:
            action = CanonicalAction.LINK
    return action


def compile_plan(
    plan: ReconciliationPlan,
    record: dict[str, Any],
    event: dict[str, Any],
    schema: dict[str, Any],
) -> CompilationResult:
    """Compile and deduplicate one plan without consulting labels or evaluator data."""
    updates: list[StressUpdate] = []
    decisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    approval = False
    for item in plan.items:
        facts = _facts(item, event)
        existing, existing_encounter = _find_existing(item, record)
        action = _canonical_action(item, facts, existing)
        target_path = _target_path(item, schema, action)
        encounter_id = _encounter(item, facts, record, existing_encounter)
        timestamp = next((f.get("timestamp") for f in facts if f.get("timestamp")), None)
        record_id = item.matched_record_id
        if action is CanonicalAction.ADD:
            record_id = item.proposed_record_id or _external_id(facts) or facts[0]["id"]
        reconciliation = RECONCILIATION_KIND[item.identity_relationship]
        if isinstance(reconciliation, dict):
            reconciliation = reconciliation[item.entity_type]
        update = StressUpdate(
            case_id=plan.case_id,
            action_type=action.value,
            target_path=target_path,
            record_id=record_id,
            encounter_id=encounter_id,
            value=_value(item, action, facts, existing, record),
            timestamp=timestamp,
            provenance=_provenance(facts),
            source_fact_ids=item.source_fact_ids,
            reconciliation_kind=reconciliation,
            temporal_classification=TEMPORAL_CLASSIFICATION[item.temporal_relationship],
        )
        key = json.dumps(update.model_dump(mode="json"), sort_keys=True)
        emitted = key not in seen
        if emitted:
            seen.add(key)
            updates.append(update)
        approval = approval or item.human_approval_required
        decisions.append({
            "source_fact_ids": item.source_fact_ids,
            "planned_action": item.intended_action.value,
            "compiled_action": action.value,
            "target_path": target_path,
            "record_id": record_id,
            "encounter_id": encounter_id,
            "emitted": emitted,
            "reason": item.reason,
        })
    return CompilationResult(
        updates=updates,
        decisions=decisions,
        execution_policy={"human_approval_required": approval},
    )
