# Experiment changelog

## Experiment 001 — Single general-purpose LLM baseline

### Hypothesis

A single general-purpose LLM request, given all normalized facts and the complete
target schema, can produce a useful baseline for exact field mapping without
task-specific semantic rules or orchestration.

### Architecture

For each clinical-document/target-schema pair, one OpenAI Responses API request
returns Pydantic-validated structured mappings. There are no retries, tools,
verification steps, agents, or access to expected answers during generation.

### Evaluation dataset

The fixed Milestone 1 dataset: 10 wholly synthetic clinical documents crossed
with 2 heterogeneous synthetic EHR schemas, yielding 20 independent cases.

### Primary metric

Field-mapping accuracy (result pending; no baseline run has been performed).

### Known limitations

- Results can vary by model and model revision.
- One request has no opportunity to repair omissions or invalid field paths.
- Exact-value scoring gives no partial credit for semantically close outputs.
- The small synthetic dataset may not represent production legacy systems.
- API availability and structured-output support depend on the selected model.

## Experiment 001B — Stateful workflow redesign

### Observation

Simple field mapping does not represent the current patient record, information
arriving over time, duplicates, conflicts between explicit sources, or missing
information that prevents a safe mapping.

### Hypothesis

Representing the task as explicit, source-traceable record-state updates will
make the benchmark more representative of the real administrative and
information workflow.

### Architecture

This milestone adds fictional current record states, explicitly sourced incoming
events, expected `ProposedUpdate` actions, and a separate deterministic evaluator.
The allowed actions organize information or flag it for review; they do not make
clinical decisions or apply changes to a real record.

### Evaluation status

This is evaluation-environment work preparing for Experiment 002. No predictor,
multi-agent architecture, result, or improvement number is claimed yet.

## Experiment 001C — Stateful benchmark realism correction

### Observation 1

Real incoming information can require multiple record changes, while the first
stateful fixture version contained exactly one expected action per event.

### Observation 2

Stateful record updating must retain heterogeneous destination schemas or the
benchmark loses the project's AI-to-legacy-system interoperability problem.

### Change

The benchmark now supports zero-, one-, and multi-action cases through explicit
case manifests, includes five multi-action source scenarios evaluated against
both systems, and identifies every case and update by patient, event, and target
schema. Operational schema extensions preserve heterogeneous Alpha/Beta paths
without changing the Experiment 001 schemas.

### Primary metric

Case-level exact update set accuracy. A case passes only when its complete set of
action types, target paths, proposed values, and source traces is correct, with no
missing or extra action.

### Evaluation status

This remains benchmark-design work. No Experiment 002 predictor, model result,
improvement number, or multi-agent workflow is included.

## Experiment 002 — Single-LLM stateful update baseline

### Hypothesis

A general-purpose LLM receiving the current record, incoming sourced information,
and destination schema can perform a meaningful fraction of stateful record
updates, but may fail on complete multi-action coverage, conflicts, missing
context, traceability, or heterogeneous destination schemas.

### Architecture

One patient/event/schema case → one general-purpose LLM request → one structured
`ProposedUpdate` set → separate deterministic evaluation. There are no retries,
tools, verifier, critic, specialized agents, or evaluation feedback during
generation.

### Primary metric

Case-level exact update set accuracy — **pending real API run**.

### Secondary metrics

- Exact update accuracy — **pending**.
- Action-type accuracy — **pending**.
- Target-path accuracy — **pending**.
- Proposed-value accuracy — **pending**.
- Source-traceability accuracy — **pending**.
- Conflict-detection recall — **pending**.
- Missing-context detection recall — **pending**.

### Results

No performance result or improvement number has been recorded. Credentials and
external API access are required for the first real baseline run.

### Infrastructure compatibility fix

The initial real run was invalid because all requests failed during API
response-schema validation before model inference. Its 0.0 metrics are not
baseline performance.

The response-only wire contract now represents flexible current and proposed
values as JSON-encoded strings with explicit JSON Schema `type: string`, then
losslessly decodes them into the unchanged `ProposedUpdate` benchmark model.
This corrects OpenAI strict structured-output compatibility without changing the
task prompt, benchmark data, model configuration, evaluator, or update semantics.
# Stress benchmark v1.0.0 — benchmark hardening

## Invalid stress baseline attempt — structured-output schema failure

