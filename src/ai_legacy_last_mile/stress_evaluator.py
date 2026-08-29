"""Semantic evaluator for frozen stress benchmark v1.

Normalization is deliberately narrow: object key and set-like list ordering,
case/whitespace in identity text, and the two conversions declared by the
benchmark (creatinine mg/dL <-> umol/L and glucose mg/dL <-> mmol/L).
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
from itertools import permutations
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "stress_benchmark"

IDENTITY_KEYS = {"description", "title", "test_name", "document_type"}
SET_KEYS = {"aliases", "values"}
CONVERSIONS = {"creatinine": {"mg/dl": Decimal("88.4")}, "glucose": {"mg/dl": Decimal("0.0555")}}


@dataclass(frozen=True)
class StressMetrics:
    benchmark_version: str
    expected_cases: int
    expected_updates: int
    predicted_updates: int
    case_level_semantic_update_set_accuracy: float
    semantic_update_accuracy: float
    action_decision_accuracy: float
    target_record_identity_accuracy: float
    encounter_association_accuracy: float
    value_accuracy: float
    provenance_source_attribution_accuracy: float
    temporal_reconciliation_accuracy: float
    duplicate_reconciliation_decision_accuracy: float
    conflict_classification_accuracy: float
    missing_context_detection_recall: float
    extra_update_rate: float
    missing_update_rate: float


def _text(value: str) -> str:
    return " ".join(value.casefold().split())


def _normalize(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        # Numeric observations have a deterministic benchmark-defined unit form.
        if {"test_name", "value", "unit"} <= value.keys():
            test = _text(str(value["test_name"])); unit = _text(str(value["unit"])); number = Decimal(str(value["value"]))
            factor = CONVERSIONS.get(test, {}).get(unit)
            if factor is not None:
                number *= factor; unit = "umol/l" if test == "creatinine" else "mmol/l"
            rest = {k: v for k, v in value.items() if k not in {"test_name", "value", "unit"}}
            normalized = {"test_name": test, "value": str(number.quantize(Decimal("0.001")).normalize()), "unit": unit}
            normalized.update({k: _normalize(v, k) for k, v in rest.items()})
            return normalized
        return {k: _normalize(v, k) for k, v in sorted(value.items())}
    if isinstance(value, list):
        items = [_normalize(v, key) for v in value]
        if key in SET_KEYS:
            return sorted(items, key=lambda item: json.dumps(item, sort_keys=True))
        return items
    if isinstance(value, str) and key in IDENTITY_KEYS:
        return _text(value)
    return value


def semantic_value_equal(left: Any, right: Any) -> bool:
    return _normalize(left) == _normalize(right)


COMPONENTS = ("action", "target", "encounter", "value", "provenance", "temporal", "reconciliation")


def _matches(predicted: dict[str, Any] | None, expected: dict[str, Any] | None) -> dict[str, bool]:
    if predicted is None or expected is None:
        return {name: False for name in COMPONENTS}
    return {
        "action": predicted.get("action_type") == expected.get("action_type"),
        "target": (predicted.get("target_path"), predicted.get("record_id")) == (expected.get("target_path"), expected.get("record_id")),
        "encounter": predicted.get("encounter_id") == expected.get("encounter_id"),
        "value": semantic_value_equal(predicted.get("value"), expected.get("value")),
        "provenance": set(predicted.get("source_fact_ids", [])) == set(expected.get("source_fact_ids", [])) and _normalize(predicted.get("provenance")) == _normalize(expected.get("provenance")),
        "temporal": predicted.get("timestamp") == expected.get("timestamp") and predicted.get("temporal_classification") == expected.get("temporal_classification"),
        "reconciliation": predicted.get("reconciliation_kind") == expected.get("reconciliation_kind"),
    }


def _align(predicted: list[dict[str, Any]], expected: list[dict[str, Any]]) -> list[tuple[dict[str, Any] | None, dict[str, Any] | None]]:
    size = max(len(predicted), len(expected)); p = [*predicted, *([None] * (size-len(predicted)))]; e = [*expected, *([None] * (size-len(expected)))]
    if not size: return []
    best = None; best_score = -1
    for order in permutations(p):
        pairs = list(zip(order, e, strict=True)); score = sum(sum(_matches(a,b).values()) for a,b in pairs)
        if score > best_score: best, best_score = pairs, score
    return best or []


def evaluate(predictions: list[dict[str, Any]], ground_truth: list[dict[str, Any]], cases: list[dict[str, Any]]) -> tuple[StressMetrics, list[dict[str, Any]]]:
    byp: dict[str,list[dict[str,Any]]] = {}; bye: dict[str,list[dict[str,Any]]] = {}
    for row in predictions: byp.setdefault(row["case_id"], []).append(row)
    for row in ground_truth: bye.setdefault(row["case_id"], []).append(row)
    totals = Counter(); denoms = Counter(); exact_cases = extras = missing = 0; per_case=[]
    for case in cases:
        cid=case["case_id"]; pred=byp.get(cid,[]); exp=bye.get(cid,[]); pairs=_align(pred,exp); exact= len(pred)==len(exp) and all(all(_matches(a,b).values()) for a,b in pairs)
        exact_cases += exact; extras += max(0,len(pred)-len(exp)); missing += max(0,len(exp)-len(pred))
        row={"case_id":cid,"target_schema_id":case["target_schema_id"],"categories":case["categories"],"expected_updates":len(exp),"predicted_updates":len(pred),"semantic_update_set_correct":exact}
        for name in COMPONENTS:
            applicable=[(a,b) for a,b in pairs if b is not None and (name not in {"encounter","temporal"} or b.get("encounter_id" if name=="encounter" else "temporal_classification") is not None)]
            matches=sum(_matches(a,b)[name] for a,b in applicable); totals[name]+=matches; denoms[name]+=len(applicable); row[f"{name}_matches"]=matches; row[f"{name}_denominator"]=len(applicable)
        semantic=sum(all(_matches(a,b).values()) for a,b in pairs); totals["semantic"]+=semantic; denoms["semantic"]+=len(exp); row["semantic_matches"]=semantic
        per_case.append(row)
    conflicts=[e for e in ground_truth if e["reconciliation_kind"]=="true_conflict"]; missing_ctx=[e for e in ground_truth if e["action_type"]=="FLAG_MISSING_CONTEXT"]
    def recall(items, action): return sum(any(p.get("action_type")==action for p in byp.get(e["case_id"],[])) for e in items)/len(items) if items else 1.0
    rate=lambda n,d: n/d if d else 1.0
    metrics=StressMetrics("stress-v1.0.0",len(cases),len(ground_truth),len(predictions),rate(exact_cases,len(cases)),rate(totals["semantic"],denoms["semantic"]),rate(totals["action"],denoms["action"]),rate(totals["target"],denoms["target"]),rate(totals["encounter"],denoms["encounter"]),rate(totals["value"],denoms["value"]),rate(totals["provenance"],denoms["provenance"]),rate(totals["temporal"],denoms["temporal"]),rate(totals["reconciliation"],denoms["reconciliation"]),recall(conflicts,"FLAG_CONFLICT"),recall(missing_ctx,"FLAG_MISSING_CONTEXT"),rate(extras,len(ground_truth)),rate(missing,len(ground_truth)))
    return metrics,per_case


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("predictions",type=Path); parser.add_argument("--output",type=Path,default=ROOT/"results/stress_baseline_metrics.json"); parser.add_argument("--per-case-output",type=Path,default=ROOT/"results/stress_baseline_per_case_metrics.json"); args=parser.parse_args()
    load=lambda p: json.loads(p.read_text(encoding="utf-8")); metrics, per_case=evaluate(load(args.predictions),load(DATA/"ground_truth_updates.json"),load(DATA/"cases.json")); args.output.parent.mkdir(exist_ok=True); args.output.write_text(json.dumps(asdict(metrics),indent=2)+"\n"); args.per_case_output.write_text(json.dumps(per_case,indent=2)+"\n"); print(json.dumps(asdict(metrics),indent=2))

if __name__ == "__main__": main()
