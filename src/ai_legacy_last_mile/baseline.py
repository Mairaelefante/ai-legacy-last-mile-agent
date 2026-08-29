"""Intentionally simple: one LLM mapping request per document/schema pair."""

import json
from dataclasses import dataclass

from .llm import LLMClient
from .models import (
    BaselineFailure,
    ClinicalDocument,
    MappingCase,
    MappingResponse,
    RawBaselineResponse,
    TargetSchema,
)


@dataclass(frozen=True)
class BaselineRun:
    predictions: list[MappingCase]
    raw_responses: list[RawBaselineResponse]
    failures: list[BaselineFailure]


def build_prompt(document: ClinicalDocument, schema: TargetSchema) -> str:
    """Serialize only the source document/facts and complete target schema."""

    payload = {
        "clinical_document": document.model_dump(mode="json"),
        "target_schema": schema.model_dump(mode="json"),
    }
    return (
        "Map every source fact exactly once to the best target field. Use only source fact "
        "IDs and target field paths present below. Preserve each source fact's value exactly. "
        "Return only the structured mappings.\n\n"
        + json.dumps(payload, indent=2)
    )


def _validate_response(
    response: MappingResponse, document: ClinicalDocument, schema: TargetSchema
) -> None:
    expected_fact_ids = {fact.id for fact in document.facts}
    returned_fact_ids = [mapping.source_fact_id for mapping in response.mappings]
    missing = expected_fact_ids - set(returned_fact_ids)
    duplicates = sorted(
        {fact_id for fact_id in returned_fact_ids if returned_fact_ids.count(fact_id) > 1}
    )
    unknown_facts = set(returned_fact_ids) - expected_fact_ids
    valid_paths = {field.path for field in schema.fields}
    nonexistent_paths = {
        mapping.target_field_path
        for mapping in response.mappings
        if mapping.target_field_path not in valid_paths
    }
    if missing:
        raise ValueError(f"missing mappings for source facts: {sorted(missing)}")
    if duplicates:
        raise ValueError(f"duplicate mappings for source facts: {duplicates}")
    if unknown_facts:
        raise ValueError(f"unknown source fact IDs: {sorted(unknown_facts)}")
    if nonexistent_paths:
        raise ValueError(f"nonexistent target fields: {sorted(nonexistent_paths)}")
    source_values = {fact.id: fact.value for fact in document.facts}
    changed_values = sorted(
        mapping.source_fact_id
        for mapping in response.mappings
        if mapping.source_fact_id in source_values
        and mapping.value != source_values[mapping.source_fact_id]
    )
    if changed_values:
        raise ValueError(f"mapped values differ from source facts: {changed_values}")


def run_baseline(
    documents: list[ClinicalDocument], schemas: list[TargetSchema], client: LLMClient
) -> BaselineRun:
    """Run every pair once; failed cases remain empty so evaluation penalizes them."""

    predictions: list[MappingCase] = []
    raw_responses: list[RawBaselineResponse] = []
    failures: list[BaselineFailure] = []
    for document in documents:
        for schema in schemas:
            mappings = []
            raw_text: str | None = None
            try:
                completion = client.complete(build_prompt(document, schema), MappingResponse)
                raw_text = completion.raw_text
                response = MappingResponse.model_validate(completion.parsed)
                _validate_response(response, document, schema)
                mappings = response.mappings
                raw_responses.append(
                    RawBaselineResponse(
                        document_id=document.id,
                        target_schema_id=schema.id,
                        response=raw_text,
                    )
                )
            except Exception as error:
                # No retry: retain an empty case so the failed request counts against results.
                message = str(error)
                failures.append(
                    BaselineFailure(
                        document_id=document.id,
                        target_schema_id=schema.id,
                        error_type=type(error).__name__,
                        message=message,
                    )
                )
                raw_responses.append(
                    RawBaselineResponse(
                        document_id=document.id,
                        target_schema_id=schema.id,
                        response=raw_text,
                        error=message,
                    )
                )
            predictions.append(
                MappingCase(
                    document_id=document.id,
                    target_schema_id=schema.id,
                    mappings=mappings,
                )
            )
    return BaselineRun(predictions, raw_responses, failures)
