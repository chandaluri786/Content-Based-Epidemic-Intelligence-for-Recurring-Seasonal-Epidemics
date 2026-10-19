"""Load the articles and the human labels from the JSON files in data/."""

import json
from dataclasses import dataclass, field
from pathlib import Path

DEV = "dev"
TEST = "test"
SPLITS = (DEV, TEST)


@dataclass(frozen=True)
class Article:
    """One news article, exactly as it is sent to the model."""

    article_id: str   # e.g. "20240214121500-1731"
    labeler: str      # who labeled it (Aditya, Jahnavi, Manoj or Thanya)
    split: str        # "dev" (tune on it) or "test" (run once, at the end)
    scan_date: str    # YYYY-MM-DD, the day the article was collected
    link: str
    text: str         # the article body (the "article" field in the JSON)


@dataclass(frozen=True)
class HumanLabel:
    """The human answer for one article."""

    article_id: str
    labeler: str
    split: str
    useful: bool
    items: list[dict] = field(default_factory=list)  # human items, in the model's reply format


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_articles(path: Path) -> dict[str, Article]:
    """Read articles.json into {article_id: Article}."""
    return {
        record["article_id"]: Article(
            article_id=record["article_id"],
            labeler=record["labeler"],
            split=record["split"],
            scan_date=record["scan_date"],
            link=record["link"],
            text=record["article"],
        )
        for record in _read_json(path)
    }


def load_human_labels(path: Path) -> dict[str, HumanLabel]:
    """Read human_labels.json into {article_id: HumanLabel}."""
    return {
        record["article_id"]: HumanLabel(
            article_id=record["article_id"],
            labeler=record["labeler"],
            split=record["split"],
            useful=record["useful"],
            items=record["items"],
        )
        for record in _read_json(path)
    }
