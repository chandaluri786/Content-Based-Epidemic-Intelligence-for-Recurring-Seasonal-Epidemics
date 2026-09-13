"""Disk-space safety guard for GDELT ingestion.

Reuses the pattern validated in investigation/check_gdelt_flu_content_raw.py:
check free space before starting and after every unit of work, abort rather
than risk a repeat of the earlier full-disk incident.
"""

import shutil


class DiskSpaceError(Exception):
    """Raised when free disk space drops below the configured safety threshold."""


def free_gb(path: str) -> float:
    """Return free disk space at path, in gigabytes."""
    _total, _used, free = shutil.disk_usage(path)
    return free / (1024**3)


def ensure_min_free_space(min_gb: float, path: str) -> None:
    """Raise DiskSpaceError if free space at path is below min_gb."""
    free = free_gb(path)
    if free < min_gb:
        raise DiskSpaceError(
            f"Free space at {path} is {free:.2f}GB, below the {min_gb}GB safety threshold"
        )
