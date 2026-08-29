"""Deterministic, target-agnostic field-mapping evaluation."""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import TypeAdapter

from .datasets import load_ground_truth
from .models import MappingCase, MappingResult


@dataclass(frozen=True)
class EvaluationMetrics:
    correct: int
    predicted: int
    expected: int
    precision: float
    recall: float
    accuracy: float


def evaluate_mappings(
    predicted: list[MappingResult], expected: list[MappingResult]
) -> EvaluationMetrics:
    """Score exact source/target/value assignments without mapping-specific rules."""

    def signature(mapping: MappingResult) -> tuple[str, str, str]:
        value = json.dumps(mapping.value, sort_keys=True, separators=(",", ":"))
        return mapping.source_fact_id, mapping.target_field_path, value

    predicted_set = {signature(mapping) for mapping in predicted}
    expected_set = {signature(mapping) for mapping in expected}
    correct = len(predicted_set & expected_set)
    precision = correct / len(predicted_set) if predicted_set else float(not expected_set)
    recall = correct / len(expected_set) if expected_set else float(not predicted_set)
    union = predicted_set | expected_set
    accuracy = correct / len(union) if union else 1.0
    return EvaluationMetrics(
        correct=correct,
        predicted=len(predicted_set),
        expected=len(expected_set),
        precision=precision,
        recall=recall,
        accuracy=accuracy,
    )


def evaluate_cases(
    predicted_cases: list[MappingCase], expected_cases: list[MappingCase]
) -> EvaluationMetrics:
    """Evaluate complete cases while including case identity in every assignment."""

    def qualify(cases: list[MappingCase]) -> list[MappingResult]:
        return [
            MappingResult(
                source_fact_id=f"{case.document_id}:{mapping.source_fact_id}",
                target_field_path=f"{case.target_schema_id}:{mapping.target_field_path}",
                value=mapping.value,
            )
            for case in cases
            for mapping in case.mappings
        ]

    return evaluate_mappings(qualify(predicted_cases), qualify(expected_cases))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate predicted mapping cases")
    parser.add_argument("predictions", type=Path, help="JSON file containing MappingCase objects")
    parser.add_argument("--output", type=Path, help="Write aggregate metrics as JSON")
    parser.add_argument("--per-case-output", type=Path, help="Write per-case metrics as JSON")
    args = parser.parse_args()
    with args.predictions.open(encoding="utf-8") as predictions_file:
        predicted = TypeAdapter(list[MappingCase]).validate_python(json.load(predictions_file))
    expected = load_ground_truth()
    aggregate = asdict(evaluate_cases(predicted, expected))
    expected_by_id = {(case.document_id, case.target_schema_id): case for case in expected}
    predicted_by_id = {(case.document_id, case.target_schema_id): case for case in predicted}
    per_case = []
    for case_id, expected_case in expected_by_id.items():
        predicted_case = predicted_by_id.get(case_id)
        metrics = evaluate_mappings(
            predicted_case.mappings if predicted_case else [], expected_case.mappings
        )
        per_case.append(
            {
                "document_id": case_id[0],
                "target_schema_id": case_id[1],
                **asdict(metrics),
            }
        )
    rendered = json.dumps(aggregate, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    if args.per_case_output:
        args.per_case_output.parent.mkdir(parents=True, exist_ok=True)
        args.per_case_output.write_text(json.dumps(per_case, indent=2) + "\n", encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
