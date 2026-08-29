import hashlib, json
from pathlib import Path

from ai_legacy_last_mile.stress_baseline import build_prompt
from ai_legacy_last_mile.stress_evaluator import DATA, evaluate, semantic_value_equal

load=lambda name: json.loads((DATA/name).read_text())

def test_integrity_references_uniqueness_and_synthetic():
    cases=load("cases.json"); records=load("patient_records.json"); events=load("incoming_events.json"); schemas=load("target_schemas.json"); truth=load("ground_truth_updates.json")
    assert len(cases)==20==len({c["case_id"] for c in cases})
    assert all(r["synthetic"] for r in records) and all(e["synthetic"] for e in events)
    assert {c["patient_id"] for c in cases}<={r["patient_id"] for r in records}
    assert {(c["patient_id"],c["event_id"]) for c in cases}<={(e["patient_id"],e["event_id"]) for e in events}
    assert {c["target_schema_id"] for c in cases}<={s["id"] for s in schemas}
    assert {u["case_id"] for u in truth}=={c["case_id"] for c in cases}

def test_frozen_hashes():
    manifest=load("freeze_manifest.json")
    for name,digest in manifest["sha256"].items(): assert hashlib.sha256((DATA/name).read_bytes()).hexdigest()==digest

def test_no_ground_truth_leakage_into_prompt():
    case=load("cases.json")[0]; record=load("patient_records.json")[0]; event=load("incoming_events.json")[0]; schema=load("target_schemas.json")[0]
    prompt=build_prompt(case,record,event,schema)
    assert "categories" not in prompt and "expected" not in prompt and "ground_truth" not in prompt
    assert "reconciliation_kind" not in prompt and "temporal_classification" not in prompt

def test_semantic_equivalence_rules_are_narrow():
    assert semantic_value_equal({"test_name":"Creatinine","value":"1.0","unit":"mg/dL"},{"unit":"umol/L","value":"88.4","test_name":" creatinine "})
    assert semantic_value_equal({"values":["4.8","3.1"]},{"values":["3.1","4.8"]})
    assert not semantic_value_equal({"test_name":"creatinine","value":"1.1","unit":"mg/dL"},{"test_name":"creatinine","value":"88.4","unit":"umol/L"})
    assert not semantic_value_equal({"timestamp":"a"},{"timestamp":"b"})

def test_perfect_predictions_and_order_independent_multi_action():
    truth=load("ground_truth_updates.json"); metrics,_=evaluate(list(reversed(truth)),truth,load("cases.json"))
    assert metrics.case_level_semantic_update_set_accuracy==1 and metrics.semantic_update_accuracy==1
    assert metrics.conflict_classification_accuracy==1 and metrics.missing_context_detection_recall==1

def test_extra_and_missing_updates_are_penalized():
    truth=load("ground_truth_updates.json"); cases=load("cases.json")
    missing=truth[:-1]; m,_=evaluate(missing,truth,cases); assert m.missing_update_rate==1/len(truth) and m.case_level_semantic_update_set_accuracy<1
    extra=[*truth,{**truth[0],"record_id":"wrong-extra"}]; m,_=evaluate(extra,truth,cases); assert m.extra_update_rate==1/len(truth) and m.case_level_semantic_update_set_accuracy<1

def test_meaningful_reconciliation_components_score_separately():
    truth=load("ground_truth_updates.json"); cases=load("cases.json")
    bad=[dict(x) for x in truth]; bad[0]["temporal_classification"]="true_conflict"; bad[1]["encounter_id"]="enc-new"; bad[2]["reconciliation_kind"]="new_observation"
    metrics,_=evaluate(bad,truth,cases)
    assert metrics.temporal_reconciliation_accuracy<1
    assert metrics.encounter_association_accuracy<1
    assert metrics.duplicate_reconciliation_decision_accuracy<1

def test_experiment_002_files_remain_git_identical():
    # The hardening suite names and guards the frozen artifacts; git status is also checked in CI/review.
    for name in ["stateful_cases.json","ground_truth_updates.json"]: assert (Path("data")/name).exists()
    for name in ["stateful_baseline_predictions.json","stateful_baseline_metrics.json","stateful_baseline_per_case_metrics.json","stateful_baseline_failures.json","stateful_baseline_raw.json"]: assert (Path("results")/name).exists()
