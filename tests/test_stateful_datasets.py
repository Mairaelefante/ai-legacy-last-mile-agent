from ai_legacy_last_mile.datasets import (
    load_ground_truth_updates,
    load_incoming_events,
    load_patient_records,
    load_stateful_schema_extensions,
    load_update_cases,
)
from ai_legacy_last_mile.models import UpdateActionType


def action_for(event_id: str):
    return next(update for update in load_ground_truth_updates() if update.event_id == event_id)


def test_loads_stateful_synthetic_datasets() -> None:
    records = load_patient_records()
    events = load_incoming_events()
    updates = load_ground_truth_updates()

    assert len(records) == 10
    assert len(events) == 20
    assert len(updates) == 52
    assert len(load_update_cases()) == 40
    assert len({record.patient_id for record in records}) == 10


def test_every_event_and_update_references_explicit_fixture_data() -> None:
    records = {record.patient_id for record in load_patient_records()}
    events = {(event.patient_id, event.event_id): event for event in load_incoming_events()}

    assert all(event.patient_id in records for event in events.values())
    assert set(events) == {
        (update.patient_id, update.event_id) for update in load_ground_truth_updates()
    }
    for update in load_ground_truth_updates():
        event = events[(update.patient_id, update.event_id)]
        assert set(update.source_fact_ids) <= {fact.id for fact in event.facts}


def test_cases_and_operational_paths_reference_both_existing_schemas() -> None:
    cases = load_update_cases()
    case_keys = {
        (case.case_id, case.patient_id, case.event_id, case.target_schema_id) for case in cases
    }
    extensions = {
        extension.target_schema_id: {field.path for field in extension.fields}
        for extension in load_stateful_schema_extensions()
    }

    assert set(extensions) == {"ehr_alpha", "ehr_beta"}
    assert {case.target_schema_id for case in cases} == set(extensions)
    assert len({case.case_id for case in cases}) == len(cases)
    for update in load_ground_truth_updates():
        assert (
            update.case_id,
            update.patient_id,
            update.event_id,
            update.target_schema_id,
        ) in case_keys
        assert update.target_path in extensions[update.target_schema_id]


def test_duplicate_produces_no_op() -> None:
    update = action_for("event-01")

    assert update.action_type == UpdateActionType.NO_OP
    assert update.current_value == update.proposed_value == "10 mg"


def test_explicit_value_change_produces_update() -> None:
    update = action_for("event-13")

    assert update.action_type == UpdateActionType.UPDATE
    assert update.current_value == "5 mg"
    assert update.proposed_value == "10 mg"


def test_new_request_produces_add() -> None:
    update = action_for("event-03")

    assert update.action_type == UpdateActionType.ADD
    assert update.target_path == "encounter.requests.radiology"


def test_incompatible_explicit_sources_produce_conflict_flag() -> None:
    update = action_for("event-06")

    assert update.action_type == UpdateActionType.FLAG_CONFLICT
    assert set(update.source_fact_ids) == {"e06-source-a", "e06-source-b"}


def test_unsafe_unnamed_result_produces_missing_context_flag() -> None:
    update = action_for("event-10")

    assert update.action_type == UpdateActionType.FLAG_MISSING_CONTEXT
    assert update.target_path == "workflow.review.missing_context"
