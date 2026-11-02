"""Run the model on one article and turn its reply into a log record.

Every reply is validated before it is accepted: it must be complete (not cut off at MAX_TOKENS),
parse as one JSON object (after a safe repair of stray quotes), and follow the reply format
(checks.find_shape_errors). An invalid reply is asked for again with a note naming the problem,
up to MAX_VALIDATION_RETRIES times; the last time it asks for a compact reply at
LAST_RETRY_TEMPERATURE. Each request goes through the shared rate limiter.
"""

import json

import openai

from flu_extractor import config
from flu_extractor.checks import find_shape_errors
from flu_extractor.data_loading import Article
from flu_extractor.llm_client import ask_model
from flu_extractor.prompt import build_messages

# The Rule 1 reply of the prompt. An article that fails the keyword gate never reaches the model,
# because the prompt tells the model this check has already happened in code.
RULE_1_REPLY = {
    "summary": "The article failed the flu keyword check, so it was not sent to the model.",
    "reasoning": [
        "Step 0 (summary): The article failed the flu keyword check, so it was not sent to the model.",
        "Step 1 (Rule 1): the article never mentions flu, influenza, a flu strain, a flu drug or "
        "vaccine, or a flu-like illness, so it is not useful.",
    ],
    "useful": False,
    "reason": "Not useful: the article never mentions flu, influenza, a flu strain, a flu drug or "
              "vaccine, or a flu-like illness.",
    "items": [],
}

TRUNCATED = "reply truncated at max_tokens"

# What the model is told when its reply was invalid. Added after the article in the next request.
_NOTE_TRUNCATED = (
    "Note: your previous reply to this article was too long and was cut off before the JSON object "
    "ended. Reply again with one complete JSON object. Keep each reasoning step to one or two short "
    "sentences, list each statement once, and do not repeat yourself."
)
_NOTE_INVALID_JSON = (
    "Note: your previous reply to this article was not valid JSON ({problem}). Reply again with one "
    "valid JSON object and nothing else. Inside every JSON string, write a double quote as \\\" and a "
    "line break as \\n; when you quote the article in `reasoning`, you may use single quotes instead."
)
# The last attempt asks for a compact reply that avoids the usual causes of a broken reply: article
# text quoted inside `reasoning` (stray quotes), and long or repeating reasoning (cut off).
_NOTE_COMPACT = (
    "Note: your earlier replies to this article were invalid ({problem}). Reply again with one valid "
    "JSON object, and keep it compact: `reasoning` is one JSON array of at most 12 short steps, closed "
    "with ] only after the last step; inside `reasoning`, refer to statements as S1, S2, ... and do not "
    "copy any text from the article. Article text appears only in `evidence`, copied exactly, with every "
    "double quote written as \\\"."
)
_NOTE_FORMAT = (
    "Note: your previous reply to this article broke the reply format: {problem}. Reply again with "
    "one JSON object that has summary, reasoning, useful, reason and items, and every item with all "
    "12 fields."
)


def repair_json_strings(text: str) -> str:
    """Escape what a model often leaves raw inside JSON strings: double quotes and control characters.

    A double quote inside a string ends it only when the next non-space character is one that may
    follow a string in JSON (, : } ] or the end); any other double quote is article text and is
    escaped. Line breaks and tabs inside strings become \\n and \\t. Text outside strings is kept.
    """
    out, in_string, i = [], False, 0
    while i < len(text):
        char = text[i]
        if not in_string:
            out.append(char)
            in_string = char == '"'
        elif char == "\\":
            out.append(text[i:i + 2])  # an escape the model wrote itself: keep it whole
            i += 2
            continue
        elif char == '"':
            j = i + 1
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j == len(text) or text[j] in ",:}]":
                out.append(char)
                in_string = False
            else:
                out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\t":
            out.append("\\t")
        elif ord(char) < 0x20:
            out.append(" ")
        else:
            out.append(char)
        i += 1
    return "".join(out)


