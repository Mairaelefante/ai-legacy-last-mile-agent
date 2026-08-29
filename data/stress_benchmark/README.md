# Stateful reconciliation stress benchmark v1.0.0

This frozen, synthetic-only benchmark contains 20 case-isolated administrative
record-reconciliation tasks across `ehr_alpha` and `ehr_beta`. Ground truth is
stored only in `ground_truth_updates.json`; it is never loaded by the baseline.

## Allowed evaluation equivalences

The evaluator ignores JSON object key order; ignores order only for fields
explicitly modeled as sets (`values`, `aliases`); and folds whitespace/case only
for `description`, `title`, `test_name`, and `document_type`. It recognizes only
these exact deterministic conversions: creatinine `1 mg/dL = 88.4 umol/L` and
glucose `1 mg/dL = 0.0555 mmol/L` (values compared to three decimal places).
Source-fact IDs are sets. No action, target path, record ID, encounter,
timestamp, provenance, reconciliation classification, missing/extra update, or
list ordering outside the named set fields is normalized away.

The primary metric is **case-level semantic update-set accuracy**: every
expected update must match semantically and no extra update may be present.
Secondary metrics report their actual applicable denominators through the
per-case artifact. `freeze_manifest.json` records statistics, rules, and SHA-256
digests for every inference input and ground-truth file.

Research prototype. Synthetic data only. No autonomous clinical decisions. No production EHR deployment. Human approval required for consequential write actions.
