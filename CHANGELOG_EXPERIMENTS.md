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
