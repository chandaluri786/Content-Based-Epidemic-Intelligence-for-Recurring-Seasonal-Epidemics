"""Build the chat messages sent to the model.

A request is: the system prompt, then each solved example as a user/assistant pair
(few-shot), then the article to process as the last user message.
"""

import json
from pathlib import Path

from flu_extractor.data_loading import Article


def load_system_prompt(path: Path) -> str:
    """Read the instructions (a plain text file) that tell the model what to do."""
    return path.read_text(encoding="utf-8").strip()


def load_examples(path: Path) -> list[dict]:
    """Read the solved examples: records with article_id, scan_date, link, article, answer."""
    return json.loads(path.read_text(encoding="utf-8"))


def format_article(scan_date: str, link: str, article_text: str) -> str:
    """Write one article with the input names the prompt uses (its Input section)."""
    return f"scan_date: {scan_date}\nlink: {link}\narticle:\n{article_text}"


def build_prefix_messages(system_prompt: str, examples: list[dict], fewshot_guide: str = "") -> list[dict]:
    """The part of the request that is the same for every article: instructions and examples.

    The few-shot guide (how to learn from the examples' reasoning and evidence) follows the
    rules in the system message, only when there are examples. Each example becomes two
    messages: the article as a user turn and the answer, written as JSON, as the assistant
    turn. Built once per run.
    """
    if examples and fewshot_guide:
        system_prompt = f"{system_prompt}\n\n---\n\n{fewshot_guide}"
    messages = [{"role": "system", "content": system_prompt}]
    for example in examples:
        messages.append({
            "role": "user",
            "content": format_article(example["scan_date"], example["link"], example["article"]),
        })
        messages.append({
            "role": "assistant",
            "content": json.dumps(example["answer"], ensure_ascii=False),
        })
    return messages


def build_messages(prefix_messages: list[dict], article: Article, note: str = "") -> list[dict]:
    """The full request: the shared prefix plus this article as the final user message.

    `note` is added after the article only when an earlier reply for it was invalid: it says what
    was wrong, so the next reply differs (at temperature 0 the same request gives the same reply).
    """
    content = format_article(article.scan_date, article.link, article.text)
    if note:
        content += f"\n\n{note}"
    return [*prefix_messages, {"role": "user", "content": content}]
