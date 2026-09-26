"""Load manifest: one row per attempted partition load, plus the current state per partition.

Plan §4: every source partition records URL, source-provided update time, fetch time,
scope, checksum, schema fingerprint, row count, load status and code version.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import polars as pl
import psycopg

from .config import PROJECT_ROOT


@lru_cache(maxsize=1)
def code_version() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:  # noqa: BLE001 - git is optional
        pass
    return "unversioned"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def schema_fingerprint(df: pl.DataFrame) -> str:
    sig = ";".join(f"{c}:{t}" for c, t in zip(df.columns, df.dtypes, strict=True))
    return hashlib.sha1(sig.encode()).hexdigest()[:16]


@dataclass
class LoadRecord:
    source: str
    dataset: str
    partition_key: str
    status: str = "success"
    source_url: str | None = None
    source_last_modified: str | None = None
    source_etag: str | None = None
    fetched_at: datetime | None = None
    checksum_sha256: str | None = None
    schema_fingerprint: str | None = None
    row_count: int | None = None
    error: str | None = None
    file_path: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_params(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "dataset": self.dataset,
            "partition_key": self.partition_key,
            "source_url": self.source_url,
            "source_last_modified": self.source_last_modified,
            "source_etag": self.source_etag,
            "fetched_at": self.fetched_at,
            "checksum_sha256": self.checksum_sha256,
            "schema_fingerprint": self.schema_fingerprint,
            "row_count": self.row_count,
            "status": self.status,
            "error": (self.error or "")[:4000] or None,
            "code_version": code_version(),
            "file_path": self.file_path,
            "started_at": self.started_at,
        }


def get_partition_state(
    conn: psycopg.Connection, source: str, dataset: str, partition_key: str
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """select checksum_sha256, source_etag, source_last_modified, row_count, loaded_at
               from ops.source_partition where source=%s and dataset=%s and partition_key=%s""",
            (source, dataset, partition_key),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "checksum_sha256": row[0],
        "source_etag": row[1],
        "source_last_modified": row[2],
        "row_count": row[3],
        "loaded_at": row[4],
    }


def record_manifest(conn: psycopg.Connection, rec: LoadRecord) -> int:
    """Insert a manifest row; on success also update the partition state. Caller commits."""
    p = rec.as_params()
    with conn.cursor() as cur:
        cur.execute(
            """insert into ops.load_manifest
               (source, dataset, partition_key, source_url, source_last_modified, source_etag,
                fetched_at, checksum_sha256, schema_fingerprint, row_count, status, error,
                code_version, file_path, started_at, finished_at)
               values (%(source)s, %(dataset)s, %(partition_key)s, %(source_url)s,
                       %(source_last_modified)s, %(source_etag)s, %(fetched_at)s,
                       %(checksum_sha256)s, %(schema_fingerprint)s, %(row_count)s, %(status)s,
                       %(error)s, %(code_version)s, %(file_path)s, %(started_at)s, now())
               returning load_id""",
            p,
        )
        load_id = cur.fetchone()[0]
        if rec.status == "success":
            cur.execute(
                """insert into ops.source_partition
                   (source, dataset, partition_key, last_load_id, checksum_sha256, source_etag,
                    source_last_modified, row_count, loaded_at)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,now())
                   on conflict (source, dataset, partition_key) do update set
                     last_load_id=excluded.last_load_id, checksum_sha256=excluded.checksum_sha256,
                     source_etag=excluded.source_etag, source_last_modified=excluded.source_last_modified,
                     row_count=excluded.row_count, loaded_at=now()""",
                (
                    rec.source,
                    rec.dataset,
                    rec.partition_key,
                    load_id,
                    rec.checksum_sha256,
                    rec.source_etag,
                    rec.source_last_modified,
                    rec.row_count,
                ),
            )
    return load_id
