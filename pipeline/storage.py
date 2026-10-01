"""
Stage 10: persist extracted articles. Only ever called for articles that
already passed BOTH retrievability and content-richness (Stages 8-9) --
callers are responsible for that check, this module doesn't re-check it.

One record per article. The stored shape is deliberately trimmed to five
things -- url, datetime, themes, locations, article text -- plus the GDELT
record ID as a storage key. No author, no media links, no pass/fail gate
flags. `locations` is the article's full, unfiltered location list, even
though Stage 5 already required at least one cohort country to be present
to get this far -- see README "Stage 5 -> location filtering."

Pluggable backend (config.STORAGE_BACKEND). A local filesystem backend is
always available and needs no configuration; an S3 backend is provided as
the default real cloud option. See README "Open decisions" -- the actual
cloud provider wasn't specified when this was built, so S3 was chosen as a
reasonable default, not confirmed. Swap in a different backend class here
if a different provider is actually wanted.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from config import LOCAL_STORAGE_DIR, S3_BUCKET_NAME, S3_KEY_PREFIX, S3_REGION, STORAGE_BACKEND
from models import ExtractedArticle


class StorageBackend(ABC):
    @abstractmethod
    def write(self, article: ExtractedArticle) -> None:
        """Persist one article record."""


class LocalStorageBackend(StorageBackend):
    """Appends one JSON line per article to a single file:
    {LOCAL_STORAGE_DIR}/matched_articles.jsonl

    No per-country split -- there's no country field to split on anymore.
    A labeling tool filters by inspecting each line's "locations" list
    itself (e.g. does it contain country_fips "IN")."""

    def __init__(self, base_dir: str = LOCAL_STORAGE_DIR) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._base_dir / "matched_articles.jsonl"

    def write(self, article: ExtractedArticle) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_to_dict(article)) + "\n")


class S3StorageBackend(StorageBackend):
    """Writes one JSON object per article to S3, keyed by GDELT record ID:
    s3://{bucket}/{prefix}/{record_id}.json

    No per-country nesting. A labeling tool reading from S3 lists objects
    under the prefix and filters on each object's "locations" field, the
    same way the local backend's single file is filtered.
    """

    def __init__(self, bucket: str = S3_BUCKET_NAME, prefix: str = S3_KEY_PREFIX, region: str = S3_REGION) -> None:
        import boto3  # imported lazily -- boto3 is only required when this backend is actually used

        if not bucket:
            raise ValueError("PIPELINE_S3_BUCKET must be set to use the S3 storage backend.")
        self._client = boto3.client("s3", region_name=region)
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")

    def write(self, article: ExtractedArticle) -> None:
        key = f"{self._prefix}/{article.gkg_record_id}.json"
        body = json.dumps(_to_dict(article)).encode("utf-8")
        self._client.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType="application/json")


def _to_dict(article: ExtractedArticle) -> dict:
    """Exactly five content fields (url, datetime, themes, locations,
    article) plus the GDELT record ID as a storage key -- see README
    "Final storage structure" for the full schema and why each field not
    included here was deliberately left out."""
    return {
        "gkg_record_id": article.gkg_record_id,
        "url": article.url,
        "datetime": article.gkg_datetime,
        "themes": [{"theme": h.theme, "offset": h.char_offset} for h in article.themes],
        "locations": [
            {"name": loc.name, "country_fips": loc.country_fips, "offset": loc.char_offset}
            for loc in article.locations
        ],
        "article": article.article_text,
    }


def get_storage_backend() -> StorageBackend:
    if STORAGE_BACKEND == "s3":
        return S3StorageBackend()
    return LocalStorageBackend()
