"""Run the model on one article and turn its reply into a log record."""

import json

import openai

from flu_extractor import config
from flu_extractor.data_loading import Article
from flu_extractor.llm_client import ask_model
from flu_extractor.prompt import build_messages


def parse_reply(reply_text: str) -> tuple[dict | None, str | None]:
    """Parse the model's reply as JSON. Returns (parsed object, error message).

    Models sometimes wrap JSON in ```json fences or add a sentence around it, so if the
    plain parse fails we retry on the text between the first "{" and the last "}".
    """
    candidates = [reply_text.strip()]
    first_brace, last_brace = reply_text.find("{"), reply_text.rfind("}")
    if 0 <= first_brace < last_brace:
        candidates.append(reply_text[first_brace : last_brace + 1])

    last_error = "empty reply"
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as error:
            last_error = f"invalid JSON: {error}"
            continue
        if isinstance(parsed, dict):
            return parsed, None
        last_error = "JSON is not an object"
    return None, last_error


def extract_article(client, prefix_messages: list[dict], article: Article) -> dict:
    """Call the model for one article and return a record ready to write to the run log.

    A failed call never raises: the error is stored in the record so one bad article
    cannot stop a long run, and the article can be retried later.
    """
    record = {
        "article_id": article.article_id,
        "split": article.split,
        "model": config.MODEL_ID,
        "finish_reason": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "seconds": None,
        "raw_reply": None,
        "parsed": None,
        "parse_error": None,
        "api_error": None,
    }
    try:
        reply = ask_model(client, build_messages(prefix_messages, article))
    except openai.OpenAIError as error:
        record["api_error"] = f"{type(error).__name__}: {error}"
        return record

    record.update(
        finish_reason=reply.finish_reason,
        prompt_tokens=reply.prompt_tokens,
        completion_tokens=reply.completion_tokens,
        seconds=reply.seconds,
        raw_reply=reply.text,
    )
    if reply.finish_reason == "length":
        # A reply cut off at MAX_TOKENS is incomplete JSON; do not try to repair it.
        record["parse_error"] = "reply truncated at max_tokens"
    else:
        record["parsed"], record["parse_error"] = parse_reply(reply.text)
    return record
