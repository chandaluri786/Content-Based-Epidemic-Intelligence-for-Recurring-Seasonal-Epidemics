"""Load the articles, the gold labels and the human labels from the JSON files in data/."""

import json
from dataclasses import dataclass, field
from pathlib import Path

DEV = "dev"    # Jahnavi, Aditya and Manoj (where the labels came from)
TEST = "test"  # Thanya rows 41-320 (no gold labels yet)
ALL = "all"    # both: runs treat every labelled article as one set


@dataclass(frozen=True)
class Article:
    """One news article, exactly as it is sent to the model."""

    article_id: str   # e.g. "20240214121500-1731"
    scan_date: str    # YYYY-MM-DD, the day the article was collected
    link: str
    text: str         # the article body (the "article" field in the JSON)
    split: str        # DEV or TEST
    passes_keyword_gate: bool  # False: Rule 1 applies and the model is not called
    sources: tuple[str, ...] = ()  # where it appears in the labeling sets, e.g. ("Jahnavi:46",)


@dataclass(frozen=True)
class GoldLabel:
    """The answer for one article, from the chain-of-thought records."""

    article_id: str
    useful: bool
    items: list[dict] = field(default_factory=list)  # items in the model's reply format
    labelers: tuple[str, ...] = ()


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_articles(path: Path) -> dict[str, Article]:
    """Read articles.json into {article_id: Article}."""
    return {
        record["article_id"]: Article(
            article_id=record["article_id"],
            scan_date=record["scan_date"],
            link=record["link"],
            text=record["article"],
            split=record["split"],
            passes_keyword_gate=record["passes_keyword_gate"],
            sources=tuple(record["sources"]),
        )
        for record in _read_json(path)
    }


def load_gold_labels(path: Path) -> dict[str, GoldLabel]:
    """Read gold_labels.json into {article_id: GoldLabel}."""
    return {
        record["article_id"]: GoldLabel(
            article_id=record["article_id"],
            useful=record["useful"],
            items=record["items"],
            labelers=tuple(record["labelers"]),
        )
        for record in _read_json(path)
    }


def load_human_useful(path: Path) -> dict[str, bool | None]:
    """Read human_labels.json into {article_id: the human useful answer}. None = no answer."""
    return {record["article_id"]: record["useful"] for record in _read_json(path)}


def resolve_article_id(spec: str, articles: dict[str, Article]) -> str:
    """Turn an article id or a set position such as 'Jahnavi:46' into an article id."""
    if spec in articles:
        return spec
    for article in articles.values():
        if spec in article.sources:
            return article.article_id
    raise ValueError(f"No article matches {spec!r}. Use an article id or a form like Jahnavi:46.")
