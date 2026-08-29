"""Deterministic evaluation for proposed stateful patient-record updates."""

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from itertools import permutations
from pathlib import Path

from pydantic import TypeAdapter

from .datasets import load_ground_truth_updates, load_update_cases
from .models import ProposedUpdate, UpdateActionType, UpdateCase


@dataclass(frozen=True)
class UpdateMetrics:
    """Aggregate and primary case-level stateful benchmark scores."""

    expected_cases: int
    predicted_cases: int
    expected_updates: int
    predicted_updates: int
    case_level_exact_update_set_accuracy: float
    exact_update_accuracy: float
    action_type_accuracy: float
    target_path_accuracy: float
    value_accuracy: float
    source_traceability_accuracy: float
    conflict_detection_recall: float
    missing_context_detection_recall: float


@dataclass(frozen=True)
class CaseEvaluation:
    """Complete-set and component results for one destination-specific case."""

    case_id: str
    patient_id: str
    event_id: str
    target_schema_id: str
    expected_updates: int
    predicted_updates: int
    exact_update_set: bool
    exact_matches: int
    action_type_matches: int
    target_path_matches: int
    value_matches: int
    source_traceability_matches: int


def _case_key(update: ProposedUpdate) -> tuple[str, str, str, str]:
    return update.case_id, update.patient_id, update.event_id, update.target_schema_id


def _component_matches(
    predicted: ProposedUpdate | None, expected: ProposedUpdate | None
) -> tuple[bool, bool, bool, bool, bool]:
    if predicted is None or expected is None:
        return False, False, False, False, False
    action = predicted.action_type == expected.action_type
    target = predicted.target_path == expected.target_path
    value = predicted.proposed_value == expected.proposed_value
    traceability = set(predicted.source_fact_ids) == set(expected.source_fact_ids)
    return action and target and value and traceability, action, target, value, traceability


def _update_signature(update: ProposedUpdate) -> tuple[str, str | None, str, tuple[str, ...]]:
    return (
        update.action_type.value,
        update.target_path,
        json.dumps(update.proposed_value, sort_keys=True, separators=(",", ":")),
        tuple(sorted(update.source_fact_ids)),
    )


def _align_case(
    predicted: list[ProposedUpdate], expected: list[ProposedUpdate]
) -> list[tuple[ProposedUpdate | None, ProposedUpdate | None]]:
    """Find the deterministic alignment maximizing total component agreement."""

    size = max(len(predicted), len(expected))
    if size == 0:
        return []
    predicted_slots: list[ProposedUpdate | None] = sorted(predicted, key=_update_signature)
    predicted_slots.extend([None] * (size - len(predicted_slots)))
    expected_slots: list[ProposedUpdate | None] = sorted(expected, key=_update_signature)
    expected_slots.extend([None] * (size - len(expected_slots)))

    best_pairs: list[tuple[ProposedUpdate | None, ProposedUpdate | None]] | None = None
    best_score: tuple[int, int, int, int, int, int] | None = None
    for ordering in permutations(predicted_slots):
        pairs = list(zip(ordering, expected_slots, strict=True))
        counts = [sum(matches) for matches in zip(
            *(_component_matches(predicted_update, expected_update) for predicted_update, expected_update in pairs),
            strict=True,
        )]
        score = (sum(counts), *counts)
        if best_score is None or score > best_score:
            best_score = score
            best_pairs = pairs
    return best_pairs or []


def _case_set_is_exact(predicted: list[ProposedUpdate], expected: list[ProposedUpdate]) -> bool:
    return Counter(map(_update_signature, predicted)) == Counter(map(_update_signature, expected))


