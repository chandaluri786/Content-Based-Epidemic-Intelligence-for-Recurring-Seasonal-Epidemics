"""Load the articles and the gold labels from the JSON files in data/, and read label record files.

articles.json and gold_labels.json are written by scripts/build_gold_files.py from the label records
in data/chain_of_thought/ (config.RECORDS_SUFFIX). read_label_records() reads those record files in
either of the two layouts the project has:

    nested (chain-of-thought v2): {article_id, scan_date, source_rows, summary, reasoning,
                                   output: {useful, reason, items}, rules_used, hard_case, ...}
    flat (v5.2 labels):           {pos, tag, article_id, scan_date, split, summary, reasoning,
                                   useful, reason, items}
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Article:
    """One news article, exactly as it is sent to the model."""

    article_id: str   # e.g. "20240214121500-1731"
    scan_date: str    # YYYY-MM-DD, the day the article was collected
    link: str
    text: str         # the article body (the "article" field in the JSON)
    sources: tuple[str, ...] = ()  # where it appears in the labeling sets, e.g. ("Jahnavi:46",)


@dataclass(frozen=True)
class GoldLabel:
    """The answer for one article, from its label record."""

    article_id: str
    useful: bool
    items: list[dict] = field(default_factory=list)  # items in the model's reply format
    labelers: tuple[str, ...] = ()


_CITED_RULES = re.compile(r"^Step \d+ \(([^)]*)\)")


def _rules_cited(reasoning: list[str]) -> list[str]:
    """The rule IDs a reply's reasoning cites in its step headers, in first-cited order."""
    rules: list[str] = []
    for step in reasoning:
        match = _CITED_RULES.match(step)
        for rule in (match.group(1).split(",") if match else []):
            rule = rule.strip()
            if rule and rule not in rules:
                rules.append(rule)
    return rules


def read_label_records(path: Path) -> list[dict]:
    """Read one <Name><RECORDS_SUFFIX> file into records of the nested layout (see the module doc).

    A flat record is converted: its labeler is the file name before the first "_", its row is `pos`,
    and `rules_used` is taken from the rule IDs its reasoning cites.
    """
    labeler = path.name.split("_")[0]
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if "output" not in record:
            record = {
                "article_id": record["article_id"], "scan_date": record["scan_date"],
                "source_rows": [{"labeler": labeler, "row": record["pos"]}],
                "summary": record["summary"], "reasoning": record["reasoning"],
                "output": {"useful": record["useful"], "reason": record["reason"], "items": record["items"]},
                "rules_used": _rules_cited(record["reasoning"]),
            }
        records.append(record)
    return records


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


def resolve_article_id(spec: str, articles: dict[str, Article]) -> str:
    """Turn an article id or a set position such as 'Jahnavi:46' into an article id."""
    if spec in articles:
        return spec
    for article in articles.values():
        if spec in article.sources:
            return article.article_id
    raise ValueError(f"No article matches {spec!r}. Use an article id or a form like Jahnavi:46.")
