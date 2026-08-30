# Experiment Changelog

## Experiment 001 --- Initial mapping baseline

Minimal synthetic document-to-schema mapping baseline. It established
repository and evaluator structure but did not represent evolving-state
reconciliation.

## Experiment 002 --- Stateful update baseline

Added current patient state, incoming sourced information and
heterogeneous destinations.

Failure analysis showed that most apparent failures were
representation/serialization mismatches.

**Rejected:** formatter-only optimization. It could improve exact match
without solving reconciliation. A harder semantic stress benchmark was
created and frozen instead.

## Frozen semantic stress benchmark --- v1.0.0

20 cases, 24 expected updates. Ground truth/evaluator feedback excluded
from inference.

Valid direct baseline: - predicted updates: 33 - case-level semantic
update-set accuracy: 0.000 - semantic update accuracy: 0.000 - action
decision accuracy: 0.625 - target identity accuracy: 0.5833333333 -
encounter association accuracy: 0.7826086957 - value accuracy: 0.000 -
provenance accuracy: 0.000 - temporal accuracy: 0.000 - duplicate
reconciliation accuracy: 0.0416666667 - conflict classification
accuracy: 1.000 - missing-context recall: 1.000 - extra update rate:
0.375 - missing update rate: 0.000

## Experiment 003 --- Structured Planner + Deterministic Compiler

**Hypothesis:** keep probabilistic freedom for semantic ambiguity while
constraining operational representation.

One structured LLM call per case produces the reconciliation plan;
deterministic Python compiles the canonical action. No multi-agent
system, second call, retry loop, evaluator feedback or ground-truth
access.

Valid result: - case-level semantic update-set accuracy: **0.350** -
semantic update accuracy: **0.4166666667** - action decision accuracy:
**0.9583333333** - target identity accuracy: **0.9166666667** -
encounter association accuracy: **0.8695652174** - value accuracy:
**0.875** - provenance accuracy: **0.9166666667** - temporal accuracy:
**0.8461538462** - duplicate reconciliation accuracy: **0.9583333333** -
conflict classification accuracy: **1.000** - missing-context recall:
**1.000** - extra update rate: **0.000** - missing update rate:
**0.000**

Predictions fell from 33 to exactly 24 for 24 expected updates.

## Experiment 004 --- Narrow generic canonicalization

Preserved Experiment 003 architecture and added narrow generic
normalization/canonicalization. No benchmark, evaluator or ground-truth
changes.

Valid result: - case-level semantic update-set accuracy: **0.650** -
semantic update accuracy: **0.6666666667** - action decision accuracy:
**0.875** - target identity accuracy: **0.8333333333** - encounter
association accuracy: **0.9130434783** - value accuracy:
**0.9166666667** - provenance accuracy: **0.9166666667** - temporal
accuracy: **0.7692307692** - duplicate reconciliation accuracy:
**0.875** - conflict classification accuracy: **1.000** -
missing-context recall: **0.750** - extra update rate: **0.000** -
missing update rate: **0.000**

Transition analysis: 7 exact→exact, 6 fail→exact, 0 exact→fail, 7
fail→fail.

Five of six newly exact cases were primarily deterministic
canonicalization improvements; one was a genuine planner improvement.
Component regressions were retained and read-only analysis attributed
the observed regressions to fresh-call planner variance rather than
deterministic Experiment 004 transformations.

Two benchmark targets contain identifiers unavailable in agent input.
They were deliberately not hard-coded.

**Decision:** keep Experiment 004 as final measured architecture; do not
create Experiment 005 to chase another fresh-call score.

## Final integration --- Synthetic FHIR demo

Not a new benchmark experiment.

``` text
Synthetic FHIR Bundle
→ deterministic validation/adaptation
→ live Experiment 004 planner
→ deterministic compiler
→ FHIR-compatible proposal
→ simulated human approval
→ evolving in-memory synthetic Bundle
```

Observed live run: 1. sodium → `NEW / DISTINCT_LATER` → `ADD` 2.
equivalent creatinine → `EQUIVALENT_UNIT_DUPLICATE / SAME_MEASUREMENT` →
`NO_OP` 3. conflicting report → `TRUE_CONFLICT / NOT_APPLICABLE` →
`FLAG_CONFLICT` 4. later potassium → `NEW / DISTINCT_LATER` → `ADD`

Summary: 2 observations added, 1 duplicate avoided, 1 conflict awaiting
review, 0 external writes, 0 clinical recommendations.

Live output is demonstration evidence, not a benchmark metric. Replay is
an offline reproducibility fallback and is not live inference.

## Rejected / removed directions

-   Formatter-only optimization.
-   Unjustified multi-agent complexity.
-   Hard-coded unavailable identifiers.
-   Experiment 005 score chasing.
-   Production EHR / Medplum / SMART-on-FHIR integration.
-   External FHIR server or general-purpose FHIR layer.

## Final principle

> More agentic behavior is not always better. Give the model freedom
> where reasoning is ambiguous, and constraints where actions have
> consequences.