Invalid stress baseline attempt — structured-output schema failure. All 20 calls
were rejected by the API before model inference because StressResponse.value
generated an invalid JSON Schema without an explicit type. The resulting 0%
metrics are not considered a valid baseline and are excluded from performance
comparison.

This transport-only correction encodes flexible response values as JSON strings
and does not change stress-v1.0.0.

Experiment 002 showed that the original benchmark's apparent failures were
overwhelmingly output-representation mismatches rather than failures of semantic
reconciliation. Instead of claiming an artificial improvement by adding a
formatter, the next benchmark was created to test the real operational
bottleneck: reconciliation of fragmented, temporally distinct, cross-source
patient-record information.

This release adds a completely separate, frozen 20-case synthetic stress suite,
semantic evaluator, one-call baseline, leakage/integrity tests, explicit
normalization contract, benchmark statistics, and SHA-256 manifest. Experiment
002 data, evaluation behavior, prompts, and results remain unchanged.

### Valid frozen stress baseline

Using the same base model, the valid run completed all 20 calls and produced 33
updates for 24 expected updates. Case-level semantic update-set accuracy and
semantic update accuracy were 0.0. Action accuracy was 0.625, target identity
accuracy 0.5833333333, encounter accuracy 0.7826086957, and duplicate
reconciliation accuracy 0.0416666667. Conflict classification and missing-context
recall were both 1.0; extra-update rate was 0.375 and missing-update rate 0.0.

This result exposed genuine reconciliation errors as well as noncanonical output
and excess-action problems on the harder benchmark. It is not the invalid
transport-failure result described above.

## Experiment 003 — Structured reconciliation planner and canonical compiler

### Evidence and hypothesis

The valid one-call stress baseline completed all 20 calls but produced 33
updates against 24 expected updates. Action accuracy was 0.625, while canonical
value, provenance, and temporal metrics were 0.0. Inspection showed both genuine
identity/duplicate/temporal mistakes and output-contract failures: free-form
labels, richer-than-canonical payloads, decomposed partial duplicates, and
separate approval/review actions. Conflict classification and missing-context
recall were already 1.0.

The hypothesis is therefore not that more agents are needed. One LLM should
make the ambiguous reconciliation decision, while deterministic code should
enforce the operational write representation and action cardinality.

### Architecture

Each frozen case makes one provider-neutral structured-output call. The model
returns explicit fact groups, entity type, matched identities, identity and
temporal relationships, write decision, intended action, target collection,
provenance sources, evidence, and approval policy. The response model contains
only constrained scalars, lists, and enums—no unconstrained `Any` at the OpenAI
schema boundary.

A deterministic compiler then maps those decisions to schema-declared target
paths, existing/new record identities, encounters, canonical values,
source-derived provenance, reconciliation labels, and temporal labels. It
collapses identical updates and represents human approval only as execution
policy. It reads the current record, incoming event, target schema, and plan; it
does not read ground truth, evaluator output, or case-specific answer tables.

### Results

The valid 20-case run produced 24 updates for 24 expected updates. Case-level
semantic update-set accuracy was 0.35 and semantic update accuracy 0.4166666667.
Action accuracy was 0.9583333333, target identity 0.9166666667, encounter
association 0.8695652174, value 0.875, provenance 0.9166666667, temporal
reconciliation 0.8461538462, and duplicate reconciliation 0.9583333333. Conflict
classification and missing-context recall remained 1.0; extra- and missing-update
rates were both 0.0.

### Research interpretation

A low exact-match score can be a benchmark bug rather than an intelligence
failure. We rejected a formatter-driven win and redesigned evaluation around
semantic reconciliation. On the harder benchmark, the useful boundary is not
“add more agents”: the LLM is used for ambiguous reconciliation and deterministic
code enforces the write contract. The valid run improved the primary case-level
metric from 0.0 to 0.35 without changing the base model.

## Experiment 004 — Narrow canonicalization and identity normalization

### Hypothesis

Most remaining Experiment 003 failures appear to come from canonical contract
mismatches plus a small normalization/reasoning error class, rather than from a
need for additional agents. A narrowly revised one-call planner and deterministic
compiler should address those observed classes without expanding the system
architecture.

### Changes

The Experiment 004 planner explicitly treats case, surrounding whitespace, and
repeated internal whitespace in document titles and request descriptions as
superficial identity formatting. A narrow deterministic guard applies the same
normalization only when every supplied meaningful field is already represented;
it does not perform fuzzy matching or discard a new identifier or metadata field.

