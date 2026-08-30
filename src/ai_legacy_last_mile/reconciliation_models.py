"""Transport-safe intermediate models for Experiment 003 reconciliation plans."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IdentityRelationship(StrEnum):
    NEW = "NEW"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"
    EQUIVALENT_UNIT_DUPLICATE = "EQUIVALENT_UNIT_DUPLICATE"
    PARTIAL_DUPLICATE = "PARTIAL_DUPLICATE"
    TRUE_CONFLICT = "TRUE_CONFLICT"
    MISSING_CONTEXT = "MISSING_CONTEXT"


class TemporalRelationship(StrEnum):
    SAME_EVENT = "SAME_EVENT"
    SAME_MEASUREMENT = "SAME_MEASUREMENT"
    DISTINCT_LATER = "DISTINCT_LATER"
    HISTORICAL = "HISTORICAL"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CanonicalAction(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    LINK = "LINK"
    NO_OP = "NO_OP"
    FLAG_CONFLICT = "FLAG_CONFLICT"
    FLAG_MISSING_CONTEXT = "FLAG_MISSING_CONTEXT"


class EntityType(StrEnum):
    RESULT = "RESULT"
    REQUEST = "REQUEST"
    DOCUMENT = "DOCUMENT"


class PlanItem(BaseModel):
    """One independently compilable fact group, with no arbitrary JSON fields."""

    model_config = ConfigDict(extra="forbid")
    source_fact_ids: list[str] = Field(min_length=1)
    entity_type: EntityType
    matched_record_id: str | None
    matched_encounter_id: str | None
    proposed_record_id: str | None
    identity_relationship: IdentityRelationship
    temporal_relationship: TemporalRelationship
    new_write_needed: bool
    intended_action: CanonicalAction
    target_collection: str
    provenance_fact_ids: list[str] = Field(min_length=1)
    reason: str
    evidence: list[str]
    human_approval_required: bool

    @model_validator(mode="after")
    def validate_contract(self) -> "PlanItem":
        if not set(self.provenance_fact_ids) <= set(self.source_fact_ids):
            raise ValueError("provenance facts must belong to the planned fact group")
        return self


class ReconciliationPlan(BaseModel):
    """Auditable output of the single planning call for one benchmark case."""

    model_config = ConfigDict(extra="forbid")
    case_id: str
    items: list[PlanItem]
    summary: str
