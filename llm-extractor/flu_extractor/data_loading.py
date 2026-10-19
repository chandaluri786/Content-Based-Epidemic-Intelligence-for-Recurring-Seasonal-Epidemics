"""Load the articles and the human labels from the JSON files in data/."""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Article:
    """One news article, exactly as it is sent to the model."""

    row: int          # row number in the labeling sheet (1-based)
    article_id: str   # e.g. "20240214121500-1731"
    scan_date: str    # YYYY-MM-DD, the day the article was collected
    link: str
    text: str         # the article body (the "article" field in the JSON)


@dataclass(frozen=True)
class HumanLabel:
    """The human answer for one article."""

    row: int
    article_id: str
    useful: bool | None   # None when the human sheet has no label (rows 109 and 152)
    needs_relook: bool    # the labeler is unsure about this row
    items: list[dict] = field(default_factory=list)  # human items, in the model's reply format


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_articles(path: Path) -> dict[int, Article]:
    """Read articles.json into {row number: Article}."""
    return {
        record["row"]: Article(
            row=record["row"],
            article_id=record["article_id"],
            scan_date=record["scan_date"],
            link=record["link"],
            text=record["article"],
        )
        for record in _read_json(path)
    }


def load_human_labels(path: Path) -> dict[int, HumanLabel]:
    """Read human_labels.json into {row number: HumanLabel}."""
    return {
        record["row"]: HumanLabel(
            row=record["row"],
            article_id=record["article_id"],
            useful=record["useful"],
            needs_relook=record["needs_relook"],
            items=record["items"],
        )
        for record in _read_json(path)
    }
