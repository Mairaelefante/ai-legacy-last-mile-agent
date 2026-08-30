# AI Legacy Last-Mile Agent

Clinical information often arrives as fragmented updates that must be reconciled
against an evolving record. The operational question is not only what a source
says, but whether it is new information, a duplicate, a partial update, a
conflict, missing context, or a distinct later event.

The central engineering contribution is a boundary between **probabilistic
semantic reconciliation** and **deterministic operational write compilation**.
The model has freedom where semantic reasoning is ambiguous; deterministic code
constrains exact actions, identities, paths, provenance, temporal labels, and
approval policy where operational consequences matter. Every measured experiment
used the same base model: the improvement came from system architecture, not
fine-tuning or changed model weights.

Research prototype. Synthetic data only. No clinical recommendations. No
external EHR writes. Consequential simulated writes require separate human
approval. This is not evidence of clinical deployment readiness.

## Hot take

> More agentic behavior is not always better. Give the model freedom where
> reasoning is ambiguous, and constraints where actions have consequences.

> A low exact-match score can sometimes expose a benchmark problem rather than
> an intelligence problem. We rejected a formatter-driven win and redesigned the
> evaluation to measure reconciliation.

## Experiment history

### Early stateful baseline and benchmark redesign

The early stateful benchmark produced an apparently low exact-match score, but
failure analysis showed that most failures were representation and serialization
mismatches rather than genuine reconciliation failures. We rejected the tempting
formatter-only score improvement. Instead, we designed and froze the harder
20-case `stress-v1.0.0` benchmark to measure actual temporal, identity, duplicate,
conflict, missing-context, and provenance decisions. Its hashes and evaluation
contract are recorded in `data/stress_benchmark/freeze_manifest.json`.

### Frozen stress baseline

The same base model produced 33 proposed updates for 24 expected updates:

| Metric | Result |
|---|---:|
| Case-level semantic update-set accuracy | 0.0 |
| Semantic update accuracy | 0.0 |
| Action decision accuracy | 0.625 |
| Target record identity accuracy | 0.5833333333 |
| Encounter association accuracy | 0.7826086957 |
| Duplicate reconciliation decision accuracy | 0.0416666667 |
| Conflict classification accuracy | 1.0 |
| Missing-context detection recall | 1.0 |
| Extra update rate | 0.375 |
| Missing update rate | 0.0 |

The baseline understood conflicts and missing context, but decomposed actions and
used noncanonical operational representations. That failure analysis did not
justify adding more agents.

### Experiment 003 — structured planner and deterministic compiler

Experiment 003 introduced the final architectural boundary: one structured
`ReconciliationPlan` call decides fact groups, identity and temporal relationships,
and intended actions; deterministic Python compiles those decisions into the
canonical update contract. Human approval is execution-policy metadata, never a
fake clinical update.

| Metric | Experiment 003 |
|---|---:|
| Case-level semantic update-set accuracy | 0.35 |
| Semantic update accuracy | 0.4166666667 |
| Action decision accuracy | 0.9583333333 |
| Target record identity accuracy | 0.9166666667 |
| Encounter association accuracy | 0.8695652174 |
| Value accuracy | 0.875 |
| Provenance source attribution accuracy | 0.9166666667 |
| Temporal reconciliation accuracy | 0.8461538462 |
| Duplicate reconciliation decision accuracy | 0.9583333333 |
| Conflict classification accuracy | 1.0 |
| Missing-context detection recall | 1.0 |
| Extra update rate | 0.0 |
| Missing update rate | 0.0 |

### Experiment 004 — final reconciliation architecture

Experiment 004 retained the planner/compiler architecture and added narrow,
generic normalization and deterministic canonicalization for superficial identity
formatting, material temporal labels, missing-context payloads, and conflicts.

| Metric | Experiment 003 | Experiment 004 |
|---|---:|---:|
| Case-level semantic update-set accuracy | 0.35 | **0.65** |
| Semantic update accuracy | 0.4166666667 | **0.6666666667** |
| Action decision accuracy | **0.9583333333** | 0.875 |
| Target record identity accuracy | **0.9166666667** | 0.8333333333 |
| Encounter association accuracy | 0.8695652174 | **0.9130434783** |
| Value accuracy | 0.875 | **0.9166666667** |
| Provenance source attribution accuracy | 0.9166666667 | 0.9166666667 |
| Temporal reconciliation accuracy | **0.8461538462** | 0.7692307692 |
| Duplicate reconciliation decision accuracy | **0.9583333333** | 0.875 |
| Conflict classification accuracy | 1.0 | 1.0 |
| Missing-context detection recall | **1.0** | 0.75 |
| Extra update rate | 0.0 | 0.0 |
| Missing update rate | 0.0 | 0.0 |

