from ai_legacy_last_mile.datasets import (
    load_documents,
    load_ground_truth,
    load_schemas,
)


def test_loads_expected_synthetic_dataset_sizes() -> None:
    documents = load_documents()
    schemas = load_schemas()
    cases = load_ground_truth()

    assert len(documents) == 10
    assert len(schemas) == 2
    assert len(cases) == len(documents) * len(schemas)
    assert all(document.text.startswith("SYNTHETIC TEST RECORD") for document in documents)


def test_ground_truth_references_known_documents_schemas_facts_and_fields() -> None:
    documents = {document.id: document for document in load_documents()}
    schemas = {schema.id: schema for schema in load_schemas()}

    for case in load_ground_truth():
        document = documents[case.document_id]
        schema = schemas[case.target_schema_id]
        fact_ids = {fact.id for fact in document.facts}
        field_paths = {field.path for field in schema.fields}
        assert {mapping.source_fact_id for mapping in case.mappings} <= fact_ids
        assert {mapping.target_field_path for mapping in case.mappings} <= field_paths
