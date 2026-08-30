"""Run the narrow live or offline-replay synthetic FHIR demonstration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .canonical_update_compiler_exp004 import compile_plan_exp004
from .fhir_demo import (
    ReplayPlanClient,
    apply_approved_proposal,
    canonical_update_to_fhir_proposal,
    event_to_internal_input,
    simulate_human_approval,
)
from .llm import LLMClient, OpenAIClient
from .reconciliation_planner_exp004 import plan_case_exp004

ROOT = Path(__file__).resolve().parents[2]
DEMO_DATA = ROOT / "data" / "fhir_demo"


def _load(name: str) -> Any:
    return json.loads((DEMO_DATA / name).read_text(encoding="utf-8"))


def _planner_line(plan: Any) -> str:
    return " + ".join(
        f"{item.identity_relationship.value} / {item.temporal_relationship.value}"
        for item in plan.items
    )


def _compiler_line(updates: list[Any]) -> str:
    return " + ".join(f"{update.action_type} {update.target_path}" for update in updates)


def run_demo(mode: str, live_client: LLMClient | None = None) -> dict[str, Any]:
    """Run four events and return the final in-memory state and summary."""
    if mode not in {"live", "replay"}:
        raise ValueError("mode must be 'live' or 'replay'")
    if mode == "live":
        print("MODE: LIVE MODEL INFERENCE")
        client = live_client
        if client is None:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise SystemExit("OPENAI_API_KEY is required for --live")
            client = OpenAIClient(api_key, os.environ.get("OPENAI_MODEL", "gpt-5.6-sol"))
    else:
        print("MODE: OFFLINE RECORDED-PLAN REPLAY")
        print("No model API will be called.")
        client = None

    print("Synthetic patient: patient-demo-001")
    print("External writes: disabled\n")
    bundle = _load("patient_bundle.json")
    events = _load("events.json")
    replay_plans = {plan["case_id"]: plan for plan in _load("replay_plans.json")}
    summary = {
        "observations_added": 0,
        "duplicates_avoided": 0,
        "conflicts_awaiting_review": 0,
        "external_writes_performed": 0,
        "clinical_recommendations_made": 0,
    }

    for number, event in enumerate(events, start=1):
        print(f"EVENT {number}/{len(events)}: {event['label']}")
        case, record, internal_event, schema = event_to_internal_input(event, bundle)
        print("TOOL: valid synthetic FHIR; local Patient/Encounter references resolved")
        event_client: LLMClient
        if mode == "live":
            assert client is not None
            event_client = client
        else:
            replay_plan = replay_plans.get(case["case_id"])
            if replay_plan is None:
                raise ValueError(f"missing replay plan for {case['case_id']}")
            event_client = ReplayPlanClient(replay_plan)
        try:
            plan, _ = plan_case_exp004(event_client, case, record, internal_event, schema)
        except Exception as exc:
            if mode == "live":
                print("LIVE INFERENCE FAILED — no clinical state changed for this event")
                print("Try: run-fhir-demo --replay")
            raise RuntimeError(f"planner failed for {case['case_id']}") from exc
        print(f"PLANNER: {_planner_line(plan)}")
        compiled = compile_plan_exp004(plan, record, internal_event, schema)
        if len(compiled.updates) != 1:
            raise RuntimeError("the minimal demo requires exactly one canonical update per event")
        print(f"COMPILER: {_compiler_line(compiled.updates)}")
        update = compiled.updates[0]
        proposal = canonical_update_to_fhir_proposal(update, event["resource"])
        decision = simulate_human_approval(proposal)

        if update.action_type == "ADD":
            print("FHIR PROPOSAL: POST Observation preview")
            print(f"REVIEW: {decision}")
            bundle = apply_approved_proposal(bundle, proposal, decision)
            summary["observations_added"] += 1
            print("STATE RESULT: applied to in-memory synthetic Bundle")
        elif update.action_type == "NO_OP":
            summary["duplicates_avoided"] += 1
            print("FHIR PROPOSAL: none (NO_OP)")
            print("STATE RESULT: in-memory synthetic Bundle unchanged")
        elif update.action_type == "FLAG_CONFLICT":
            summary["conflicts_awaiting_review"] += 1
            print(f"REVIEW: {decision}; no FHIR write proposal")
            print("STATE RESULT: in-memory synthetic Bundle unchanged")
        print()

    print("FINAL SYNTHETIC RECORD")
    print(f"observations added: {summary['observations_added']}")
    print(f"duplicates avoided: {summary['duplicates_avoided']}")
    print(f"conflicts awaiting review: {summary['conflicts_awaiting_review']}")
    print("external writes performed: 0")
    print("clinical recommendations made: 0")
    return {"bundle": bundle, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the synthetic FHIR reconciliation demo")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="make four live Experiment 004 planner calls")
    mode.add_argument("--replay", action="store_true", help="use committed recorded plan fixtures offline")
    args = parser.parse_args()
    run_demo("live" if args.live else "replay")


if __name__ == "__main__":
    main()
