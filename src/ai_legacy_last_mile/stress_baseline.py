"""One-call-per-case baseline for the isolated stress benchmark."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .llm import LLMClient

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "stress_benchmark"
ALLOWED_ACTIONS = ["ADD", "UPDATE", "NO_OP", "LINK", "FLAG_CONFLICT", "FLAG_MISSING_CONTEXT"]


class StressUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    action_type: str
    target_path: str | None = None
    record_id: str | None = None
    encounter_id: str | None = None
    value: Any = None
    timestamp: str | None = None
    provenance: dict[str, Any] | None = None
    source_fact_ids: list[str] = Field(default_factory=list)
    reconciliation_kind: str
    temporal_classification: str | None = None


class StressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updates: list[StressUpdate]


def build_prompt(case: dict[str, Any], record: dict[str, Any], event: dict[str, Any], schema: dict[str, Any]) -> str:
    """Exclude category metadata and every evaluation/ground-truth field."""
    payload={"case":{"case_id":case["case_id"],"patient_id":case["patient_id"],"event_id":case["event_id"],"target_schema_id":case["target_schema_id"]},"current_patient_record":record,"incoming_event":event,"target_schema":schema,"allowed_actions":ALLOWED_ACTIONS}
    rules="""Perform administrative record reconciliation only. Never diagnose or recommend treatment.
Return all and only supported updates. Preserve distinct observations by time, institution, encounter and provenance. Equivalent units or wording may describe duplicates. Same-event incompatible claims are conflicts; different-time observations are history, not conflicts. Use LINK for an existing item identified by a new external identity, UPDATE for meaningful new metadata, NO_OP for a represented duplicate, and FLAG_MISSING_CONTEXT rather than guessing. Integrate facts in the same event. Consequential writes require human approval. Return structured output only."""
    return rules+"\nCASE INPUT:\n"+json.dumps(payload,indent=2)


def run(client: LLMClient) -> tuple[list[dict[str,Any]],list[dict[str,Any]],list[dict[str,Any]]]:
    load=lambda name: json.loads((DATA/name).read_text()); cases=load("cases.json"); records={x["patient_id"]:x for x in load("patient_records.json")}; events={(x["patient_id"],x["event_id"]):x for x in load("incoming_events.json")}; schemas={x["id"]:x for x in load("target_schemas.json")}
    predictions=[]; raw=[]; failures=[]
    for case in cases:
        text=None
        try:
            completion=client.complete(build_prompt(case,records[case["patient_id"]],events[(case["patient_id"],case["event_id"])],schemas[case["target_schema_id"]]),StressResponse); text=completion.raw_text; response=StressResponse.model_validate(completion.parsed)
            valid_facts={x["id"] for x in events[(case["patient_id"],case["event_id"])]["facts"]}
            for update in response.updates:
                if update.case_id != case["case_id"] or update.action_type not in ALLOWED_ACTIONS or not set(update.source_fact_ids)<=valid_facts: raise ValueError("invalid case, action, or source identity")
                predictions.append(update.model_dump(mode="json"))
            raw.append({"case_id":case["case_id"],"response":text})
        except Exception as exc:
            failures.append({"case_id":case["case_id"],"error_type":type(exc).__name__,"message":str(exc)}); raw.append({"case_id":case["case_id"],"response":text,"error":str(exc)})
    return predictions,raw,failures