The primary case-level result improved from 7/20 (35%) to 13/20 (65%), while
several component metrics regressed. The runs used fresh model calls: comparative
failure analysis found 7 cases exact in both, 6 failure-to-exact transitions, no
exact-to-failure transition, and 7 failures in both. Five of the six newly exact
cases were primarily deterministic representation/canonicalization improvements;
one was a genuine planner/reconciliation improvement. The observed component
regressions came from fresh-call planner variance, not the deterministic
Experiment 004 transformations.

Two benchmark targets also require stable identifiers unavailable in the agent's
inference input. We did not hard-code them or expose ground truth to inference to
inflate the score.

## Final synthetic FHIR live demo

The hackathon demo places the unchanged Experiment 004 architecture behind a
small standards-shaped adapter:

```text
Synthetic FHIR Bundle
  → deterministic Synthetic FHIR Validation and Adaptation Tool
  → LIVE Experiment 004 planner
  → unchanged deterministic Experiment 004 compiler
  → proposed FHIR-compatible change
  → separate simulated human approval
  → evolving in-memory synthetic Bundle
```

The deliberately narrow subset supports `Patient`, `Encounter`, `Observation`,
and `DiagnosticReport`. The deterministic tool enforces synthetic markers,
resolves local Patient/Encounter references, validates the supported subset, and
fails closed before a model call on invalid or unsupported data. It adapts data;
it does **not** make reconciliation decisions.

The live demo was successfully run locally with the same configured base model
and exactly one live planner call for each event:

| Event | Planner | Compiler and outcome |
|---|---|---|
| New sodium Observation | `NEW / DISTINCT_LATER` | `ADD`; POST Observation preview; simulated approval; applied only to the in-memory synthetic Bundle |
| Equivalent-unit creatinine | `EQUIVALENT_UNIT_DUPLICATE / SAME_MEASUREMENT` | `NO_OP`; no FHIR proposal; record unchanged |
| Same-accession right/left DiagnosticReport | `TRUE_CONFLICT / NOT_APPLICABLE` | `FLAG_CONFLICT`; review required; no clinical write; state unchanged |
| Later potassium Observation | `NEW / DISTINCT_LATER` | `ADD`; POST Observation preview; simulated approval; applied only to the in-memory synthetic Bundle |

Final live-demo summary: **2 observations added, 1 duplicate avoided, 1 conflict
awaiting review, 0 external writes, and 0 clinical recommendations**.

Live mode requires an API key and never silently falls back to replay:

```bash
export OPENAI_API_KEY='your-api-key'
export OPENAI_MODEL='gpt-5.6-sol'  # optional; this is the current default
run-fhir-demo --live
```

Replay is an offline reproducibility fallback using committed structured plan
fixtures. It still passes each plan through the actual Experiment 004 validation
and compiler, but it is **not live model inference**:

```bash
run-fhir-demo --replay
```

This demo is not production EHR integration or a claim of deployment readiness.

## Deliberate non-features and rejected ideas

- We rejected a formatter-only improvement after the early benchmark was found
  to measure representation mismatches more than reconciliation.
- We did not add a multi-agent architecture because failure analysis did not
  justify its complexity.
- We did not hard-code unavailable benchmark identifiers.
- We did not build production EHR integration, Medplum, SMART on FHIR, a FHIR
  server, or a general-purpose FHIR layer for the hackathon.

A Python 3.12 hackathon scaffold for testing whether AI-generated structured
information can be transferred reliably into heterogeneous legacy systems.
The project defines validated data contracts, wholly synthetic fixtures, a
deterministic evaluator, and an intentionally simple single-LLM baseline. It
includes no multi-agent workflow, LangGraph, UI, real EHR integration, or SMART
on FHIR integration.

## Project layout

```text
src/ai_legacy_last_mile/  Pydantic models, fixture loaders, and evaluator
data/                       Synthetic documents, target schemas, and ground truth
eval/                       Workspace for future prediction outputs
tests/                      Dataset and evaluator unit tests
```

