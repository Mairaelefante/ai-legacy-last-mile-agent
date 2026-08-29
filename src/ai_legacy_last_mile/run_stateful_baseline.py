"""CLI for Experiment 002 stateful prediction generation only."""

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .datasets import (
    load_incoming_events_file,
    load_patient_records_file,
    load_schemas_file,
    load_stateful_schema_extensions_file,
    load_update_cases_file,
)
from .llm import LLMClient, OpenAIClient
from .stateful_baseline import run_stateful_baseline


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def execute(
    records_path: Path,
    events_path: Path,
    cases_path: Path,
    schemas_path: Path,
    extensions_path: Path,
    output_path: Path,
    client: LLMClient,
) -> int:
    """Generate and persist predictions without loading or running evaluation."""

    result = run_stateful_baseline(
        load_patient_records_file(records_path),
        load_incoming_events_file(events_path),
        load_update_cases_file(cases_path),
        load_schemas_file(schemas_path),
        load_stateful_schema_extensions_file(extensions_path),
        client,
    )
    stem = output_path.stem.removesuffix("_predictions")
    raw_path = output_path.with_name(f"{stem}_raw.json")
    failures_path = output_path.with_name(f"{stem}_failures.json")
    _write_json(output_path, [update.model_dump(mode="json") for update in result.predictions])
    _write_json(
        raw_path,
        [response.model_dump(mode="json") for response in result.raw_responses],
    )
    _write_json(
        failures_path,
        [failure.model_dump(mode="json") for failure in result.failures],
    )
    return len(result.failures)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one general-purpose LLM request per stateful benchmark case"
    )
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--schemas", required=True, type=Path)
    parser.add_argument("--schema-extensions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    configured = (("OPENAI_API_KEY", api_key), ("OPENAI_MODEL", model))
    missing = [name for name, value in configured if not value]
    if missing:
        parser.error(f"missing required environment variables: {', '.join(missing)}")

    failures = execute(
        args.records,
        args.events,
        args.cases,
        args.schemas,
        args.schema_extensions,
        args.output,
        OpenAIClient(api_key=api_key, model=model),
    )
    print(f"Saved stateful predictions to {args.output} ({failures} failed cases)")


if __name__ == "__main__":
    main()
