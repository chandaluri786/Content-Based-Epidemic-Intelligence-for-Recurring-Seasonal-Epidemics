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
    """Read the solved examples: records with article_id, scan_date, link, article and answer."""
    return json.loads(path.read_text(encoding="utf-8"))


def format_article(scan_date: str, link: str, article_text: str) -> str:
    """Write one article the way the prompt expects it (section 3 of prompt v2.0)."""
    return f"Scan date: {scan_date}\nLink: {link}\nArticle:\n{article_text}"


def build_prefix_messages(system_prompt: str, examples: list[dict]) -> list[dict]:
    """The part of the request that is the same for every article: instructions and examples.

    Each example becomes two messages: the article as a user turn and the human answer,
    written as JSON, as the assistant turn. Built once per run.
    """
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


def build_messages(prefix_messages: list[dict], article: Article) -> list[dict]:
    """The full request: the shared prefix plus this article as the final user message."""
    user_message = {
        "role": "user",
        "content": format_article(article.scan_date, article.link, article.text),
    }
    return [*prefix_messages, user_message]
