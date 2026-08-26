"""Persistence of runs and baselines. Depends on `digline.core`."""

from digline.store.file_store import FileResultStore, utc_now_iso
from digline.store.migrate import (
    MigrationReport,
    NonAdditiveError,
    migrate_file,
    migrate_paths,
    upgrade_document,
)
from digline.store.protocol import (
    ConfigMismatchError,
    ErroredRunError,
    Listing,
    ResultStore,
    RunRef,
    TenantMismatchError,
)

__all__ = [
    "ConfigMismatchError",
    "ErroredRunError",
    "FileResultStore",
    "Listing",
    "MigrationReport",
    "NonAdditiveError",
    "ResultStore",
    "RunRef",
    "TenantMismatchError",
    "migrate_file",
    "migrate_paths",
    "upgrade_document",
    "utc_now_iso",
]
