"""Prompting and validation for the Experiment 003 reconciliation planner."""

import json
from typing import Any

from .llm import LLMClient
from .reconciliation_models import ReconciliationPlan


def build_reconciliation_prompt(
    case: dict[str, Any],
    record: dict[str, Any],
    event: dict[str, Any],
    schema: dict[str, Any],
) -> str:
    """Build a ground-truth-free prompt that asks for decisions, not payloads."""
    safe_case = {
        key: case[key]
        for key in ("case_id", "patient_id", "event_id", "target_schema_id")
    }
    payload = {
        "case": safe_case,
        "current_patient_record": record,
        "incoming_event": event,
        "target_schema": schema,
    }
    rules = """You are the reconciliation planning stage of a synthetic administrative EHR research prototype. Do not diagnose or recommend care. Produce an explicit plan, not final EHR payloads.

Group facts that jointly describe one identity, conflict, or update; keep genuinely independent actions separate. Match records and encounters only from the supplied input. Classify identity and time using the response enums. Equivalent values at the same time are duplicates (creatinine: 1 mg/dL = 88.4 umol/L; glucose: 1 mg/dL = 0.0555 mmol/L). A later measurement is new history, not a conflict. Conflicting claims about one same-time/external identity are one TRUE_CONFLICT. Missing identity or ambiguous encounter context is MISSING_CONTEXT.

Use ADD for a new record, UPDATE for a partial duplicate with meaningful metadata, LINK only when a represented item gains a new external identity, NO_OP for a represented duplicate without a new identity, and the matching FLAG action for conflict/missing context. Workflow review or human approval is policy, never a separate plan item. Set human_approval_required on consequential actions instead. target_collection must be one exact field from target_schema. proposed_record_id is needed only for ADD when a stable incoming identifier can be selected or proposed; never replace a matched record ID. Cite short evidence strings and include only source fact IDs from this event. Return structured output only."""
    return f"{rules}\nCASE INPUT:\n{json.dumps(payload, indent=2)}"


def plan_case(
    client: LLMClient,
    case: dict[str, Any],
    record: dict[str, Any],
    event: dict[str, Any],
    schema: dict[str, Any],
) -> tuple[ReconciliationPlan, str]:
    """Make exactly one provider-neutral structured planning call."""
    completion = client.complete(
        build_reconciliation_prompt(case, record, event, schema), ReconciliationPlan
    )
    plan = ReconciliationPlan.model_validate(completion.parsed)
    valid_ids = {fact["id"] for fact in event["facts"]}
    if plan.case_id != case["case_id"]:
        raise ValueError("planner returned the wrong case identity")
    used = [fact_id for item in plan.items for fact_id in item.source_fact_ids]
    if not set(used) <= valid_ids:
        raise ValueError("planner referenced a fact outside the incoming event")
    return plan, completion.raw_text