def evaluate_update_cases(
    predicted: list[ProposedUpdate],
    expected: list[ProposedUpdate],
    cases: list[UpdateCase] | None = None,
) -> tuple[UpdateMetrics, list[CaseEvaluation]]:
    """Score complete destination-specific update sets and diagnostic components."""

    predicted_by_case: dict[tuple[str, str, str, str], list[ProposedUpdate]] = {}
    expected_by_case: dict[tuple[str, str, str, str], list[ProposedUpdate]] = {}
    for update in predicted:
        predicted_by_case.setdefault(_case_key(update), []).append(update)
    for update in expected:
        expected_by_case.setdefault(_case_key(update), []).append(update)

    manifest_keys = {
        (case.case_id, case.patient_id, case.event_id, case.target_schema_id)
        for case in (cases or [])
    }
    case_keys = sorted(manifest_keys | set(predicted_by_case) | set(expected_by_case))
    per_case: list[CaseEvaluation] = []
    totals = [0, 0, 0, 0, 0]
    conflict_expected = conflict_detected = 0
    missing_expected = missing_detected = 0
    action_denominator = 0
    exact_cases = 0
    for case_id, patient_id, event_id, target_schema_id in case_keys:
        key = (case_id, patient_id, event_id, target_schema_id)
        predicted_case = predicted_by_case.get(key, [])
        expected_case = expected_by_case.get(key, [])
        pairs = _align_case(predicted_case, expected_case)
        counts = [0, 0, 0, 0, 0]
        for predicted_update, expected_update in pairs:
            matches = _component_matches(predicted_update, expected_update)
            counts = [count + int(match) for count, match in zip(counts, matches, strict=True)]
        for expected_update in expected_case:
            if expected_update.action_type == UpdateActionType.FLAG_CONFLICT:
                conflict_expected += 1
                conflict_detected += int(
                    any(
                        update.action_type == UpdateActionType.FLAG_CONFLICT
                        for update in predicted_case
                    )
                )
            if expected_update.action_type == UpdateActionType.FLAG_MISSING_CONTEXT:
                missing_expected += 1
                missing_detected += int(
                    any(
                        update.action_type == UpdateActionType.FLAG_MISSING_CONTEXT
                        for update in predicted_case
                    )
                )
        exact_set = _case_set_is_exact(predicted_case, expected_case)
        exact_cases += int(exact_set)
        action_denominator += len(pairs)
        totals = [total + count for total, count in zip(totals, counts, strict=True)]
        per_case.append(
            CaseEvaluation(
                case_id=case_id,
                patient_id=patient_id,
                event_id=event_id,
                target_schema_id=target_schema_id,
                expected_updates=len(expected_case),
                predicted_updates=len(predicted_case),
                exact_update_set=exact_set,
                exact_matches=counts[0],
                action_type_matches=counts[1],
                target_path_matches=counts[2],
                value_matches=counts[3],
                source_traceability_matches=counts[4],
            )
        )

    def action_accuracy(matches: int) -> float:
        return matches / action_denominator if action_denominator else 1.0

    expected_case_keys = manifest_keys or set(expected_by_case)
    predicted_case_keys = set(predicted_by_case)
    metrics = UpdateMetrics(
        expected_cases=len(expected_case_keys),
        predicted_cases=len(predicted_case_keys),
        expected_updates=len(expected),
        predicted_updates=len(predicted),
        case_level_exact_update_set_accuracy=(exact_cases / len(case_keys) if case_keys else 1.0),
        exact_update_accuracy=action_accuracy(totals[0]),
        action_type_accuracy=action_accuracy(totals[1]),
        target_path_accuracy=action_accuracy(totals[2]),
        value_accuracy=action_accuracy(totals[3]),
        source_traceability_accuracy=action_accuracy(totals[4]),
        conflict_detection_recall=(
            conflict_detected / conflict_expected if conflict_expected else 1.0
        ),
        missing_context_detection_recall=(
            missing_detected / missing_expected if missing_expected else 1.0
        ),
    )
    return metrics, per_case


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate stateful update predictions")
    parser.add_argument("predictions", type=Path, help="JSON list of ProposedUpdate objects")
    parser.add_argument("--output", type=Path, help="Write aggregate metrics as JSON")
    parser.add_argument("--per-case-output", type=Path, help="Write per-case results as JSON")
    args = parser.parse_args()
    with args.predictions.open(encoding="utf-8") as prediction_file:
        predicted = TypeAdapter(list[ProposedUpdate]).validate_python(json.load(prediction_file))
    metrics, per_case = evaluate_update_cases(
        predicted, load_ground_truth_updates(), load_update_cases()
    )
    rendered = json.dumps(asdict(metrics), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.per_case_output:
        args.per_case_output.parent.mkdir(parents=True, exist_ok=True)
        args.per_case_output.write_text(
            json.dumps([asdict(result) for result in per_case], indent=2) + "\n",
            encoding="utf-8",
        )
    print(rendered, end="")


if __name__ == "__main__":
    main()
