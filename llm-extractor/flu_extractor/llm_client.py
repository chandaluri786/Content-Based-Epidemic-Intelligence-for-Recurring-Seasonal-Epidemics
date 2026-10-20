"""The only module that talks to the NVIDIA API."""

import time
from dataclasses import dataclass

from openai import OpenAI

from flu_extractor import config


@dataclass(frozen=True)
class ModelReply:
    """What came back from one model call."""

    text: str                     # the model's answer, unparsed
    finish_reason: str            # "stop" = finished normally, "length" = cut off at MAX_TOKENS
    prompt_tokens: int | None     # tokens the server counted in our request
    completion_tokens: int | None # tokens the model wrote
    seconds: float                # wall-clock time for the call, including retries


def create_client() -> OpenAI:
    """Create the API client. NVIDIA's API follows OpenAI's format, so we reuse OpenAI's library."""
    return OpenAI(
        base_url=config.BASE_URL,
        api_key=config.get_api_key(),
        timeout=config.REQUEST_TIMEOUT_SECONDS,
        # No retries inside the library: its quick retries on 429 make a rate limit worse. Retries
        # and pacing are done in flu_extractor/extractor.py and flu_extractor/pacing.py.
        max_retries=0,
    )


def ask_model(client: OpenAI, messages: list[dict]) -> ModelReply:
    """Send one request (a list of chat messages) and return the reply.

    Raises openai.OpenAIError if all retries fail.
    """
    started = time.time()
    response = client.chat.completions.create(
        model=config.MODEL_ID,
        messages=messages,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
        extra_body=config.EXTRA_BODY,
    )
    choice = response.choices[0]
    usage = response.usage
    return ModelReply(
        text=choice.message.content or "",
        finish_reason=choice.finish_reason or "",
        prompt_tokens=usage.prompt_tokens if usage else None,
        completion_tokens=usage.completion_tokens if usage else None,
        seconds=round(time.time() - started, 2),
    )
