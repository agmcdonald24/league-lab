"""HTTP fetching with bounded retries, conditional requests, and an atomic on-disk archive.

The archive under ``data/raw/<source>/...`` is the replayable copy of every source partition.
Each file has a sidecar ``<file>.meta.json`` with URL, ETag, Last-Modified, fetch time and
SHA-256, so a later run can send ``If-None-Match`` and skip unchanged content (plan §7).
"""

from __future__ import annotations

import gzip
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from .config import get_settings
from .manifest import sha256_bytes

USER_AGENT = "league-lab/0.1 (+local analytics; contact: repo owner)"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    pass


@dataclass
class Fetched:
    url: str
    content: bytes
    status_code: int
    etag: str | None
    last_modified: str | None
    fetched_at: datetime
    from_cache: bool  # True when the server said 304 or the archive was used offline
    path: Path
    checksum: str

    @property
    def meta(self) -> dict:
        return {
            "url": self.url,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "fetched_at": self.fetched_at.isoformat(),
            "sha256": self.checksum,
            "bytes": len(self.content),
        }


def _meta_path(path: Path) -> Path:
    return path.with_name(path.name + ".meta.json")


def read_meta(path: Path) -> dict | None:
    mp = _meta_path(path)
    if mp.exists():
        try:
            return json.loads(mp.read_text())
        except json.JSONDecodeError:
            return None
    return None


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _write_archive(path: Path, data: bytes, meta: dict) -> None:
    _atomic_write(path, data)
    _atomic_write(_meta_path(path), json.dumps(meta, indent=2).encode())


def read_archive(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix == ".gz":
        return gzip.decompress(data)
    return data


def _client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        timeout=httpx.Timeout(s.http_timeout_seconds, connect=30.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        trust_env=True,
    )


def fetch_to_archive(
    url: str,
    path: Path,
    *,
    conditional: bool = True,
    offline: bool = False,
    client: httpx.Client | None = None,
    compress: bool = False,
) -> Fetched:
    """Download ``url`` into ``path`` (atomic) unless unchanged; return content + metadata.

    * ``conditional``: send If-None-Match / If-Modified-Since using the sidecar metadata.
    * ``offline``: never touch the network; replay the archived file or raise.
    * ``compress``: gzip the archive on disk (used for JSON payloads).
    """
    s = get_settings()
    prior = read_meta(path)
    now = datetime.now(UTC)

    if offline:
        if not path.exists():
            raise FetchError(f"offline replay requested but no archive at {path}")
        data = read_archive(path)
        return Fetched(
            url=url,
            content=data,
            status_code=0,
            etag=(prior or {}).get("etag"),
            last_modified=(prior or {}).get("last_modified"),
            fetched_at=datetime.fromisoformat(prior["fetched_at"]) if prior and prior.get("fetched_at") else now,
            from_cache=True,
            path=path,
            checksum=sha256_bytes(data),
        )

    headers: dict[str, str] = {}
    if conditional and prior and path.exists():
        if prior.get("etag"):
            headers["If-None-Match"] = prior["etag"]
        if prior.get("last_modified"):
            headers["If-Modified-Since"] = prior["last_modified"]

    own_client = client is None
    client = client or _client()
    try:
        last_exc: Exception | None = None
        for attempt in range(s.http_max_retries + 1):
            try:
                resp = client.get(url, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as exc:  # transient
                last_exc = exc
                resp = None
            if resp is not None and resp.status_code == 304 and path.exists():
                data = read_archive(path)
                return Fetched(
                    url=url,
                    content=data,
                    status_code=304,
                    etag=prior.get("etag") if prior else None,
                    last_modified=prior.get("last_modified") if prior else None,
                    fetched_at=now,
                    from_cache=True,
                    path=path,
                    checksum=sha256_bytes(data),
                )
            if resp is not None and resp.status_code == 200:
                data = resp.content
                fetched = Fetched(
                    url=url,
                    content=data,
                    status_code=200,
                    etag=resp.headers.get("etag"),
                    last_modified=resp.headers.get("last-modified"),
                    fetched_at=now,
                    from_cache=False,
                    path=path,
                    checksum=sha256_bytes(data),
                )
                on_disk = gzip.compress(data) if compress else data
                _write_archive(path, on_disk, fetched.meta)
                return fetched
            if resp is not None and resp.status_code == 404:
                raise FetchError(f"404 not found: {url}")
            if resp is not None and resp.status_code not in RETRY_STATUSES:
                raise FetchError(f"HTTP {resp.status_code} for {url}")
            # retry with exponential backoff + jitter (plan §7)
            if attempt < s.http_max_retries:
                delay = min(60.0, (2**attempt) + random.uniform(0, 1))
                if resp is not None and resp.headers.get("retry-after"):
                    try:
                        delay = max(delay, float(resp.headers["retry-after"]))
                    except ValueError:
                        pass
                time.sleep(delay)
        detail = f"HTTP {resp.status_code}" if resp is not None else repr(last_exc)
        raise FetchError(f"giving up on {url} after {s.http_max_retries + 1} attempts: {detail}")
    finally:
        if own_client:
            client.close()
