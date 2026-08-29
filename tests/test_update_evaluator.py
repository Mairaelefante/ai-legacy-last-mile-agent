import pytest

from ai_legacy_last_mile.datasets import load_ground_truth_updates, load_update_cases
from ai_legacy_last_mile.models import UpdateActionType, UpdateCase
from ai_legacy_last_mile.update_evaluator import evaluate_update_cases


def test_perfect_predictions_produce_perfect_scores_and_per_case_results() -> None:
    truth = load_ground_truth_updates()

    metrics, per_case = evaluate_update_cases(truth, truth, load_update_cases())

    assert metrics.case_level_exact_update_set_accuracy == 1.0
    assert metrics.exact_update_accuracy == 1.0
    assert metrics.action_type_accuracy == 1.0
    assert metrics.target_path_accuracy == 1.0
    assert metrics.value_accuracy == 1.0
    assert metrics.source_traceability_accuracy == 1.0
    assert metrics.conflict_detection_recall == 1.0
    assert metrics.missing_context_detection_recall == 1.0
    assert len(per_case) == 40
    assert all(result.exact_matches == result.expected_updates for result in per_case)


@pytest.mark.parametrize(
    ("change", "lower_metric"),
    [
        ({"action_type": UpdateActionType.ADD}, "action_type_accuracy"),
        ({"target_path": "wrong.section"}, "target_path_accuracy"),
        ({"proposed_value": "wrong value"}, "value_accuracy"),
        ({"source_fact_ids": ["wrong-fact"]}, "source_traceability_accuracy"),
    ],
)
def test_incorrect_component_lowers_exact_and_component_score(change, lower_metric) -> None:
    truth = load_ground_truth_updates()
    predictions = list(truth)
    predictions[1] = truth[1].model_copy(update=change)

    metrics, _ = evaluate_update_cases(predictions, truth)

    assert metrics.exact_update_accuracy < 1.0
    assert getattr(metrics, lower_metric) < 1.0


def test_missed_flags_lower_detection_recall() -> None:
    truth = load_ground_truth_updates()
    predictions = [
        update.model_copy(update={"action_type": UpdateActionType.NO_OP})
        if update.action_type
        in {UpdateActionType.FLAG_CONFLICT, UpdateActionType.FLAG_MISSING_CONTEXT}
        else update
        for update in truth
    ]

    metrics, _ = evaluate_update_cases(predictions, truth)

    assert metrics.conflict_detection_recall == 0.0
    assert metrics.missing_context_detection_recall == 0.0


def test_one_event_has_three_expected_updates_per_schema() -> None:
    truth = load_ground_truth_updates()
    event_two = [update for update in truth if update.event_id == "event-02"]

    assert len(event_two) == 6
    assert all(
        sum(update.case_id == case_id for update in event_two) == 3
        for case_id in {update.case_id for update in event_two}
    )


def test_missing_one_of_three_actions_fails_exact_case_accuracy() -> None:
    truth = load_ground_truth_updates()
    removed = next(
        update
        for update in truth
        if update.event_id == "event-02" and update.target_schema_id == "ehr_alpha"
    )

    metrics, per_case = evaluate_update_cases(
        [update for update in truth if update is not removed], truth, load_update_cases()
    )

    case = next(result for result in per_case if result.case_id == removed.case_id)
    assert case.exact_update_set is False
    assert metrics.case_level_exact_update_set_accuracy < 1.0


def test_extra_action_fails_exact_case_accuracy() -> None:
    truth = load_ground_truth_updates()
    template = truth[0]
    extra = template.model_copy(
        update={
            "target_path": template.target_path + ".unexpected",
            "source_fact_ids": ["unexpected-source-fact"],
        }
    )

    metrics, per_case = evaluate_update_cases(
        [*truth, extra], truth, load_update_cases()
    )

    case = next(result for result in per_case if result.case_id == template.case_id)
    assert case.exact_update_set is False
    assert metrics.case_level_exact_update_set_accuracy < 1.0


def test_same_semantic_request_uses_heterogeneous_target_paths() -> None:
    truth = [update for update in load_ground_truth_updates() if update.event_id == "event-03"]
    paths_by_schema = {
        schema_id: {update.target_path for update in truth if update.target_schema_id == schema_id}
        for schema_id in {update.target_schema_id for update in truth}
    }

    assert paths_by_schema["ehr_alpha"] == {"encounter.requests.radiology"}
    assert paths_by_schema["ehr_beta"] == {"chart.orders.imaging"}


def test_case_identity_distinguishes_same_event_across_schemas() -> None:
    cases = [case for case in load_update_cases() if case.event_id == "event-03"]

    assert len(cases) == 2
    assert len({case.case_id for case in cases}) == 2
    assert {case.target_schema_id for case in cases} == {"ehr_alpha", "ehr_beta"}


def test_original_single_action_scenarios_remain_valid() -> None:
    truth = load_ground_truth_updates()
    counts = {
        case.case_id: sum(update.case_id == case.case_id for update in truth)
        for case in load_update_cases()
    }

    assert sum(count == 1 for count in counts.values()) == 30


def test_manifest_can_represent_a_zero_action_case() -> None:
    empty_case = UpdateCase(
        case_id="patient-zero:event-zero:ehr_alpha",
        patient_id="patient-zero",
        event_id="event-zero",
        target_schema_id="ehr_alpha",
    )

    metrics, per_case = evaluate_update_cases([], [], [empty_case])

    assert metrics.case_level_exact_update_set_accuracy == 1.0
    assert per_case[0].expected_updates == 0
    assert per_case[0].exact_update_set is True