## Setup

Python 3.12 is required. Create an isolated environment and install the package
with its test dependency:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Test

```bash
python -m pytest
```

## Reproduce the frozen stress evaluation

Evaluate the committed frozen-baseline predictions without making a model call:

```bash
python -m ai_legacy_last_mile.stress_evaluator \
  results/stress_baseline_predictions.json
```

To generate a new stress-baseline run first, configure the model and run the
existing one-call-per-case command. This overwrites the corresponding baseline
artifacts and is not required for the FHIR replay demo:

```bash
export OPENAI_API_KEY='your-api-key'
export OPENAI_MODEL='gpt-5.6-sol'
python -m ai_legacy_last_mile.run_stress_baseline
python -m ai_legacy_last_mile.stress_evaluator \
  results/stress_baseline_predictions.json
```

See `data/stress_benchmark/README.md` for the frozen equivalence rules and
`data/stress_benchmark/freeze_manifest.json` for integrity hashes.

## Dataset

`data/clinical_documents.json` contains ten fictional outpatient documents.
Names, dates, conditions, and measurements are generated solely for testing and
do not represent real people or encounters. Each document exposes normalized
`SourceFact` records.

`data/target_schemas.json` defines two invented EHR contracts. The same concepts
use deliberately different paths and nesting. `data/ground_truth_mappings.json`
stores the expected assignments outside evaluator code for every document and
both schemas.

## Run the single-agent baseline

This baseline makes exactly **one** OpenAI request for each document/schema pair.
Each request receives the complete clinical document, all normalized source
facts, and the complete target schema. It has no retries, verification pass,
tools, agent framework, semantic mapping rules, evaluator feedback, or access to
ground truth.

Set the two required environment variables (the application does not read a
`.env` file):

```bash
export OPENAI_API_KEY='your-api-key'
export OPENAI_MODEL='your-structured-output-capable-model'
```

Run all 20 document/schema cases:

```bash
python -m ai_legacy_last_mile.run_baseline \
  --documents data/clinical_documents.json \
  --schemas data/target_schemas.json \
  --output results/baseline_predictions.json
```

This writes:

- `results/baseline_predictions.json`: validated `MappingCase` predictions;
- `results/baseline_predictions.raw.json`: raw structured response text or error
  for every request;
- `results/baseline_predictions.failures.json`: malformed responses, missing
  mappings, invalid paths, and API failures. A failed case remains in predictions
  with no mappings so it is penalized during evaluation. There are no retries.

## Evaluate predictions separately

Only after generation finishes, run the existing deterministic evaluator. This
separation prevents expected mappings and metrics from leaking into the baseline:

```bash
python -m ai_legacy_last_mile.evaluator \
  results/baseline_predictions.json \
  --output results/baseline_metrics.json \
  --per-case-output results/baseline_per_case_metrics.json
```

The deterministic evaluator performs exact comparisons of source fact ID,
target field path, and JSON value, and reports precision, recall, and Jaccard
field-mapping accuracy. Aggregate and per-case metrics are saved by the command.
No performance number is claimed until a real API-backed run is completed.

## Milestone 3: stateful update benchmark

Experiment 001 remains the reproducible single-request field-mapping benchmark
described above. Milestone 3 adds a separate, more realistic evaluation
environment for a future Experiment 002; it does not make the old baseline solve
the new task and does not add a multi-agent implementation.

The stateful benchmark combines:

- 10 current fictional inpatient records in `data/patient_records.json`;
- 20 explicitly sourced incoming events in `data/incoming_events.json`;
- 40 stable patient/event/schema cases in `data/stateful_cases.json`;
- 52 expected traceable actions in `data/ground_truth_updates.json`;
- operational field extensions for the existing `ehr_alpha` and `ehr_beta`
  systems in `data/stateful_schema_extensions.json`.

The events cover clinical notes, explicit medication changes, imaging and
consultation requests, laboratory results, radiology reports, external
documents, duplicates, incompatible source statements, and information lacking
the context required for safe mapping. Actions are limited to `ADD`, `UPDATE`,
`NO_OP`, `FLAG_CONFLICT`, and `FLAG_MISSING_CONTEXT`. Consequential proposals and
flags require human review; the benchmark does not apply updates to a record.

Future predictions should be a JSON list of `ProposedUpdate` objects. Evaluate
them independently with:

