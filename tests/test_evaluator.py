import json
import sys

import pytest

from ai_legacy_last_mile.datasets import load_ground_truth
from ai_legacy_last_mile.evaluator import evaluate_cases, evaluate_mappings, main
from ai_legacy_last_mile.models import MappingResult


def test_ground_truth_scores_perfectly_against_itself() -> None:
    truth = load_ground_truth()

    metrics = evaluate_cases(truth, truth)

    assert metrics.correct == 100
    assert metrics.accuracy == 1.0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0


def test_evaluator_penalizes_wrong_and_missing_assignments() -> None:
    expected = [
        MappingResult(source_fact_id="a", target_field_path="target.a", value="right"),
        MappingResult(source_fact_id="b", target_field_path="target.b", value=2),
    ]
    predicted = [
        MappingResult(source_fact_id="a", target_field_path="target.a", value="wrong"),
    ]

    metrics = evaluate_mappings(predicted, expected)

    assert metrics.correct == 0
    assert metrics.precision == 0.0
    assert metrics.recall == 0.0
    assert metrics.accuracy == 0.0


def test_evaluator_is_order_independent() -> None:
    expected = [
        MappingResult(source_fact_id="a", target_field_path="x", value=True),
        MappingResult(source_fact_id="b", target_field_path="y", value={"nested": 1}),
    ]

    metrics = evaluate_mappings(list(reversed(expected)), expected)

    assert metrics.accuracy == pytest.approx(1.0)


def test_cli_saves_aggregate_and_per_case_metrics(tmp_path, monkeypatch) -> None:
    predictions = tmp_path / "predictions.json"
    aggregate = tmp_path / "metrics.json"
    per_case = tmp_path / "per-case.json"
    predictions.write_text(
        json.dumps([case.model_dump(mode="json") for case in load_ground_truth()])
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate-mappings",
            str(predictions),
            "--output",
            str(aggregate),
            "--per-case-output",
            str(per_case),
        ],
    )

    main()

    assert json.loads(aggregate.read_text())["accuracy"] == 1.0
    assert len(json.loads(per_case.read_text())) == 20
