"""Offline tests of the keyword filter and the extractor input. Run from usefulness_filter/:

    ../llm-extractor/.venv/bin/python -m unittest discover tests
"""

import unittest

import filter_config as cfg
from layers import keyword_hits, layer_for
from pool_articles import build_pool_articles, decide_layers, gold_check, is_call_to_make

K, D, F = cfg.LAYER_KEEP_BUCKET, cfg.LAYER_DROP_KEYWORD, cfg.LAYER_FLU_WORD


def text(record_id: str, article: str = "Flu cases rose.", bucket: str = "N_x") -> dict:
    return {"record_id": record_id, "bucket": bucket, "country": "USA", "year": "2019",
            "scan_date": "2019-01-04", "link": "http://x", "article": article}


def decision(record_id: str, layer: str, in_gold: bool = False) -> dict:
    return {"record_id": record_id, "bucket": "N_x", "country": "USA", "year": "2019", "layer": layer,
            "keyword_hits": 1, "in_gold": in_gold}


class LayerTest(unittest.TestCase):
    def test_p_and_z_buckets_are_always_kept_even_without_a_flu_word(self):
        for bucket in ("P_A1_counts", "P_B_trend_response", "Z_zoonotic_human"):
            self.assertEqual(layer_for(bucket, 0), K)

    def test_other_buckets_without_a_flu_word_are_dropped(self):
        self.assertEqual(layer_for("N_awareness", 0), D)
        self.assertEqual(layer_for("X_too_short", 0), D)

    def test_other_buckets_with_a_flu_word_are_sent(self):
        self.assertEqual(layer_for("N_other_flu_mention", 1), F)

    def test_keyword_hits_come_from_flu_bucketing(self):
        self.assertGreater(keyword_hits("Swine flu cases rose to 40 in Pune."), 0)
        self.assertEqual(keyword_hits("The fluid market fluctuated."), 0)
        self.assertEqual(keyword_hits(None), 0)


class DecideTest(unittest.TestCase):
    def test_every_pool_article_gets_a_layer_and_a_gold_flag(self):
        texts = [text("a"), text("b", "The fluid market fluctuated."), text("c", "No flu word.", "P_A1_counts")]
        decisions = decide_layers(texts, gold_ids={"c"})
        self.assertEqual([(d["record_id"], d["layer"], d["in_gold"]) for d in decisions],
                         [("a", F, False), ("b", D, False), ("c", K, True)])

    def test_gold_check_counts_useful_gold_articles_dropped(self):
        decisions = [decision("g1", D, True), decision("g2", F, True), decision("g3", D, True)]
        self.assertEqual(gold_check(decisions, {"g1": True, "g2": True, "g3": False}), (1, 2))

    def test_a_gold_article_missing_from_the_pool_stops(self):
        with self.assertRaises(ValueError):
            gold_check([decision("g1", F, True)], {"g1": True, "g9": True})


class CallRuleTest(unittest.TestCase):
    def test_articles_with_a_flu_word_or_a_p_z_bucket_and_not_in_gold_are_sent(self):
        self.assertTrue(is_call_to_make(decision("a", K)))
        self.assertTrue(is_call_to_make(decision("a", F)))

    def test_no_flu_word_or_gold_articles_are_not_sent(self):
        self.assertFalse(is_call_to_make(decision("a", D)))
        self.assertFalse(is_call_to_make(decision("a", F, in_gold=True)))

    def test_an_unknown_layer_stops(self):
        with self.assertRaises(ValueError):
            is_call_to_make(decision("a", "typo"))


class BuildTest(unittest.TestCase):
    def test_sent_articles_get_the_extractor_format_in_decision_order(self):
        decisions = [decision("b", F), decision("x", D), decision("a", K)]
        articles = build_pool_articles(decisions, [text("a"), text("b"), text("x")])
        self.assertEqual([a["article_id"] for a in articles], ["b", "a"])
        self.assertEqual(articles[0], {"article_id": "b", "scan_date": "2019-01-04", "link": "http://x",
                                       "sources": [], "article": "Flu cases rose."})

    def test_a_sent_article_without_text_stops(self):
        with self.assertRaises(ValueError):
            build_pool_articles([decision("a", F)], [])
        with self.assertRaises(ValueError):
            build_pool_articles([decision("a", F)], [text("a", "  ")])


if __name__ == "__main__":
    unittest.main()
