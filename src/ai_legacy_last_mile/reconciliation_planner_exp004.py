"""Experiment 004 planner guidance and narrow identity normalization."""

import json
from typing import Any

from .llm import LLMClient
from .reconciliation_models import (
    CanonicalAction,
    EntityType,
    IdentityRelationship,
    PlanItem,
    ReconciliationPlan,
)


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _existing_record(record: dict[str, Any], record_id: str | None) -> dict[str, Any] | None:
    if not record_id:
        return None
    for encounter in record.get("encounters", []):
        for collection in ("documents", "requests"):
            for candidate in encounter.get(collection, []):
                if candidate.get("id") == record_id:
                    return candidate
    return None


def _only_superficial_difference(
    item: PlanItem, record: dict[str, Any], event: dict[str, Any]
) -> bool:
    """Recognize only exact field equality plus normalized identity text."""
    if item.identity_relationship is not IdentityRelationship.PARTIAL_DUPLICATE:
        return False
    if item.entity_type not in {EntityType.DOCUMENT, EntityType.REQUEST}:
        return False
    existing = _existing_record(record, item.matched_record_id)
    if existing is None:
        return False
    fact_by_id = {fact["id"]: fact for fact in event["facts"]}
    facts = [fact_by_id[fact_id] for fact_id in item.source_fact_ids]
    ignored = {"id", "kind", "institution", "encounter_id", "timestamp"}
    identity_text = {"title", "description"}
    for fact in facts:
        for key, value in fact.items():
            if key in ignored:
                continue
            if key not in existing:
                return False
            if key in identity_text and isinstance(value, str) and isinstance(existing[key], str):
                if _normalized_text(value) != _normalized_text(existing[key]):
                    return False
            elif value != existing[key]:
                return False
    return True


def normalize_superficial_duplicates(
    plan: ReconciliationPlan, record: dict[str, Any], event: dict[str, Any]
) -> ReconciliationPlan:
    """Correct a narrow formatter-only partial-duplicate classification."""
    items: list[PlanItem] = []
    for item in plan.items:
        if _only_superficial_difference(item, record, event):
            item = item.model_copy(
                update={
                    "identity_relationship": IdentityRelationship.SEMANTIC_DUPLICATE,
                    "new_write_needed": False,
                    "intended_action": CanonicalAction.NO_OP,
                }
            )
        items.append(item)
    return plan.model_copy(update={"items": items})


def build_reconciliation_prompt_exp004(
    case: dict[str, Any],
    record: dict[str, Any],
    event: dict[str, Any],
    schema: dict[str, Any],
) -> str:
    """Build the Experiment 004 plan prompt without labels or ground truth."""
    payload = {
        "case": {key: case[key] for key in ("case_id", "patient_id", "event_id", "target_schema_id")},
        "current_patient_record": record,
        "incoming_event": event,
        "target_schema": schema,
    }
    rules = """You are the reconciliation planning stage of a synthetic administrative EHR research prototype. Do not diagnose or recommend care. Produce an explicit plan, not final EHR payloads.

Group facts that jointly describe one identity, conflict, or update; keep genuinely independent actions separate. Match records and encounters only from the supplied input. Equivalent values at the same time are duplicates (creatinine: 1 mg/dL = 88.4 umol/L; glucose: 1 mg/dL = 0.0555 mmol/L). A later measurement is new history, not a conflict. Conflicting claims about one same-time/external identity are one TRUE_CONFLICT. Missing identity or ambiguous encounter context is MISSING_CONTEXT.

For document titles and request descriptions, identity comparison ignores case, leading/trailing whitespace, and repeated internal whitespace. Those formatting differences alone are SEMANTIC_DUPLICATE, never PARTIAL_DUPLICATE. Do not use broader fuzzy matching: different words, clinical qualifiers, status, timestamps, or identifiers remain meaningful. If all semantic content is represented and there is no new external identity or meaningful field, choose SEMANTIC_DUPLICATE and NO_OP.

Use ADD for a new record, UPDATE for meaningful metadata on a partial duplicate, LINK only when a represented item gains a new external identity, and the matching FLAG action for conflict/missing context. Human approval is policy, never a separate plan item. proposed_record_id must come from the input when possible; do not invent unavailable stable identifiers. Include only source fact IDs from this event. Return structured output only."""
    return f"{rules}\nCASE INPUT:\n{json.dumps(payload, indent=2)}"


def plan_case_exp004(
    client: LLMClient,
    case: dict[str, Any],
    record: dict[str, Any],
    event: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[ReconciliationPlan, str]:
    """Make one structured planning call and apply narrow normalization."""
    completion = client.complete(
        build_reconciliation_prompt_exp004(case, record, event, schema), ReconciliationPlan
    )
    plan = ReconciliationPlan.model_validate(completion.parsed)
    valid_ids = {fact["id"] for fact in event["facts"]}
    if plan.case_id != case["case_id"]:
        raise ValueError("planner returned the wrong case identity")
    if not {fact_id for item in plan.items for fact_id in item.source_fact_ids} <= valid_ids:
        raise ValueError("planner referenced a fact outside the incoming event")
    return normalize_superficial_duplicates(plan, record, event), completion.raw_text
