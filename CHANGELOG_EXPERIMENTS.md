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

### Evaluation status

Implementation and local deterministic tests are complete. A new measured score
is pending a valid 20-case API run because this development environment has no
`OPENAI_API_KEY`. Until then, the frozen direct baseline remains the only result
and no improvement claim is made.

### Research interpretation

A low exact-match score can be a benchmark bug rather than an intelligence
failure. We rejected a formatter-driven win and redesigned evaluation around
semantic reconciliation. On the harder benchmark, the useful boundary is not
“add more agents”: the LLM is used for ambiguous reconciliation and deterministic
code enforces the write contract. Whether that boundary improves the primary
metric remains an empirical question for the pending run.

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

### Evaluation status

No Experiment 004 API run has been performed and no metric improvement is
claimed. The new behavior is covered by deterministic tests; a valid one-time
20-case run is still required to measure the hypothesis.