The Experiment 004 compiler retains the Experiment 003 compiler's action,
schema-path, record/encounter validation, provenance, approval-policy, and
deduplication behavior. It adds three general canonical rules:

1. temporal classification is emitted only for result reconciliation where
   same-measurement, distinct-later, historical-encounter, or ambiguous timing
   materially distinguishes the action;
2. missing-context payloads are derived from absent result identity/unit/time,
   absent stable document identity, or—only after intrinsic fields are present—
   ambiguous encounter context;
3. conflict payloads are derived from the actual existing and incoming values,
   statuses, or document-side text rather than planner prose.

A separate runner writes only `stress_exp004_*` artifacts. It still makes one
structured planning call per case and evaluates only after inference finishes.

### Deliberate non-changes

Experiment 004 does not modify the frozen benchmark, labels, evaluator,
Experiment 003 pipeline or artifacts, provider boundary, ground truth, or safety
policy. It adds no case-specific rules, answer-derived identifier generation,
retry, verifier, second model call, multi-agent orchestration, retrieval, external
tool, or fine-tuning. Stable identifiers unavailable in the supplied input remain
an explicit benchmark limitation.

### Final frozen-benchmark results

The valid run produced 24 updates for 24 expected updates. Case-level semantic
update-set accuracy was 0.65 and semantic update accuracy 0.6666666667. Action
accuracy was 0.875, target identity 0.8333333333, encounter association
0.9130434783, value 0.9166666667, provenance 0.9166666667, temporal reconciliation
0.7692307692, and duplicate reconciliation 0.875. Conflict classification remained
1.0, missing-context recall was 0.75, and extra- and missing-update rates were 0.0.

The primary metric improved from 7/20 exact cases in Experiment 003 to 13/20 in
Experiment 004, but the component regressions are not hidden. The two experiments
used fresh model calls. Transition analysis found 7 cases exact in both, 6 changed
from failure to exact, none changed from exact to failure, and 7 failed in both.
Five newly exact cases were primarily deterministic representation or
canonicalization improvements; one was a genuine planner/reconciliation
improvement. The observed component regressions were attributable to fresh-call
planner variance rather than the deterministic Experiment 004 transformations.

Two benchmark targets include stable identifiers unavailable from inference
input. They remain an explicit limitation: they were not hard-coded and ground
truth was not exposed to inference to increase the score.

## Final hackathon demo — narrow synthetic FHIR boundary

The final demo keeps Experiment 004 unchanged and adds a small integration layer:

```text
Synthetic FHIR Bundle
  → deterministic Synthetic FHIR Validation and Adaptation Tool
  → live Experiment 004 planner
  → deterministic Experiment 004 compiler
  → proposed FHIR-compatible change
  → separate simulated human approval
  → evolving in-memory synthetic Bundle
```

The tool supports only Patient, Encounter, Observation, and DiagnosticReport. It
requires synthetic markers, resolves local Patient/Encounter references, validates
the supported subset, and fails closed before inference. It performs adaptation,
not reconciliation reasoning.

The four-event live demo was run successfully locally with the same configured
base model and one live planner call per event:

1. new sodium: `NEW / DISTINCT_LATER` → `ADD` → approved POST Observation preview
   applied only to the in-memory synthetic Bundle;
2. equivalent-unit creatinine: `EQUIVALENT_UNIT_DUPLICATE / SAME_MEASUREMENT` →
   `NO_OP`, with no proposal or state change;
3. same-accession right/left report: `TRUE_CONFLICT / NOT_APPLICABLE` →
   `FLAG_CONFLICT`, with review required and no clinical write;
4. later potassium: `NEW / DISTINCT_LATER` → `ADD` → approved POST Observation
   preview applied only to the in-memory synthetic Bundle.

The final live summary was 2 observations added, 1 duplicate avoided, 1 conflict
awaiting review, 0 external writes, and 0 clinical recommendations. Replay mode is
an offline reproducibility fallback and is explicitly not live inference.

This remains a synthetic research demonstration, not production EHR integration
or evidence of clinical deployment readiness. The hackathon scope deliberately
excludes a multi-agent redesign, hard-coded benchmark identifiers, Medplum, SMART
on FHIR, a FHIR server, and a general-purpose FHIR layer.
