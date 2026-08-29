# AI Legacy Last-Mile Agent

## Frozen reconciliation stress benchmark (v1.0.0)

Experiment 002 was useful but its apparent failures were overwhelmingly JSON
representation mismatches, while action selection and traceability were already
semantically strong. The separate `data/stress_benchmark/` suite therefore tests
the operational bottleneck: cross-source temporal history, explicit unit
equivalence, duplicates and partial duplicates, true conflicts, encounter
selection, provenance, dependent facts, ambiguity, and heterogeneous actions.
It does not alter or replace any Experiment 002 input, evaluator, or result.

The baseline makes exactly one general provider-neutral LLM request per case,
with no verifier, agent team, retry, or deterministic answer generator. Its
prompt receives a current record, incoming facts, target schema, allowed actions,
and task rules. Categories, expected updates, scoring labels, evaluator output,
and ground truth are excluded and covered by automated leakage tests.

```bash
python -m ai_legacy_last_mile.run_stress_baseline
python -m ai_legacy_last_mile.stress_evaluator results/stress_baseline_predictions.json
cat results/stress_baseline_metrics.json
```

See `data/stress_benchmark/README.md` for frozen normalization/scoring rules and
`freeze_manifest.json` for v1.0.0 integrity hashes and statistics.

Research prototype. Synthetic data only. No autonomous clinical decisions. No production EHR deployment. Human approval required for consequential write actions.

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
