"""Experiment 002: one general-purpose LLM request per stateful case."""

import json
from collections import Counter
from dataclasses import dataclass

from .llm import LLMClient
from .models import (
    IncomingEvent,
    PatientRecord,
    ProposedUpdate,
    RawStatefulResponse,
    StatefulBaselineFailure,
    StatefulSchemaExtension,
    StatefulUpdateResponse,
    TargetSchema,
    UpdateActionType,
    UpdateCase,
)


@dataclass(frozen=True)
class StatefulBaselineRun:
    """Validated predictions and auditable outcomes from all case requests."""

    predictions: list[ProposedUpdate]
    raw_responses: list[RawStatefulResponse]
    failures: list[StatefulBaselineFailure]


def build_stateful_prompt(
    case: UpdateCase,
    record: PatientRecord,
    event: IncomingEvent,
    schema: TargetSchema,
    extension: StatefulSchemaExtension,
) -> str:
    """Build a case-isolated prompt containing only generation-time information."""

    payload = {
        "case": case.model_dump(mode="json"),
        "current_patient_record": record.model_dump(mode="json"),
        "incoming_event": event.model_dump(mode="json"),
        "destination_schema": schema.model_dump(mode="json"),
        "destination_operational_fields": extension.model_dump(mode="json"),
        "allowed_action_types": [action.value for action in UpdateActionType],
    }
    rules = """You are not making clinical decisions. Determine only the structured record
changes explicitly supported by the incoming information relative to the current record.

Rules:
- Never invent a diagnosis or treatment.
- Never infer a medication change unless the incoming information explicitly supports it.
- Never resolve conflicting information by guessing.
- Preserve source traceability using only fact IDs from the incoming event.
- Use only target paths in destination_schema fields or destination_operational_fields.
- Return every supported update for this case, including multiple independent updates.
- Do not omit an update because another update was found, and do not duplicate updates.
- Use NO_OP when incoming information is already represented correctly.
- Use FLAG_CONFLICT when supplied sources conflict and cannot be reconciled.
- Use FLAG_MISSING_CONTEXT when required context for safe mapping is absent.
- Consequential proposals require human review; do not apply any update.
- Return only the structured response."""
    return f"{rules}\n\nCASE INPUT:\n{json.dumps(payload, indent=2)}"


def _update_signature(update: ProposedUpdate) -> tuple[str, str | None, str, tuple[str, ...]]:
    return (
        update.action_type.value,
        update.target_path,
        json.dumps(update.proposed_value, sort_keys=True, separators=(",", ":")),
        tuple(sorted(update.source_fact_ids)),
    )


def _validate_response(
    response: StatefulUpdateResponse,
    case: UpdateCase,
    event: IncomingEvent,
    schema: TargetSchema,
    extension: StatefulSchemaExtension,
) -> None:
    """Reject invalid output without repairing model-proposed semantics."""

    expected_identity = (
        case.case_id,
        case.patient_id,
        case.event_id,
        case.target_schema_id,
    )
    for update in response.updates:
        identity = (
            update.case_id,
            update.patient_id,
            update.event_id,
            update.target_schema_id,
        )
        if identity != expected_identity:
            raise ValueError(f"update identity does not match input case: {identity}")

    valid_paths = {field.path for field in schema.fields} | {
        field.path for field in extension.fields
    }
    invalid_paths = sorted(
        {
            update.target_path
            for update in response.updates
            if update.target_path not in valid_paths
        },
        key=lambda path: path or "",
    )
    if invalid_paths:
        raise ValueError(f"target paths are not in the destination schema: {invalid_paths}")

    valid_fact_ids = {fact.id for fact in event.facts}
    unknown_fact_ids = sorted(
        {
            fact_id
            for update in response.updates
            for fact_id in update.source_fact_ids
            if fact_id not in valid_fact_ids
        }
    )
    if unknown_fact_ids:
        raise ValueError(f"source fact IDs are not in the incoming event: {unknown_fact_ids}")

    signatures = [_update_signature(update) for update in response.updates]
    duplicates = [signature for signature, count in Counter(signatures).items() if count > 1]
    if duplicates:
        raise ValueError("response contains duplicate update objects")


def run_stateful_baseline(
    records: list[PatientRecord],
    events: list[IncomingEvent],
    cases: list[UpdateCase],
    schemas: list[TargetSchema],
    extensions: list[StatefulSchemaExtension],
    client: LLMClient,
) -> StatefulBaselineRun:
    """Make exactly one request per case and never retry failed generations."""

    records_by_id = {record.patient_id: record for record in records}
    events_by_id = {(event.patient_id, event.event_id): event for event in events}
    schemas_by_id = {schema.id: schema for schema in schemas}
    extensions_by_id = {extension.target_schema_id: extension for extension in extensions}
    predictions: list[ProposedUpdate] = []
    raw_responses: list[RawStatefulResponse] = []
    failures: list[StatefulBaselineFailure] = []

    for case in cases:
        record = records_by_id[case.patient_id]
        event = events_by_id[(case.patient_id, case.event_id)]
        schema = schemas_by_id[case.target_schema_id]
        extension = extensions_by_id[case.target_schema_id]
        raw_text: str | None = None
        try:
            completion = client.complete(
                build_stateful_prompt(case, record, event, schema, extension),
                StatefulUpdateResponse,
            )
            raw_text = completion.raw_text
            response = StatefulUpdateResponse.model_validate(completion.parsed)
            _validate_response(response, case, event, schema, extension)
            predictions.extend(response.updates)
            raw_responses.append(
                RawStatefulResponse(
                    **case.model_dump(),
                    response=raw_text,
                )
            )
        except Exception as error:
            message = str(error)
            failures.append(
                StatefulBaselineFailure(
                    **case.model_dump(),
                    error_type=type(error).__name__,
                    message=message,
                )
            )
            raw_responses.append(
                RawStatefulResponse(
                    **case.model_dump(),
                    response=raw_text,
                    error=message,
                )
            )
    return StatefulBaselineRun(predictions, raw_responses, failures)
