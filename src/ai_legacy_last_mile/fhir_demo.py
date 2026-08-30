"""Narrow deterministic FHIR tool and safety gate for the synthetic demo."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel

from .llm import LLMCompletion
from .stress_baseline import StressUpdate

SUPPORTED_RESOURCES = {"Patient", "Encounter", "Observation", "DiagnosticReport"}
SYNTHETIC_TAG_SYSTEM = "https://example.invalid/tags"
SYNTHETIC_TAG_CODE = "synthetic-demo"
DEMO_SCHEMA = {
    "id": "fhir_demo",
    "fields": [
        "encounters[].results[]",
        "encounters[].documents[]",
        "workflow.review",
    ],
}


class FhirDemoValidationError(ValueError):
    """The deterministic demo tool rejected unsupported or inconsistent input."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FhirDemoValidationError(message)


def _has_synthetic_marker(resource: dict[str, Any]) -> bool:
    tags = resource.get("meta", {}).get("tag", [])
    return any(
        tag.get("system") == SYNTHETIC_TAG_SYSTEM and tag.get("code") == SYNTHETIC_TAG_CODE
        for tag in tags
        if isinstance(tag, dict)
    )


def _resource_key(resource: dict[str, Any]) -> str:
    resource_type = resource.get("resourceType")
    resource_id = resource.get("id")
    _require(resource_type in SUPPORTED_RESOURCES, f"unsupported FHIR resource: {resource_type!r}")
    _require(isinstance(resource_id, str) and bool(resource_id), "FHIR resource id is required")
    _require(_has_synthetic_marker(resource), f"synthetic marker missing on {resource_type}/{resource_id}")
    return f"{resource_type}/{resource_id}"


def _local_reference(value: Any, expected_type: str) -> str:
    _require(isinstance(value, str), f"{expected_type} reference is required")
    prefix = f"{expected_type}/"
    _require(value.startswith(prefix) and value.count("/") == 1, f"only local {prefix} references are supported")
    resource_id = value[len(prefix) :]
    _require(bool(resource_id), f"empty {expected_type} reference")
    return value


def _reference(resource: dict[str, Any], field: str, expected_type: str) -> str:
    container = resource.get(field)
    _require(isinstance(container, dict), f"{resource['resourceType']}.{field} is required")
    return _local_reference(container.get("reference"), expected_type)


def _identifier(resource: dict[str, Any], *, required: bool) -> str | None:
    identifiers = resource.get("identifier", [])
    _require(isinstance(identifiers, list), "identifier must be a list")
    values = [item.get("value") for item in identifiers if isinstance(item, dict) and item.get("value")]
    _require(len(values) <= 1, "the demo supports at most one stable identifier")
    if required:
        _require(len(values) == 1, f"{resource['resourceType']} stable identifier is required")
    return values[0] if values else None


def _validate_observation(resource: dict[str, Any]) -> None:
    _require(isinstance(resource.get("status"), str), "Observation.status is required")
    _require(isinstance(resource.get("code", {}).get("text"), str), "Observation.code.text is required")
    quantity = resource.get("valueQuantity")
    _require(isinstance(quantity, dict), "Observation.valueQuantity is required")
    _require(isinstance(quantity.get("value"), (int, float)), "Observation.valueQuantity.value must be numeric")
    _require(isinstance(quantity.get("unit"), str) and bool(quantity["unit"]), "Observation.valueQuantity.unit is required")
    _require(isinstance(resource.get("effectiveDateTime"), str), "Observation.effectiveDateTime is required")
    _identifier(resource, required=False)


def _validate_report(resource: dict[str, Any]) -> None:
    _require(isinstance(resource.get("status"), str), "DiagnosticReport.status is required")
    _require(isinstance(resource.get("code", {}).get("text"), str), "DiagnosticReport.code.text is required")
    _identifier(resource, required=True)


