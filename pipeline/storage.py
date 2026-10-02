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

Both backends bucket output by calendar year (the article's own
`gkg_datetime` year) so a consumer can retrieve just the year(s) it wants
without scanning everything -- see `_year_of` below.

Pluggable backend (config.STORAGE_BACKEND). A local filesystem backend is
always available and needs no configuration; a Google Drive backend is the
real remote option (decided: not an AWS/cloud-provider bucket). See README
"Storage -> Google Drive" for one-time setup. Swap in a different backend
class here if a different destination is actually wanted.
"""

from __future__ import annotations

import io
import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from config import (
    GDRIVE_CREDENTIALS_PATH,
    GDRIVE_FOLDER_ID,
    GDRIVE_TOKEN_PATH,
    LOCAL_STORAGE_DIR,
    STORAGE_BACKEND,
)
from models import ExtractedArticle

_GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class StorageBackend(ABC):
    @abstractmethod
    def write(self, article: ExtractedArticle) -> None:
        """Persist one article record."""

    def already_stored_ids(self) -> set[str]:
        """Every gkg_record_id already persisted by a previous run -- used
        by run_pipeline.py to seed cross-run deduplication, so overlapping
        windows across separate runs never store the same GDELT record
        twice. gkg_record_id, not url: it's deterministic (same raw GDELT
        file + line always parses to the same record_id), which is exactly
        the property needed to recognize "this day's file was already
        processed in an earlier run" -- see run_pipeline.py's module
        docstring for why this is the right key for that specific case.

        Default: none. Override where it's actually cheap to enumerate --
        see LocalStorageBackend. Not yet implemented for
        GoogleDriveStorageBackend (not in active use yet); a run against
        gdrive storage will only dedupe within that single run until this
        is added there too."""
        return set()


class LocalStorageBackend(StorageBackend):
    """Appends one JSON line per article to a year-bucketed file:
    {LOCAL_STORAGE_DIR}/{year}/matched_articles.jsonl

    `year` is taken from the article's own `gkg_datetime` (see _year_of) --
    the only date captured per article, so it's the only thing this can
    bucket on. No per-country split within a year -- there's no country
    field to split on anymore. A labeling tool filters by inspecting each
    line's "locations" list itself (e.g. does it contain country_fips
    "IN"), after first picking the year(s) it wants off disk."""

    def __init__(self, base_dir: str = LOCAL_STORAGE_DIR) -> None:
        self._base_dir = Path(base_dir)

    def write(self, article: ExtractedArticle) -> None:
        year_dir = self._base_dir / str(_year_of(article))
        year_dir.mkdir(parents=True, exist_ok=True)
        path = year_dir / "matched_articles.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_to_dict(article)) + "\n")

    def already_stored_ids(self) -> set[str]:
        """Reads every year's matched_articles.jsonl under base_dir and
        collects their gkg_record_id fields. Cheap here since it's just
        local file reads -- see the ABC docstring for why this exists."""
        ids: set[str] = set()
        if not self._base_dir.exists():
            return ids
        for jsonl_path in self._base_dir.glob("*/matched_articles.jsonl"):
            with jsonl_path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        ids.add(json.loads(line)["gkg_record_id"])
        return ids


class GoogleDriveStorageBackend(StorageBackend):
    """Writes one JSON file per article into a year subfolder of the
    configured Drive folder:
    {PIPELINE_GDRIVE_FOLDER_ID}/{year}/{record_id}.json

    `year` is taken from the article's own `gkg_datetime` (see _year_of).
    Year subfolders are looked up by name under the root folder and created
    on first use, then cached in `self._year_folder_ids` for the rest of
    the run so repeated writes in the same year don't re-query Drive every
    time. No per-country nesting within a year -- same filtering approach
    as the local backend (inspect each file's "locations" field after
    picking the year folder(s) you want).

    Uses OAuth2 *user* credentials, not a service account: a service
    account has no storage quota of its own on a regular (non-Workspace)
    Google Drive, so uploads under one would fail. The one-time interactive
    browser consent authorizes this script to act as the destination
    folder's owner; the resulting token is cached to GDRIVE_TOKEN_PATH so
    later runs don't need a browser again. See README "Storage -> Google
    Drive" for the one-time setup steps (Cloud Console project, OAuth
    client, sharing the folder).
    """

    def __init__(
        self,
        folder_id: str = GDRIVE_FOLDER_ID,
        credentials_path: str = GDRIVE_CREDENTIALS_PATH,
        token_path: str = GDRIVE_TOKEN_PATH,
    ) -> None:
        # Imported lazily -- these packages are only required when this
        # backend is actually used, same pattern the old S3 backend used.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload

        if not folder_id:
            raise ValueError("PIPELINE_GDRIVE_FOLDER_ID must be set to use the Google Drive storage backend.")

        self._folder_id = folder_id
        self._media_upload_cls = MediaIoBaseUpload
        self._year_folder_ids: dict[int, str] = {}

        token_file = Path(token_path)
        creds = Credentials.from_authorized_user_file(str(token_file), _GDRIVE_SCOPES) if token_file.exists() else None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, _GDRIVE_SCOPES)
                creds = flow.run_local_server(port=0)
            token_file.write_text(creds.to_json())

        self._service = build("drive", "v3", credentials=creds)

    def _year_folder_id(self, year: int) -> str:
        """Finds (or creates, on first use) the subfolder for `year` under
        the configured root Drive folder, and caches the result."""
        if year in self._year_folder_ids:
            return self._year_folder_ids[year]

        query = (
            f"name = '{year}' and mimeType = 'application/vnd.google-apps.folder' "
            f"and '{self._folder_id}' in parents and trashed = false"
        )
        existing = self._service.files().list(q=query, fields="files(id)", spaces="drive").execute()
        matches = existing.get("files", [])
        if matches:
            folder_id = matches[0]["id"]
        else:
            metadata = {
                "name": str(year),
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [self._folder_id],
            }
            folder_id = self._service.files().create(body=metadata, fields="id").execute()["id"]

        self._year_folder_ids[year] = folder_id
        return folder_id

    def write(self, article: ExtractedArticle) -> None:
        year_folder_id = self._year_folder_id(_year_of(article))
        body = json.dumps(_to_dict(article)).encode("utf-8")
        media = self._media_upload_cls(io.BytesIO(body), mimetype="application/json")
        metadata = {"name": f"{article.gkg_record_id}.json", "parents": [year_folder_id]}
        self._service.files().create(body=metadata, media_body=media, fields="id").execute()


def _year_of(article: ExtractedArticle) -> int:
    """The calendar year this article is bucketed under -- the year of the
    GKG record's own scan datetime (`gkg_datetime`), the only date captured
    per article. Not a country-season year: see the README's discussion of
    why per-country window attribution isn't tracked per record."""
    return datetime.fromisoformat(article.gkg_datetime).year


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
    if STORAGE_BACKEND == "gdrive":
        return GoogleDriveStorageBackend()
    return LocalStorageBackend()
