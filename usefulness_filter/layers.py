"""The keyword filter's rule: which layer each pool article falls in.

Layer 1 keeps every P_/Z_ article. Layer 2 drops the other articles that have no flu word
(the keyword rules of flu_bucketing/flu_keywords.py). Everything else is sent to the LLM.
"""

import sys

import filter_config as cfg

sys.path.insert(0, str(cfg.REPO_DIR / "flu_bucketing"))
from flu_keywords import flu_hits  # noqa: E402  (the keyword rules of flu_bucketing/)


def keyword_hits(text: str | None) -> int:
    """The number of flu words in an article; 0 means none at all."""
    return len(flu_hits(text or ""))


def layer_for(bucket: str, hits: int) -> str:
    """Keep the P_/Z_ buckets; drop the rest when they have no flu word; send everything else."""
    if bucket.startswith(cfg.ALWAYS_KEEP_PREFIXES):
        return cfg.LAYER_KEEP_BUCKET
    if hits == 0:
        return cfg.LAYER_DROP_KEYWORD
    return cfg.LAYER_FLU_WORD
