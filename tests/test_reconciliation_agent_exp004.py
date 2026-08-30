from ai_legacy_last_mile.canonical_update_compiler_exp004 import compile_plan_exp004
from ai_legacy_last_mile.reconciliation_models import (
    CanonicalAction,
    EntityType,
    IdentityRelationship,
    PlanItem,
    ReconciliationPlan,
    TemporalRelationship,
)
from ai_legacy_last_mile.reconciliation_planner_exp004 import (
    build_reconciliation_prompt_exp004,
    normalize_superficial_duplicates,
)
from pathlib import Path
import inspect

from ai_legacy_last_mile.run_reconciliation_agent_exp004 import run_experiment_exp004


def _item(
    relationship: IdentityRelationship,
    action: CanonicalAction,
    *,
    entity: EntityType = EntityType.RESULT,
    record_id: str | None = "existing-1",
    temporal: TemporalRelationship = TemporalRelationship.NOT_APPLICABLE,
) -> PlanItem:
    return PlanItem(
        source_fact_ids=["fact-1"],
        entity_type=entity,
        matched_record_id=record_id,
        matched_encounter_id="encounter-1",
        proposed_record_id="new-1" if relationship is IdentityRelationship.NEW else None,
        identity_relationship=relationship,
        temporal_relationship=temporal,
        new_write_needed=action is not CanonicalAction.NO_OP,
        intended_action=action,
        target_collection="collection",
        provenance_fact_ids=["fact-1"],
        reason="source context is incomplete",
        evidence=["fixture"],
        human_approval_required=True,
    )


def _compile(item: PlanItem, fact: dict, existing: dict | None = None):
    collection = {
        EntityType.RESULT: "results",
        EntityType.REQUEST: "requests",
        EntityType.DOCUMENT: "documents",
    }[item.entity_type]
    record = {
        "active_encounter_id": "encounter-1",
        "encounters": [{"id": "encounter-1", collection: [existing] if existing else []}],
    }
    event = {"facts": [fact]}
    schema = {
        "fields": [
            "encounters[].results[]",
            "encounters[].requests[]",
            "encounters[].documents[]",
            "workflow.review",
        ]
    }
    plan = ReconciliationPlan(case_id="generic-case", items=[item], summary="fixture")
    return compile_plan_exp004(plan, record, event, schema).updates[0]


def test_document_formatting_only_is_semantic_duplicate_not_partial() -> None:
    item = _item(
        IdentityRelationship.PARTIAL_DUPLICATE,
        CanonicalAction.UPDATE,
        entity=EntityType.DOCUMENT,
    )
    plan = ReconciliationPlan(case_id="generic-case", items=[item], summary="fixture")
    record = {"encounters": [{"documents": [{"id": "existing-1", "accession": "A-1", "title": "Discharge Summary"}]}]}
    event = {"facts": [{"id": "fact-1", "kind": "document", "accession": "A-1", "title": "  discharge   SUMMARY ", "institution": "X"}]}
    normalized = normalize_superficial_duplicates(plan, record, event)
    assert normalized.items[0].identity_relationship is IdentityRelationship.SEMANTIC_DUPLICATE
    assert normalized.items[0].intended_action is CanonicalAction.NO_OP


def test_normalization_guidance_is_narrow_and_explicit() -> None:
    prompt = build_reconciliation_prompt_exp004(
        {"case_id": "generic", "patient_id": "p", "event_id": "e", "target_schema_id": "s"},
        {},
        {"facts": []},
        {"fields": []},
    )
    assert "case, leading/trailing whitespace, and repeated internal whitespace" in prompt
    assert "Do not use broader fuzzy matching" in prompt


