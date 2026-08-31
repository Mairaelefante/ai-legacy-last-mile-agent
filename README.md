# AI Legacy Last-Mile Agent

Research prototype for **agentic clinical record reconciliation**:
deciding how fragmented incoming clinical information should be
reconciled against an evolving record before any operational write is
allowed.

**Intended users:** clinical documentation and health-IT integration
teams responsible for reconciling incoming structured clinical
information into an EHR. The prototype targets the repetitive
reconciliation step before a consequential write, while keeping human
review separate from model reasoning.

**Safety scope:** synthetic data only; no clinical recommendations; no
external EHR writes; no production deployment.

## Problem

Incoming clinical information is not only an extraction problem. A
system must determine whether a new fact is new information, a
duplicate, an equivalent measurement in different units, a partial
update, a true conflict, missing required context, or a distinct later
event.

## Core contribution

**Probabilistic semantic reconciliation → deterministic operational
write compilation.**

The language model reasons about what incoming information means
relative to the current record. Deterministic Python controls exactly
how that reasoning can become an operational update. The measured
experiments use the same foundation model; the improvement comes from
the surrounding architecture, not fine-tuning.

> More agentic behavior is not always better. Give the model freedom
> where reasoning is ambiguous, and constraints where actions have
> consequences.

## Architecture

``` text
current record + incoming information + target schema
                         ↓
          Structured Reconciliation Planner
               one LLM call per case
                         ↓
         Deterministic Canonical Compiler
                         ↓
              canonical proposed action
                         ↓
               separate evaluation
```

The final demo adds a narrow FHIR boundary:

``` text
Synthetic FHIR Bundle
        ↓
Synthetic FHIR Validation and Adaptation Tool
        ↓
Live Experiment 004 planner
        ↓
Deterministic compiler
        ↓
FHIR-compatible proposed change
        ↓
Separate simulated human approval
        ↓
Evolving in-memory synthetic Bundle
```

Representative end-to-end traces, including planner instructions, tool
responses, compiler actions, the human checkpoint, and a challenging
conflict case, are documented in
[`AGENT_TRAJECTORIES.md`](AGENT_TRAJECTORIES.md).

## Setup and tests

Python 3.12 is required.

``` bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

If the editable package is not installed, run tests with `src` on
`PYTHONPATH`.

## Benchmark-design lesson

An earlier stateful benchmark produced a low exact-match score, but
failure analysis showed that most failures were
representation/serialization mismatches. A formatter-only fix could
therefore have created an attractive score increase without solving the
real reconciliation problem.

That direction was rejected. A separate harder semantic stress benchmark
was created and frozen before the later experiments.

> A low exact-match score can sometimes expose a benchmark problem
> rather than an intelligence problem. We rejected a formatter-driven
> win and redesigned the evaluation to measure reconciliation.

The earlier Experiment 002 material remains in repository history; the
final measured comparison uses the frozen stress benchmark below.

## Frozen reconciliation stress benchmark --- v1.0.0

20 cases, 24 expected updates. It tests semantic and partial duplicates,
unit equivalence, temporal history, provenance, encounter
disambiguation, true conflicts, missing context, dependent facts, and
heterogeneous actions. Ground truth and evaluator feedback are excluded
from inference.

### Direct stress baseline

One general-purpose LLM call per case; no verifier, agent team, retry
loop, deterministic answer generator, or evaluator feedback.

The baseline produced **33 predicted updates for 24 expected updates**.

  Metric                                      Baseline
  ----------------------------------------- ----------
  Case-level semantic update-set accuracy        0.000
  Semantic update accuracy                       0.000
  Action decision accuracy                       0.625
  Target record identity accuracy                0.583
  Encounter association accuracy                 0.783
  Value accuracy                                 0.000
  Provenance attribution accuracy                0.000
  Temporal reconciliation accuracy               0.000
  Duplicate reconciliation accuracy              0.042
  Conflict classification accuracy               1.000
  Missing-context detection recall               1.000
  Extra update rate                              0.375
  Missing update rate                            0.000

``` bash
python -m ai_legacy_last_mile.run_stress_baseline
```

## Experiment 003 --- Structured Planner + Deterministic Compiler

Experiment 003 introduced the main architectural change. One structured
LLM planning call returns identity/temporal relations, intended action,
evidence, matched record/encounter information, and source facts.
Deterministic Python constructs canonical paths, values, provenance and
labels, suppresses duplicate actions, and keeps approval policy separate
from clinical updates.

  Metric                                      Baseline    Exp. 003
  ----------------------------------------- ---------- -----------
  Case-level semantic update-set accuracy        0.000   **0.350**
  Semantic update accuracy                       0.000   **0.417**
  Action decision accuracy                       0.625   **0.958**
  Target record identity accuracy                0.583   **0.917**
  Encounter association accuracy                 0.783   **0.870**
  Value accuracy                                 0.000   **0.875**
  Provenance attribution accuracy                0.000   **0.917**
  Temporal reconciliation accuracy               0.000   **0.846**
  Duplicate reconciliation accuracy              0.042   **0.958**
  Conflict classification accuracy               1.000       1.000
  Missing-context detection recall               1.000       1.000
  Extra update rate                              0.375   **0.000**
  Missing update rate                            0.000       0.000

The system moved from **33 predictions for 24 expected** to **24
predictions for 24 expected**, reducing extra-update rate from **37.5%
to 0%**.

``` bash
python -m ai_legacy_last_mile.run_reconciliation_agent
```

## Experiment 004 --- Narrow canonicalization hardening

Experiment 004 preserves the same planner/compiler architecture and adds
only narrow generic normalization and canonicalization. It does not add
a second model call, retrieval, multi-agent orchestration, case-specific
rules, or ground-truth access.

  Metric                                       Exp. 003    Exp. 004
  ----------------------------------------- ----------- -----------
  Case-level semantic update-set accuracy         0.350   **0.650**
  Semantic update accuracy                        0.417   **0.667**
  Action decision accuracy                    **0.958**       0.875
  Target record identity accuracy             **0.917**       0.833
  Encounter association accuracy                  0.870   **0.913**
  Value accuracy                                  0.875   **0.917**
  Provenance attribution accuracy                 0.917       0.917
  Temporal reconciliation accuracy            **0.846**       0.769
  Duplicate reconciliation accuracy           **0.958**       0.875
  Conflict classification accuracy                1.000       1.000
  Missing-context detection recall            **1.000**       0.750
  Extra update rate                               0.000       0.000
  Missing update rate                             0.000       0.000

Primary case-level accuracy improved from **35% to 65%**. Transition
analysis: 7 exact→exact, 6 fail→exact, 0 exact→fail, 7 fail→fail. Five
of six newly exact cases were primarily deterministic
representation/canonicalization improvements; one was a genuine planner
improvement.

The regressions are intentionally reported. Read-only failure analysis
attributed observed component regressions to fresh-call planner variance
rather than the deterministic Experiment 004 transformations.

Two benchmark targets contain identifiers unavailable in agent input.
They were deliberately **not hard-coded**, and ground truth was never
exposed to inference.

``` bash
python -m ai_legacy_last_mile.run_reconciliation_agent_exp004
```

## End-to-end synthetic FHIR demo

Supported subset: `Patient`, `Encounter`, `Observation`,
`DiagnosticReport`.

The deterministic FHIR tool validates synthetic markers and local
Patient/Encounter references and fails closed on invalid or unsupported
input before inference. It does not make semantic reconciliation
decisions.

### Live mode

``` bash
python -m ai_legacy_last_mile.run_fhir_demo --live
```

Observed local live trajectory:

1.  New sodium Observation → `NEW / DISTINCT_LATER` → `ADD`.
2.  Equivalent-unit creatinine →
    `EQUIVALENT_UNIT_DUPLICATE / SAME_MEASUREMENT` → `NO_OP`.
3.  Conflicting DiagnosticReport → `TRUE_CONFLICT / NOT_APPLICABLE` →
    `FLAG_CONFLICT`.
4.  Later potassium Observation → `NEW / DISTINCT_LATER` → `ADD`.

Observed summary:

``` text
observations added: 2
duplicates avoided: 1
conflicts awaiting review: 1
external writes performed: 0
clinical recommendations made: 0
```

This live trajectory is demonstration evidence, **not a benchmark
metric** and not a claim of 100% accuracy.

### Replay mode

``` bash
python -m ai_legacy_last_mile.run_fhir_demo --replay
```

Replay uses committed structured planner fixtures and makes no live
model inference. It is an offline reproducibility fallback.

## Deliberately rejected directions

-   Formatter-only optimization after discovering the earlier benchmark
    over-measured representation mismatch.
-   Multi-agent complexity without evidence that it addressed measured
    failures.
-   Hard-coded identifiers unavailable to the agent.
-   Experiment 005 score chasing.
-   Production EHR integration, Medplum, SMART on FHIR, or an external
    FHIR server.
-   General-purpose FHIR support.

## Safety and scope

-   Synthetic data only; no real patient information.
-   No autonomous diagnosis, prescribing, or clinical decision-making.
-   No clinical recommendations.
-   No external EHR writes.
-   Consequential simulated changes pass through a separate approval
    gate.
-   The live demo mutates only an in-memory synthetic Bundle.
-   Real deployment would require institution-specific interoperability,
    authentication/authorization, privacy/security controls,
    auditability, regulatory/compliance review, clinical validation, and
    production human-review workflows.

## Main takeaway

The contribution is not a smarter model. It is a safer and more testable
boundary between **probabilistic semantic reasoning** and
**consequential operational execution**.
