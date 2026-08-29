"""Validated data contracts shared by datasets and future mapping agents."""

import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model which rejects misspelled or unexpected fixture fields."""

    model_config = ConfigDict(extra="forbid")


class SourceFact(StrictModel):
    """A normalized fact extracted from a synthetic source document."""

    id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    name: str = Field(min_length=1)
    value: Any
    unit: str | None = None


class ClinicalDocument(StrictModel):
    """A synthetic clinical note and its normalized source facts."""

    id: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    text: str = Field(min_length=1)
    facts: list[SourceFact] = Field(min_length=1)

    @model_validator(mode="after")
    def fact_ids_are_unique(self) -> "ClinicalDocument":
        ids = [fact.id for fact in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("fact IDs must be unique within a document")
        return self


class TargetField(StrictModel):
    """A writable leaf in a target system, addressed with a dotted path."""

    path: str = Field(min_length=1)
    label: str = Field(min_length=1)
    data_type: Literal["string", "integer", "number", "boolean", "date"]
    required: bool = False
    description: str | None = None


class TargetSchema(StrictModel):
    """The flattened writable contract of one heterogeneous target EHR."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    fields: list[TargetField] = Field(min_length=1)

    @model_validator(mode="after")
    def field_paths_are_unique(self) -> "TargetSchema":
        paths = [field.path for field in self.fields]
        if len(paths) != len(set(paths)):
            raise ValueError("target field paths must be unique")
        return self


class MappingResult(StrictModel):
    """One proposed assignment from a source fact to a target field."""

    source_fact_id: str = Field(min_length=1)
    target_field_path: str = Field(min_length=1)
    value: Any


class MappingCase(StrictModel):
    """Mappings for one document/schema pair."""

    document_id: str = Field(min_length=1)
    target_schema_id: str = Field(min_length=1)
    mappings: list[MappingResult]


class MappingResponse(StrictModel):
    """Structured output requested from the baseline LLM."""

    mappings: list[MappingResult]


class BaselineFailure(StrictModel):
    """A failed document/schema request retained for honest evaluation."""

    document_id: str
    target_schema_id: str
    error_type: str
    message: str


class RawBaselineResponse(StrictModel):
    """Raw response or error captured for one baseline request."""

    document_id: str
    target_schema_id: str
    response: str | None = None
    error: str | None = None


class PatientDemographics(StrictModel):
    """Minimal fictional patient identity used by the stateful benchmark."""

    full_name: str = Field(min_length=1)
    birth_date: str = Field(min_length=1)


class MedicationRecord(StrictModel):
    """A medication explicitly present in the current synthetic record."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    dose: str = Field(min_length=1)
    status: Literal["active"] = "active"


class ClinicalDiaryEntry(StrictModel):
    """An existing time-stamped clinical diary entry."""

    id: str = Field(min_length=1)
    recorded_at: datetime
    text: str = Field(min_length=1)


class ObservationRecord(StrictModel):
    """An explicitly recorded observation or result."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    value: Any
    unit: str | None = None
    observed_at: datetime


class RequestRecord(StrictModel):
    """A request already present in the synthetic record."""

    id: str = Field(min_length=1)
    request_type: Literal["imaging", "consultation", "laboratory"]
    description: str = Field(min_length=1)
    status: Literal["active"] = "active"


class AvailableDocument(StrictModel):
    """A document already available in the current record."""

    id: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    title: str = Field(min_length=1)


class PatientRecord(StrictModel):
    """Current state of one wholly synthetic hospitalized patient's record."""

    patient_id: str = Field(min_length=1)
    demographics: PatientDemographics
    clinical_framing: list[str]
    active_medications: list[MedicationRecord]
    clinical_diary_entries: list[ClinicalDiaryEntry]
    observations: list[ObservationRecord]
    active_requests: list[RequestRecord]
    available_documents: list[AvailableDocument]


class EventType(StrEnum):
    CLINICAL_NOTE = "CLINICAL_NOTE"
    MEDICATION_UPDATE = "MEDICATION_UPDATE"
    IMAGING_REQUEST = "IMAGING_REQUEST"
    CONSULTATION_REQUEST = "CONSULTATION_REQUEST"
    LAB_RESULT = "LAB_RESULT"
    RADIOLOGY_REPORT = "RADIOLOGY_REPORT"
    EXTERNAL_DOCUMENT = "EXTERNAL_DOCUMENT"


class EventSource(StrictModel):
    """Explicit provenance for an incoming synthetic event."""

    source_id: str = Field(min_length=1)
    source_type: Literal["clinician", "laboratory", "radiology", "external_system"]
    author: str = Field(min_length=1)


