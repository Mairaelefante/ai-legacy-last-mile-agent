# Agent Trajectories

This document provides representative trajectories for the single agent used in the final system: the **Structured Reconciliation Planner**.

The project deliberately does **not** use a multi-agent architecture. The planner performs the probabilistic semantic reasoning; deterministic Python validates inputs and compiles the planner output into a restricted canonical action. Consequential simulated changes remain behind a separate human-approval checkpoint.

## Agent instructions

The final Experiment 004 planner is instructed to act as the reconciliation planning stage of a synthetic administrative EHR research prototype. It must not diagnose or recommend care and must **produce an explicit plan, not final EHR payloads**.

Its relevant rules include:

- group facts that jointly describe one identity, conflict, or update;
- match records and encounters only from supplied input;
- treat equivalent same-time measurements as duplicates;
- treat later measurements as new history rather than conflicts;
- classify conflicting claims about one same-time/external identity as `TRUE_CONFLICT`;
- use `MISSING_CONTEXT` when identity or encounter context is insufficient;
- return a structured plan only;
- never invent unavailable stable identifiers.

The planner can propose only the semantic intent. Deterministic code compiles that intent into the restricted action vocabulary used by the system.

## Tool boundary

The end-to-end FHIR demo uses the following sequence:

```text
Synthetic FHIR Bundle
        ↓
Deterministic FHIR Validation and Adaptation Tool
        ↓
Structured Reconciliation Planner (one live LLM call per event)
        ↓
Deterministic Canonical Compiler
        ↓
FHIR-compatible proposed change / no-change / review issue
        ↓
Separate simulated human approval
        ↓
Evolving in-memory synthetic Bundle
```

The validation tool checks the narrow supported FHIR subset, synthetic-data markers, local Patient/Encounter references, required fields, and resource consistency. It fails closed before inference on unsupported or inconsistent input. It does not make semantic reconciliation decisions.

The compiler is deterministic. It converts the structured planner decision into canonical actions such as `ADD`, `NO_OP`, or `FLAG_CONFLICT`. The model is therefore free where semantic reasoning is ambiguous but not where operational representation has consequences.

---

## Trajectory 1 — New sodium observation

**Incoming situation**

A synthetic sodium `Observation` arrives as new information for an existing patient/encounter.

**1. Tool response — validation/adaptation**

The FHIR validation tool accepts the synthetic resource, confirms that Patient/Encounter references resolve locally, and adapts the resource into the internal Experiment 004 case representation.

**2. Agent reasoning output**

Observed live classification:

```text
NEW / DISTINCT_LATER
```

The planner determines that the observation represents new clinical-record history rather than a duplicate or conflict.

**3. Deterministic compiler response**

```text
ADD
```

The compiler turns the plan into a canonical proposed addition.

**4. Human checkpoint**

The separate simulated review policy returns:

```text
APPROVED_FOR_SYNTHETIC_SIMULATION
```

**5. Final result**

The proposal is applied only to the copied, in-memory synthetic FHIR Bundle. No external EHR write occurs.

**Retry behavior:** none. The final architecture intentionally uses one planner call per case/event and no retry loop.

---

## Trajectory 2 — Equivalent-unit creatinine duplicate

**Incoming situation**

A creatinine measurement arrives in a representation equivalent to one already present in the record.

**1. Tool response — validation/adaptation**

The deterministic FHIR tool accepts the resource and exposes the incoming measurement together with the existing record state to the planner.

**2. Agent reasoning output**

Observed live classification:

```text
EQUIVALENT_UNIT_DUPLICATE / SAME_MEASUREMENT
```

The planner recognizes that the incoming value represents the same measurement rather than a new observation.

**3. Deterministic compiler response**

```text
NO_OP
```

No new record is constructed.

**4. Human checkpoint**

Because this is a no-change action, the separate simulated review policy returns:

```text
NOT_APPLICABLE
```

**5. Final result**

The duplicate is avoided and the synthetic Bundle remains unchanged.

**Retry behavior:** none.

**Why this case matters:** duplicate suppression was one of the major weaknesses of the direct baseline. On the frozen stress benchmark, duplicate-reconciliation accuracy improved from `0.0417` in the baseline to `0.9583` in Experiment 003; Experiment 004 retained a high value of `0.875` while preserving a zero extra-update rate.

---

## Trajectory 3 — True conflict requiring review

**Incoming situation**

A synthetic `DiagnosticReport` conflicts with information that refers to the same identity/context.

**1. Tool response — validation/adaptation**

The deterministic FHIR tool validates the incoming resource and passes the current record plus incoming event to the planner.

**2. Agent reasoning output**

Observed live classification:

```text
TRUE_CONFLICT / NOT_APPLICABLE
```

