"""CLI for the intentionally simple single-LLM baseline."""

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .baseline import run_baseline
from .datasets import load_documents_file, load_schemas_file
from .llm import OpenAIClient


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def execute(documents_path: Path, schemas_path: Path, output_path: Path, client: Any) -> int:
    """Run and persist predictions plus auditable raw/failure sidecars."""

    result = run_baseline(
        load_documents_file(documents_path), load_schemas_file(schemas_path), client
    )
    _write_json(output_path, [case.model_dump(mode="json") for case in result.predictions])
    _write_json(
        output_path.with_name(f"{output_path.stem}.raw.json"),
        [response.model_dump(mode="json") for response in result.raw_responses],
    )
    _write_json(
        output_path.with_name(f"{output_path.stem}.failures.json"),
        [failure.model_dump(mode="json") for failure in result.failures],
    )
    return len(result.failures)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one LLM request per document/schema pair")
    parser.add_argument("--documents", required=True, type=Path)
    parser.add_argument("--schemas", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL")
    configured = (("OPENAI_API_KEY", api_key), ("OPENAI_MODEL", model))
    missing = [name for name, value in configured if not value]
    if missing:
        parser.error(f"missing required environment variables: {', '.join(missing)}")

    failures = execute(
        args.documents,
        args.schemas,
        args.output,
        OpenAIClient(api_key=api_key, model=model),
    )
    print(f"Saved predictions to {args.output} ({failures} failed cases)")


if __name__ == "__main__":
    main()