class IncomingEvent(StrictModel):
    """New explicitly sourced information arriving after the current record."""

    event_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    event_type: EventType
    occurred_at: datetime
    source: EventSource
    summary: str = Field(min_length=1)
    facts: list[SourceFact] = Field(min_length=1)

    @model_validator(mode="after")
    def fact_ids_are_unique(self) -> "IncomingEvent":
        ids = [fact.id for fact in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("fact IDs must be unique within an incoming event")
        return self


class UpdateActionType(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    NO_OP = "NO_OP"
    FLAG_CONFLICT = "FLAG_CONFLICT"
    FLAG_MISSING_CONTEXT = "FLAG_MISSING_CONTEXT"


class UpdateStatus(StrEnum):
    PROPOSED = "PROPOSED"
    REQUIRES_HUMAN_REVIEW = "REQUIRES_HUMAN_REVIEW"
    INFORMATIONAL = "INFORMATIONAL"


class ProposedUpdate(StrictModel):
    """A traceable record action supported only by explicit source facts."""

    case_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    target_schema_id: str = Field(min_length=1)
    action_type: UpdateActionType
    target_path: str | None
    source_fact_ids: list[str] = Field(min_length=1)
    current_value: Any = None
    proposed_value: Any = None
    status: UpdateStatus
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def source_fact_ids_are_unique(self) -> "ProposedUpdate":
        if len(self.source_fact_ids) != len(set(self.source_fact_ids)):
            raise ValueError("source fact IDs must be unique within an update")
        return self


class UpdateCase(StrictModel):
    """Stable identity for a patient/event/destination evaluation case."""

    case_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    target_schema_id: str = Field(min_length=1)


class OperationalTargetField(StrictModel):
    """A stateful writable destination extending an Experiment 001 system."""

    path: str = Field(min_length=1)
    label: str = Field(min_length=1)


class StatefulSchemaExtension(StrictModel):
    """Operational fields keyed to an existing heterogeneous target schema."""

    target_schema_id: str = Field(min_length=1)
    fields: list[OperationalTargetField] = Field(min_length=1)

    @model_validator(mode="after")
    def field_paths_are_unique(self) -> "StatefulSchemaExtension":
        paths = [field.path for field in self.fields]
        if len(paths) != len(set(paths)):
            raise ValueError("operational target field paths must be unique")
        return self


class StatefulUpdateResponse(StrictModel):
    """Structured Experiment 002 output for one stateful case."""

    updates: list["StatefulOutputUpdate"]

    @classmethod
    def from_proposed_updates(
        cls, updates: list[ProposedUpdate]
    ) -> "StatefulUpdateResponse":
        """Encode flexible JSON values for the strict OpenAI response boundary."""

        return cls(
            updates=[
                StatefulOutputUpdate(
                    **update.model_dump(exclude={"current_value", "proposed_value"}),
                    current_value=json.dumps(update.current_value, separators=(",", ":")),
                    proposed_value=json.dumps(update.proposed_value, separators=(",", ":")),
                )
                for update in updates
            ]
        )

    def to_proposed_updates(self) -> list[ProposedUpdate]:
        """Decode strict response-boundary values into benchmark update values."""

        return [update.to_proposed_update() for update in self.updates]


class StatefulOutputUpdate(StrictModel):
    """OpenAI-compatible wire representation of a proposed stateful update."""

    case_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    target_schema_id: str = Field(min_length=1)
    action_type: UpdateActionType
    target_path: str | None
    source_fact_ids: list[str] = Field(min_length=1)
    current_value: str = Field(
        description="Current value encoded as a JSON string, including JSON null."
    )
    proposed_value: str = Field(
        description="Proposed value encoded as a JSON string, including JSON null."
    )
    status: UpdateStatus
    reason: str = Field(min_length=1)

    def to_proposed_update(self) -> ProposedUpdate:
        """Convert wire values without altering their JSON semantics."""

        return ProposedUpdate(
            **self.model_dump(exclude={"current_value", "proposed_value"}),
            current_value=json.loads(self.current_value),
            proposed_value=json.loads(self.proposed_value),
        )


class StatefulBaselineFailure(StrictModel):
    """A failed Experiment 002 case retained for honest evaluation."""

    case_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    target_schema_id: str = Field(min_length=1)
    error_type: str = Field(min_length=1)
    message: str = Field(min_length=1)


class RawStatefulResponse(StrictModel):
    """Raw response or error captured for one Experiment 002 request."""

    case_id: str = Field(min_length=1)
    patient_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    target_schema_id: str = Field(min_length=1)
    response: str | None = None
    error: str | None = None
