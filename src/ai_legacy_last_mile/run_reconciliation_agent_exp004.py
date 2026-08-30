"""Run and evaluate Experiment 004 without overwriting prior artifacts."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .canonical_update_compiler_exp004 import compile_plan_exp004
from .llm import LLMClient, OpenAIClient
from .reconciliation_planner_exp004 import plan_case_exp004
from .stress_evaluator import evaluate
from .stress_integrity import verify_frozen_stress_benchmark

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "stress_benchmark"
RESULTS = ROOT / "results"


def _load(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def run_experiment_exp004(
    client: LLMClient,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cases = _load("cases.json")
    records = {row["patient_id"]: row for row in _load("patient_records.json")}
    events = {(row["patient_id"], row["event_id"]): row for row in _load("incoming_events.json")}
    schemas = {row["id"]: row for row in _load("target_schemas.json")}
    predictions: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for case in cases:
        case_id = case["case_id"]
        raw_text: str | None = None
        record = records[case["patient_id"]]
        event = events[(case["patient_id"], case["event_id"])]
        schema = schemas[case["target_schema_id"]]
        try:
            plan, raw_text = plan_case_exp004(client, case, record, event, schema)
            compiled = compile_plan_exp004(plan, record, event, schema)
            predictions.extend(update.model_dump(mode="json") for update in compiled.updates)
            plans.append({
                "case_id": case_id,
                "input": {"case": {key: case[key] for key in ("case_id", "patient_id", "event_id", "target_schema_id")}, "current_patient_record": record, "incoming_event": event, "target_schema": schema},
                "plan": plan.model_dump(mode="json"),
                "compiler_decisions": compiled.decisions,
                "execution_policy": compiled.execution_policy,
                "final_updates": [update.model_dump(mode="json") for update in compiled.updates],
            })
            raw.append({"case_id": case_id, "response": raw_text})
        except Exception as exc:
            failures.append({"case_id": case_id, "error_type": type(exc).__name__, "message": str(exc)})
            raw.append({"case_id": case_id, "response": raw_text, "error": str(exc)})
    return predictions, plans, raw, failures


def _write(name: str, value: Any) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    verify_frozen_stress_benchmark()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is required")
    model = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")
    started = time.monotonic()
    predictions, plans, raw, failures = run_experiment_exp004(OpenAIClient(api_key, model))
    metrics, per_case = evaluate(predictions, _load("ground_truth_updates.json"), _load("cases.json"))
    by_case = {row["case_id"]: row for row in per_case}
    for trajectory in plans:
        trajectory["evaluator_result"] = by_case[trajectory["case_id"]]
    _write("stress_exp004_predictions.json", predictions)
    _write("stress_exp004_plans.json", plans)
    _write("stress_exp004_raw.json", raw)
    _write("stress_exp004_failures.json", failures)
    payload = asdict(metrics) | {
        "model": model,
        "model_calls": len(_load("cases.json")),
        "failed_calls": len(failures),
        "runtime_seconds": round(time.monotonic() - started, 3),
    }
    _write("stress_exp004_metrics.json", payload)
    _write("stress_exp004_per_case_metrics.json", per_case)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