```bash
python -m ai_legacy_last_mile.update_evaluator \
  results/update_predictions.json \
  --output results/update_metrics.json \
  --per-case-output results/update_per_case_metrics.json
```

The deterministic report includes exact update, action-type, target-path,
proposed-value, and source-traceability accuracy, plus conflict-detection and
missing-context detection recall. No Experiment 002 predictor is implemented yet.

### Stateful case identity and heterogeneous destinations

Every stateful case has an explicit `case_id`, `patient_id`, `event_id`, and
`target_schema_id`. The same 20 source events are evaluated once against each of
the two existing synthetic EHR systems. Their operational extensions deliberately
use different paths for equivalent concepts—for example, Alpha imaging requests
use `encounter.requests.radiology`, while Beta uses `chart.orders.imaging`.

The original `target_schemas.json` remains unchanged for Experiment 001
reproducibility. The extension fixture adds only the operational destinations
needed by the stateful task and remains keyed to those same schema IDs. A future
Experiment 002 predictor must receive the selected base schema and its stateful
extension as input; ground truth remains a separate evaluator-only fixture.

Ten destination-specific cases contain multiple expected actions (five source
events evaluated against both schemas). Single sources include explicitly
supported combinations such as a medication change plus a new medication and
imaging request, two investigations, a laboratory result plus supplied diary
text, a valid result plus a conflict, and a document plus a missing-context flag.

### Primary stateful metric

The primary metric is **case-level exact update set accuracy**: the proportion of
patient/event/schema cases where the complete multiset of predicted updates
equals the expected set. A case is correct only when no expected action is
missing, no extra action is proposed, and every action has the correct type,
target path, proposed value, and source-fact traceability. Action-level component
metrics remain available for diagnosis but are not the primary success measure.

## Experiment 002: single-LLM stateful update baseline

Experiment 002 measures the simplest fair baseline for the frozen stateful
benchmark: one patient/event/schema case produces exactly one general-purpose LLM
request and one structured `ProposedUpdate` set. Unlike Experiment 001, the input
includes current patient-record state and arriving information over time. Unlike
future experiments, it has no retry, critic, verifier, specialized agent, tool,
or evaluator feedback during generation.

Use the Python 3.12 setup described above, then export the same two required
environment variables:

```bash
export OPENAI_API_KEY='your-api-key'
export OPENAI_MODEL='your-structured-output-capable-model'
```

Generate all 40 cases with exactly one request per case:

```bash
python -m ai_legacy_last_mile.run_stateful_baseline \
  --records data/patient_records.json \
  --events data/incoming_events.json \
  --cases data/stateful_cases.json \
  --schemas data/target_schemas.json \
  --schema-extensions data/stateful_schema_extensions.json \
  --output results/stateful_baseline_predictions.json
```

Generation writes these artifacts before any evaluation is run:

- `results/stateful_baseline_predictions.json` — validated updates from
  successful cases;
- `results/stateful_baseline_raw.json` — one raw response or recorded error per
  case;
- `results/stateful_baseline_failures.json` — API and validation failures. A
  failed case contributes no predicted updates and is penalized later.

After generation is complete, run the frozen evaluator separately:

```bash
python -m ai_legacy_last_mile.update_evaluator \
  results/stateful_baseline_predictions.json \
  --output results/stateful_baseline_metrics.json \
  --per-case-output results/stateful_baseline_per_case_metrics.json
```

The model input contains only the current synthetic record, explicitly sourced
incoming event, case identity, base destination schema, matching operational
extension, allowed actions, output contract, and safety/task rules. It never
contains expected updates, ground truth, scores, other cases' answers, or hidden
answer-derived hints. All Experiment 002 results remain pending until a real API
run is performed.

## Safety and Scope

- **Synthetic data only:** all patient names, records, events, sources, and
  clinical content in this repository are fictional.
- This is a research/hackathon prototype, not a production-ready clinical system.
- It has no access to a production EHR and performs no real record updates.
- It must not perform autonomous diagnosis.
- It must not perform autonomous prescribing.
- It must not perform autonomous clinical decision-making.
- It may only organize explicit source information, map it, identify changes or
  conflicts, and propose traceable updates supported by that information.
- All proposed consequential changes require review and approval by an
  authorized human; a proposal is never an instruction to provide care.
- Deployment in a real healthcare environment would require institutional
  authorization, security and privacy review, regulatory and compliance
  assessment, and system-specific integration.
