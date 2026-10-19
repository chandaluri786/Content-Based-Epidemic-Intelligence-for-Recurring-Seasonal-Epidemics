"""Tests for reading the four labeling sheets, the sample and the split (scripts/build_data_files.py).

Uses small made-up sheets in a temporary folder. Run from the llm-extractor folder:

    python -m unittest discover tests
"""

import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_data_files.py"
_spec = importlib.util.spec_from_file_location("build_data_files", _SCRIPT)
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

LABEL_FIELDS = ["row", "round", "article_id", "link", "scan_date", "useful", "causes", "labeler", "notes"]
ITEM_FIELDS = ["article_id", "strain", "kind", "number", "status", "total_or_new", "city", "state", "country",
               "start_date", "end_date", "words", "evidence"]


def item_row(article_id: str, **fields) -> dict:
    base = {name: "" for name in ITEM_FIELDS}
    return {**base, "article_id": article_id, "kind": "cases", "number": "12", "country": "USA",
            "end_date": "2020-01-10", "evidence": "Twelve cases were reported.", **fields}


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class SheetsTest(unittest.TestCase):
    """Each labeler owns one useful and one not-useful article and checks someone else's useful one."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        names = build.LABELERS
        for n, name in enumerate(names):
            partner = f"{names[(n + 1) % len(names)]}-yes"
            write_csv(self.folder / f"{name}_labels.csv", LABEL_FIELDS, [
                {"row": 1, "round": "1-own", "article_id": f"{name}-yes", "useful": "Yes", "labeler": name},
                {"row": 2, "round": "2", "article_id": f"{name}-no", "useful": "no", "labeler": name},
                {"row": 3, "round": "1-check-x", "article_id": partner, "useful": "no", "labeler": name},
            ])
            write_csv(self.folder / f"{name}_items.csv", ITEM_FIELDS, [
                item_row(f"{name}-yes", evidence="First quote.\n||\nSecond quote. || Third quote."),
                item_row(partner, number="999"),  # this labeler's copy of the partner's item: never used
            ])
        self.answers = build.read_sheets(self.folder)
        self.ids = sorted(self.answers)
        self.sample = {i: {"record_id": i, "scan_date": "2020-01-10", "url": f"https://x/{i}", "text": "body"}
                       for i in self.ids}
        self.split = {i: {"article_id": i, "split": "dev" if n % 2 else "test",
                          "useful": self.answers[i]["useful"]} for n, i in enumerate(self.ids)}

    def errors(self):
        return build.validate(self.answers, self.sample, self.split, expected_size=len(self.ids))

    def test_check_rows_are_skipped_and_items_come_from_the_owner(self):
        self.assertEqual(len(self.answers), 8)
        yes = self.answers["Jahnavi-yes"]
        self.assertEqual((yes["labeler"], yes["useful"]), ("Jahnavi", "yes"))
        self.assertEqual([i["number"] for i in yes["items"]], [12])
        self.assertEqual(self.answers["Jahnavi-no"]["items"], [])

    def test_both_evidence_separator_styles_are_split(self):
        evidence = self.answers["Aditya-yes"]["items"][0]["evidence"]
        self.assertEqual(evidence, ["First quote.", "Second quote.", "Third quote."])

    def test_clean_sheets_pass_and_build_one_record_each(self):
        self.assertEqual(self.errors(), [])
        articles, labels = build.build_records(self.answers, self.sample, self.split)
        self.assertEqual([a["article_id"] for a in articles], self.ids)
        self.assertEqual([label["split"] for label in labels], [self.split[i]["split"] for i in self.ids])
        self.assertTrue(all(a["link"].startswith("https://x/") for a in articles))
        self.assertEqual({label["useful"] for label in labels}, {True, False})

    def test_yes_without_items_is_an_error(self):
        self.answers["Manoj-yes"]["items"] = []
        self.assertTrue(any("no items" in e for e in self.errors()))

    def test_no_with_items_is_an_error(self):
        self.answers["Manoj-no"]["items"] = list(self.answers["Manoj-yes"]["items"])
        self.assertTrue(any("useful is no but" in e for e in self.errors()))

    def test_sheet_and_split_disagreeing_is_an_error(self):
        self.split["Thanya-yes"] = {**self.split["Thanya-yes"], "useful": "no"}
        self.assertTrue(any("the split says" in e for e in self.errors()))

    def test_wrong_number_of_articles_is_an_error(self):
        self.assertTrue(any("not 1200" in e for e in build.validate(self.answers, self.sample, self.split)))

    def test_article_missing_from_the_split_is_an_error(self):
        del self.split["Thanya-no"]
        self.assertTrue(any("Thanya-no: not in the split" in e for e in self.errors()))

    def test_bad_item_fields_are_errors(self):
        bad = build.convert_item(item_row("x", number="about 40", end_date="12/20/2024", country="", kind="case"))
        problems = build.item_problems(bad)
        self.assertEqual(len(problems), 4, problems)


if __name__ == "__main__":
    unittest.main()