def test_meaningful_new_document_identity_is_not_normalized_away() -> None:
    item = _item(
        IdentityRelationship.PARTIAL_DUPLICATE,
        CanonicalAction.UPDATE,
        entity=EntityType.DOCUMENT,
    )
    item.source_fact_ids = ["fact-1", "fact-2"]
    item.provenance_fact_ids = ["fact-1", "fact-2"]
    plan = ReconciliationPlan(case_id="generic-case", items=[item], summary="fixture")
    record = {"encounters": [{"documents": [{"id": "existing-1", "accession": None, "title": "Pathology report"}]}]}
    event = {"facts": [
        {"id": "fact-1", "kind": "document", "title": "Pathology report", "external_document_id": "D-1", "institution": "X"},
        {"id": "fact-2", "kind": "identity", "external_document_id": "D-1", "accession": "A-1"},
    ]}
    normalized = normalize_superficial_duplicates(plan, record, event)
    assert normalized.items[0].identity_relationship is IdentityRelationship.PARTIAL_DUPLICATE


def test_request_same_event_omits_nonmaterial_temporal_classification() -> None:
    update = _compile(
        _item(IdentityRelationship.PARTIAL_DUPLICATE, CanonicalAction.UPDATE, entity=EntityType.REQUEST, temporal=TemporalRelationship.SAME_EVENT),
        {"id": "fact-1", "kind": "request", "description": "MRI", "status": "scheduled", "institution": "X"},
        {"id": "existing-1", "description": "MRI", "status": "ordered"},
    )
    assert update.temporal_classification is None


def test_same_measurement_result_preserves_temporal_classification() -> None:
    update = _compile(
        _item(IdentityRelationship.SEMANTIC_DUPLICATE, CanonicalAction.NO_OP, temporal=TemporalRelationship.SAME_MEASUREMENT),
        {"id": "fact-1", "kind": "result", "test_name": "sodium", "value": "140", "unit": "mmol/L", "timestamp": "t", "institution": "X"},
        {"id": "existing-1", "test_name": "sodium", "value": "140", "unit": "mmol/L", "timestamp": "t"},
    )
    assert update.temporal_classification == "same_measurement"


def test_distinct_later_result_preserves_temporal_classification() -> None:
    update = _compile(
        _item(IdentityRelationship.NEW, CanonicalAction.ADD, record_id=None, temporal=TemporalRelationship.DISTINCT_LATER),
        {"id": "fact-1", "kind": "result", "test_name": "sodium", "value": "141", "unit": "mmol/L", "timestamp": "later", "institution": "X"},
    )
    assert update.temporal_classification == "distinct_time"


def test_missing_test_name_and_unit_are_derived_from_absent_fields() -> None:
    update = _compile(
        _item(IdentityRelationship.MISSING_CONTEXT, CanonicalAction.FLAG_MISSING_CONTEXT, record_id=None, temporal=TemporalRelationship.SAME_EVENT),
        {"id": "fact-1", "kind": "result", "value": "7.1", "timestamp": "t", "institution": "X"},
    )
    assert update.value == {"reason": "test identity and unit missing", "value": "7.1"}


def test_missing_document_stable_identity_is_derived_from_absent_fields() -> None:
    update = _compile(
        _item(IdentityRelationship.MISSING_CONTEXT, CanonicalAction.FLAG_MISSING_CONTEXT, entity=EntityType.DOCUMENT, record_id=None),
        {"id": "fact-1", "kind": "document", "title": "Report", "institution": "X"},
    )
    assert update.value == {"reason": "document accession or external identifier missing", "title": "Report"}


def test_status_conflict_uses_existing_and_incoming_status() -> None:
    update = _compile(
        _item(IdentityRelationship.TRUE_CONFLICT, CanonicalAction.FLAG_CONFLICT, entity=EntityType.REQUEST),
        {"id": "fact-1", "kind": "request", "external_id": "R-1", "status": "active", "institution": "X"},
        {"id": "existing-1", "external_id": "R-1", "status": "cancelled"},
    )
    assert update.value == {
        "external_id": "R-1",
        "existing_status": "cancelled",
        "incoming_status": "active",
    }


def test_inference_modules_have_no_case_specific_rules() -> None:
    inference_modules = [
        Path("src/ai_legacy_last_mile/reconciliation_planner_exp004.py"),
        Path("src/ai_legacy_last_mile/canonical_update_compiler_exp004.py"),
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in inference_modules)
    source += inspect.getsource(run_experiment_exp004)
    assert "stress-" + "p" not in source
    assert "ground_" + "truth" not in source