def validate_bundle(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate the tiny supported FHIR subset and return its local resource index."""
    _require(bundle.get("resourceType") == "Bundle", "FHIR Bundle is required")
    _require(bundle.get("type") == "collection", "only a collection Bundle is supported")
    _require(_has_synthetic_marker(bundle), "synthetic marker missing on Bundle")
    entries = bundle.get("entry")
    _require(isinstance(entries, list) and bool(entries), "Bundle.entry must be non-empty")
    index: dict[str, dict[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, dict) and isinstance(entry.get("resource"), dict), "Bundle entry resource is required")
        resource = entry["resource"]
        key = _resource_key(resource)
        _require(key not in index, f"duplicate FHIR identity: {key}")
        _require(entry.get("fullUrl") in {None, key}, f"Bundle fullUrl must be the local identity {key}")
        index[key] = resource

    patients = [key for key in index if key.startswith("Patient/")]
    _require(len(patients) == 1, "the demo requires exactly one Patient")
    patient_ref = patients[0]
    encounters = {key for key in index if key.startswith("Encounter/")}
    _require(bool(encounters), "the demo requires at least one Encounter")

    for key, resource in index.items():
        resource_type = resource["resourceType"]
        if resource_type == "Patient":
            continue
        subject_ref = _reference(resource, "subject", "Patient")
        _require(subject_ref == patient_ref, f"cross-patient reference on {key}")
        if resource_type == "Encounter":
            _require(isinstance(resource.get("status"), str), "Encounter.status is required")
            continue
        encounter_ref = _reference(resource, "encounter", "Encounter")
        _require(encounter_ref in encounters, f"unresolved Encounter reference on {key}")
        if resource_type == "Observation":
            _validate_observation(resource)
        elif resource_type == "DiagnosticReport":
            _validate_report(resource)
    return index


def validate_incoming_resource(
    resource: dict[str, Any], index: dict[str, dict[str, Any]]
) -> None:
    """Validate one incoming clinical resource against local Patient/Encounter state."""
    _resource_key(resource)
    _require(resource["resourceType"] in {"Observation", "DiagnosticReport"}, "incoming resource must be Observation or DiagnosticReport")
    patient_ref = _reference(resource, "subject", "Patient")
    encounter_ref = _reference(resource, "encounter", "Encounter")
    _require(patient_ref in index, "unresolved incoming Patient reference")
    _require(encounter_ref in index, "unresolved incoming Encounter reference")
    if resource["resourceType"] == "Observation":
        _validate_observation(resource)
    else:
        _validate_report(resource)


def _observation_fields(resource: dict[str, Any]) -> dict[str, Any]:
    quantity = resource["valueQuantity"]
    return {
        "test_name": resource["code"]["text"],
        "value": str(quantity["value"]),
        "unit": quantity["unit"],
        "timestamp": resource["effectiveDateTime"],
    }


def bundle_to_internal_record(bundle: dict[str, Any]) -> dict[str, Any]:
    """Adapt a validated synthetic Bundle into the existing record representation."""
    index = validate_bundle(bundle)
    patient_id = next(key.split("/", 1)[1] for key in index if key.startswith("Patient/"))
    encounter_resources = [resource for resource in index.values() if resource["resourceType"] == "Encounter"]
    active = next((resource for resource in encounter_resources if resource["status"] == "in-progress"), None)
    _require(active is not None, "one in-progress Encounter is required")
    encounters: dict[str, dict[str, Any]] = {
        resource["id"]: {"id": resource["id"], "results": [], "documents": []}
        for resource in encounter_resources
    }
    for resource in index.values():
        if resource["resourceType"] not in {"Observation", "DiagnosticReport"}:
            continue
        encounter_id = resource["encounter"]["reference"].split("/", 1)[1]
        if resource["resourceType"] == "Observation":
            value = {"id": resource["id"], **_observation_fields(resource)}
            external_id = _identifier(resource, required=False)
            if external_id:
                value["external_id"] = external_id
            encounters[encounter_id]["results"].append(value)
        else:
            encounters[encounter_id]["documents"].append(
                {
                    "id": resource["id"],
                    "accession": _identifier(resource, required=True),
                    "title": resource["code"]["text"],
                }
            )
    return {
        "patient_id": patient_id,
        "synthetic": True,
        "active_encounter_id": active["id"],
        "encounters": list(encounters.values()),
    }


def event_to_internal_input(
    event: dict[str, Any], bundle: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Run the deterministic tool and build Experiment 004's four input objects."""
    index = validate_bundle(bundle)
    resource = event.get("resource")
    _require(isinstance(event.get("event_id"), str), "event_id is required")
    _require(isinstance(event.get("source"), str), "synthetic event source is required")
    _require(isinstance(resource, dict), "incoming event resource is required")
    validate_incoming_resource(resource, index)
    record = bundle_to_internal_record(bundle)
    encounter_id = resource["encounter"]["reference"].split("/", 1)[1]
    if resource["resourceType"] == "Observation":
        fact = {
            "id": resource["id"],
            "kind": "result",
            **_observation_fields(resource),
            "institution": event["source"],
            "encounter_id": encounter_id,
        }
        external_id = _identifier(resource, required=False)
        if external_id:
            fact["external_id"] = external_id
    else:
        fact = {
            "id": resource["id"],
            "kind": "document",
            "accession": _identifier(resource, required=True),
            "title": resource["code"]["text"],
            "institution": event["source"],
            "encounter_id": encounter_id,
        }
    internal_event = {
        "patient_id": record["patient_id"],
        "event_id": event["event_id"],
        "synthetic": True,
        "facts": [fact],
    }
    case = {
        "case_id": f"{record['patient_id']}:{event['event_id']}:fhir_demo",
        "patient_id": record["patient_id"],
        "event_id": event["event_id"],
        "target_schema_id": "fhir_demo",
    }
    return case, record, internal_event, deepcopy(DEMO_SCHEMA)


def canonical_update_to_fhir_proposal(
    update: StressUpdate, incoming_resource: dict[str, Any]
) -> dict[str, Any]:
    """Map the three demo actions to a FHIR preview, no-change, or review issue."""
    base = {
        "proposal_id": f"{update.case_id}:{update.source_fact_ids[0]}",
        "canonical_action": update.action_type,
        "reconciliation_kind": update.reconciliation_kind,
        "source_fact_ids": list(update.source_fact_ids),
    }
    if update.action_type == "ADD":
        _require(incoming_resource.get("resourceType") == "Observation", "the demo mapper only supports ADD Observation")
        resource = deepcopy(incoming_resource)
        resource["id"] = update.record_id
        return base | {
            "status": "PROPOSED",
            "fhir_entry": {
                "resource": resource,
                "request": {"method": "POST", "url": "Observation"},
            },
            "issue": None,
        }
    if update.action_type == "NO_OP":
        return base | {"status": "NO_CHANGE", "fhir_entry": None, "issue": None}
    if update.action_type == "FLAG_CONFLICT":
        return base | {
            "status": "REVIEW_REQUIRED",
            "fhir_entry": None,
            "issue": {"kind": "conflict", "details": update.value},
        }
    raise FhirDemoValidationError(f"unsupported demo outbound action: {update.action_type}")


def simulate_human_approval(proposal: dict[str, Any]) -> str:
    """Return a separate, deterministic review decision for the synthetic demo."""
    action = proposal["canonical_action"]
    if action == "ADD":
        return "APPROVED_FOR_SYNTHETIC_SIMULATION"
    if action == "NO_OP":
        return "NOT_APPLICABLE"
    if action in {"FLAG_CONFLICT", "FLAG_MISSING_CONTEXT"}:
        return "REVIEW_REQUIRED"
    return "REVIEW_REQUIRED"


def apply_approved_proposal(
    bundle: dict[str, Any], proposal: dict[str, Any], decision: str
) -> dict[str, Any]:
    """Apply only an approved POST preview to a copied, in-memory synthetic Bundle."""
    if decision != "APPROVED_FOR_SYNTHETIC_SIMULATION":
        raise FhirDemoValidationError("proposal is not approved for synthetic simulation")
    if proposal.get("canonical_action") != "ADD" or not proposal.get("fhir_entry"):
        raise FhirDemoValidationError("only approved ADD proposals can change demo state")
    request = proposal["fhir_entry"].get("request", {})
    if request != {"method": "POST", "url": "Observation"}:
        raise FhirDemoValidationError("unsupported in-memory FHIR operation")
    updated = deepcopy(bundle)
    resource = deepcopy(proposal["fhir_entry"]["resource"])
    key = _resource_key(resource)
    existing = validate_bundle(updated)
    _require(key not in existing, f"resource already exists: {key}")
    updated["entry"].append({"fullUrl": key, "resource": resource})
    validate_bundle(updated)
    return updated


class ReplayPlanClient:
    """Fixture-backed LLMClient used only for explicit offline replay mode."""

    def __init__(self, plan: dict[str, Any]) -> None:
        self._plan = plan
        self.calls = 0

    def complete(self, prompt: str, response_model: type[BaseModel]) -> LLMCompletion:
        self.calls += 1
        parsed = response_model.model_validate(self._plan)
        return LLMCompletion(
            parsed=parsed,
            raw_text=f"offline replay fixture: {self._plan['case_id']}",
        )
