"""Load and validate the repository's versioned JSON fixtures."""

import json
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from .models import (
    ClinicalDocument,
    IncomingEvent,
    MappingCase,
    PatientRecord,
    ProposedUpdate,
    StatefulSchemaExtension,
    TargetSchema,
    UpdateCase,
)

T = TypeVar("T")
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _load_list(path: Path, item_type: type[T]) -> list[T]:
    with path.open(encoding="utf-8") as fixture:
        payload = json.load(fixture)
    return TypeAdapter(list[item_type]).validate_python(payload)


def load_documents(data_dir: Path = DEFAULT_DATA_DIR) -> list[ClinicalDocument]:
    return _load_list(data_dir / "clinical_documents.json", ClinicalDocument)


def load_schemas(data_dir: Path = DEFAULT_DATA_DIR) -> list[TargetSchema]:
    return _load_list(data_dir / "target_schemas.json", TargetSchema)


def load_ground_truth(data_dir: Path = DEFAULT_DATA_DIR) -> list[MappingCase]:
    return _load_list(data_dir / "ground_truth_mappings.json", MappingCase)


def load_documents_file(path: Path) -> list[ClinicalDocument]:
    """Load documents from an explicit baseline input path."""

    return _load_list(path, ClinicalDocument)


def load_schemas_file(path: Path) -> list[TargetSchema]:
    """Load schemas from an explicit baseline input path."""

    return _load_list(path, TargetSchema)


def load_patient_records(data_dir: Path = DEFAULT_DATA_DIR) -> list[PatientRecord]:
    """Load current synthetic patient record states."""

    return _load_list(data_dir / "patient_records.json", PatientRecord)


def load_incoming_events(data_dir: Path = DEFAULT_DATA_DIR) -> list[IncomingEvent]:
    """Load new explicitly sourced synthetic events."""

    return _load_list(data_dir / "incoming_events.json", IncomingEvent)


def load_ground_truth_updates(data_dir: Path = DEFAULT_DATA_DIR) -> list[ProposedUpdate]:
    """Load expected actions for the stateful update benchmark."""

    return _load_list(data_dir / "ground_truth_updates.json", ProposedUpdate)


def load_update_cases(data_dir: Path = DEFAULT_DATA_DIR) -> list[UpdateCase]:
    """Load stable patient/event/target-schema case identities."""

    return _load_list(data_dir / "stateful_cases.json", UpdateCase)


def load_stateful_schema_extensions(
    data_dir: Path = DEFAULT_DATA_DIR,
) -> list[StatefulSchemaExtension]:
    """Load operational fields extending the existing target systems."""

    return _load_list(data_dir / "stateful_schema_extensions.json", StatefulSchemaExtension)


def load_patient_records_file(path: Path) -> list[PatientRecord]:
    """Load patient records from an explicit Experiment 002 input path."""

    return _load_list(path, PatientRecord)


def load_incoming_events_file(path: Path) -> list[IncomingEvent]:
    """Load incoming events from an explicit Experiment 002 input path."""

    return _load_list(path, IncomingEvent)


def load_update_cases_file(path: Path) -> list[UpdateCase]:
    """Load case identities from an explicit Experiment 002 input path."""

    return _load_list(path, UpdateCase)


def load_stateful_schema_extensions_file(path: Path) -> list[StatefulSchemaExtension]:
    """Load operational schema fields from an explicit Experiment 002 input path."""

    return _load_list(path, StatefulSchemaExtension)