The planner does not choose one conflicting value and does not convert the disagreement into an autonomous write.

**3. Deterministic compiler response**

```text
FLAG_CONFLICT
```

The outbound FHIR mapping produces a review issue with status:

```text
REVIEW_REQUIRED
```

and no FHIR write entry.

**4. Human checkpoint**

The separate simulated policy returns:

```text
REVIEW_REQUIRED
```

**5. Final result**

The conflict is routed for human review. No change is applied to the synthetic Bundle.

**Retry behavior:** none. The safety behavior is escalation, not repeated model calls.

**Why this case matters:** it demonstrates the project’s core boundary. The agent can identify semantic ambiguity, but consequential resolution is not delegated to the model.

---

## Trajectory 4 — Later potassium observation

**Incoming situation**

A potassium observation arrives at a later time than the existing measurement.

**1. Tool response — validation/adaptation**

The FHIR tool validates the resource and preserves the encounter and timestamp context for the planner.

**2. Agent reasoning output**

Observed live classification:

```text
NEW / DISTINCT_LATER
```

The planner treats the later measurement as new history rather than incorrectly collapsing it into a duplicate or conflict.

**3. Deterministic compiler response**

```text
ADD
```

**4. Human checkpoint**

```text
APPROVED_FOR_SYNTHETIC_SIMULATION
```

**5. Final result**

The new observation is added only to the evolving in-memory synthetic Bundle.

**Retry behavior:** none.

---

## Live trajectory summary

The observed local live demo produced:

```text
observations added: 2
duplicates avoided: 1
conflicts awaiting review: 1
external writes performed: 0
clinical recommendations made: 0
```

This is demonstration evidence, not a benchmark metric and not a claim of perfect accuracy.

---

## Challenging benchmark case — same-time potassium conflict

A representative hard case from the frozen semantic stress benchmark is:

```text
case_id: stress-p05:stress-e05:ehr_alpha
source facts: f5a, f5b
expected semantic situation: two conflicting potassium values for the same measurement context
```

Experiment 004 compiled the planner output to:

```text
action_type: FLAG_CONFLICT
target_path: workflow.review
encounter_id: enc-new
values: [3.1, 4.8] mmol/L
reconciliation_kind: true_conflict
temporal_classification: same_measurement
```

This case is useful because the safe outcome is not to select a value. The correct behavior is to preserve the contradiction and route it to review.

It also illustrates why the architecture separates reasoning from execution: the planner identifies the semantic relationship, while deterministic code controls the canonical review action.

---

## Feedback and iteration history

The trajectories above are the result of several measured iterations:

1. The direct baseline allowed one general-purpose LLM call to reason and construct updates. On the frozen stress benchmark it produced **33 predicted updates for 24 expected updates**, with `0.000` case-level semantic update-set accuracy and a `0.375` extra-update rate.
2. Failure analysis of an earlier stateful benchmark showed that many apparent failures were representation/serialization mismatches. A formatter-only improvement was deliberately rejected because it could raise exact match without improving reconciliation.
3. Experiment 003 introduced the Structured Planner + Deterministic Compiler boundary. Case-level exact semantic accuracy rose to `0.350`, and predicted updates fell to exactly `24/24`, eliminating extra updates.
4. Experiment 004 kept the same architecture and added only narrow generic canonicalization. Case-level exact semantic accuracy rose to `0.650` with a `0.000` extra-update rate.
5. Regressions were retained rather than hidden: missing-context recall fell from `1.000` in Experiment 003 to `0.750` in Experiment 004, and read-only analysis attributed observed component regressions to fresh-call planner variance rather than the deterministic transformations.
6. Experiment 005 score-chasing, unjustified multi-agent complexity, hard-coded unavailable identifiers, and production EHR integration were deliberately rejected.

## Human checkpoints and retries

The final system has **no automatic retry loop** and no second model call. This is intentional and is part of the measured architecture rather than an omitted feature.

Human control is represented separately from the planner:

- `ADD` proposals can be approved only for synthetic in-memory simulation;
- `NO_OP` requires no human write decision;
- `FLAG_CONFLICT` / `FLAG_MISSING_CONTEXT` are routed to review;
- no external EHR write is implemented.

This keeps the final trajectory auditable:

```text
agent instruction
→ structured semantic decision
→ deterministic tool/compiler response
→ explicit human checkpoint where consequential
→ bounded synthetic outcome
```

## Reproducibility

Live trajectory:

```bash
python -m ai_legacy_last_mile.run_fhir_demo --live
```

Offline deterministic replay of the committed planner fixtures:

```bash
python -m ai_legacy_last_mile.run_fhir_demo --replay
```

The replay mode is a reproducibility fallback and does not perform live model inference.