def parse_reply(reply_text: str) -> tuple[dict | None, str | None, bool]:
    """Parse the model's reply as JSON. Returns (parsed object, error message, repaired).

    Models sometimes wrap JSON in ```json fences or add a sentence around it, so if the plain
    parse fails we retry on the text between the first "{" and the last "}". If that fails too,
    the same texts are tried again after repair_json_strings; `repaired` says so.
    """
    candidates = [reply_text.strip()]
    first_brace, last_brace = reply_text.find("{"), reply_text.rfind("}")
    if 0 <= first_brace < last_brace:
        candidates.append(reply_text[first_brace : last_brace + 1])

    last_error = "empty reply"
    for repaired in (False, True):
        for candidate in candidates:
            try:
                parsed = json.loads(repair_json_strings(candidate) if repaired else candidate)
            except json.JSONDecodeError as error:
                if not repaired:
                    last_error = f"invalid JSON: {error}"
                continue
            if isinstance(parsed, dict):
                return parsed, None, repaired
            last_error = "JSON is not an object"
    return None, last_error, False


def _problem_and_note(reply) -> tuple[dict | None, str | None, bool, str]:
    """Validate one reply. Returns (parsed, problem or None, repaired, note for the next request)."""
    if reply.finish_reason == "length":
        return None, TRUNCATED, False, _NOTE_TRUNCATED
    parsed, error, repaired = parse_reply(reply.text)
    if parsed is None:
        return None, error, False, _NOTE_INVALID_JSON.format(problem=error)
    shape_errors = find_shape_errors(parsed)
    if shape_errors:
        problem = "; ".join(shape_errors[:5])
        return parsed, f"malformed: {problem}", repaired, _NOTE_FORMAT.format(problem=problem)
    return parsed, None, repaired, ""


def extract_article(client, prefix_messages: list[dict], article: Article) -> dict:
    """Call the model for one article and return a record ready to write to the run log.

    A failed call never raises: the error is stored in the record so one bad article
    cannot stop a long run, and the row can be retried later.
    """
    record = {
        "article_id": article.article_id,
        "model": config.MODEL_ID,
        "gated": not article.passes_keyword_gate,
        "finish_reason": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "seconds": None,
        "attempts": None,               # requests sent, including rate-limit and validation retries
        "validation_retries": 0,        # requests repeated because the reply was invalid
        "validation_problems": [],      # what was wrong with each rejected reply
        "repaired": False,              # the accepted reply needed stray quotes escaped
        "invalid": None,                # why the last reply was still invalid after all retries, else None
        "raw_reply": None,
        "parsed": None,
        "parse_error": None,
        "api_error": None,
    }
    if record["gated"]:
        record["parsed"] = RULE_1_REPLY
        return record

    note, prompt_tokens, completion_tokens, seconds, attempts = "", 0, 0, 0.0, 0
    for validation_round in range(config.MAX_VALIDATION_RETRIES + 1):
        last_round = validation_round == config.MAX_VALIDATION_RETRIES and validation_round > 0
        if last_round:  # the same kind of request has failed before: ask for a compact reply, and vary it
            note = _NOTE_COMPACT.format(problem=record["validation_problems"][-1][:200])
        try:
            reply = ask_model(client, build_messages(prefix_messages, article, note),
                              temperature=config.LAST_RETRY_TEMPERATURE if last_round else None)
        except openai.OpenAIError as error:
            record["api_error"] = f"{type(error).__name__}: {error}"
            break
        prompt_tokens += reply.prompt_tokens or 0
        completion_tokens += reply.completion_tokens or 0
        seconds += reply.seconds
        attempts += reply.attempts
        parsed, problem, repaired, note = _problem_and_note(reply)
        record.update(finish_reason=reply.finish_reason, raw_reply=reply.text, parsed=parsed,
                      parse_error=problem if parsed is None else None, repaired=repaired,
                      validation_retries=validation_round)
        record["invalid"] = problem
        if problem is None:
            break
        record["validation_problems"].append(problem)

    record.update(prompt_tokens=prompt_tokens or None, completion_tokens=completion_tokens or None,
                  seconds=round(seconds, 2) if attempts else None, attempts=attempts or None)
    return record
