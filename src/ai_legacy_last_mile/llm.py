"""LLM provider boundary for the single-request baseline."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class LLMCompletion:
    """Provider-neutral structured completion and its raw text."""

    parsed: BaseModel
    raw_text: str


class LLMClient(Protocol):
    """Minimal interface required by the baseline runner."""

    def complete(self, prompt: str, response_model: type[BaseModel]) -> LLMCompletion:
        """Make one request and validate it as ``response_model``."""


class OpenAIClient:
    """Official OpenAI SDK adapter using Responses API structured output."""

    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def complete(self, prompt: str, response_model: type[BaseModel]) -> LLMCompletion:
        response = self._client.responses.parse(
            model=self._model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You map supplied source facts into supplied target fields. "
                        "Follow the response schema exactly and do not add commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text_format=response_model,
        )
        if response.output_parsed is None:
            raise ValueError("OpenAI response did not contain parsed structured output")
        return LLMCompletion(parsed=response.output_parsed, raw_text=response.output_text)
