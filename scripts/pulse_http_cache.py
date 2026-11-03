#!/usr/bin/env python3
"""PULSE reusable HTTP cache and conservative ISTAT SDMX quota gate.

One cache directory for radar and structured-document fetches. No proxy/IP
rotation, no unlimited retry, no private response cache and no fake data.
"""
from __future__ import annotations
import hashlib
import json
import os
import random
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError

CACHE = Path(os.environ.get("PULSE_HTTP_CACHE_DIR", ".pulse_http_cache"))
HOST_LIMIT_SECONDS = 16.0  # maximum 3.75 ISTAT SDMX requests per minute
ISTAT_HOST_SUFFIX = ("istat.it",)
MAX_BYTES = 8_000_000


def is_istat_sdmx(url):
    p = urlsplit(str(url))
    host = (p.hostname or "").lower()
    path = p.path.lower()
    return (host == "istat.it" or host.endswith(".istat.it")) and any(
        part in (host + path) for part in ("sdmx", "istatdata", "/rest/", "/dataflow/", "/data/")
    )


def _cache_key(url):
    return hashlib.sha256(str(url).encode("utf-8")).hexdigest()


def _cache_path(url):
    return CACHE / (_cache_key(url) + ".json")


def _get_cached(url, ttl):
    if ttl <= 0:
        return None
    p = _cache_path(url)
    try:
        saved = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - saved["at"] > ttl:
            return None
        data = bytes.fromhex(saved["hex"])
        if hashlib.sha256(data).hexdigest() != saved["sha256"]:
            return None
        return data, saved["final_url"], saved["content_type"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _put_cached(url, data, final_url, content_type):
    if len(data) > MAX_BYTES or not (content_type.startswith(("text/", "application/json", "application/xml",
                                                               "application/vnd", "application/octet-stream"))):
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    entry = {"at": time.time(), "hex": data.hex(), "final_url": final_url,
             "content_type": content_type, "sha256": hashlib.sha256(data).hexdigest()}
    tmp = _cache_path(url).with_suffix(".tmp")
    tmp.write_text(json.dumps(entry), encoding="utf-8")
    tmp.replace(_cache_path(url))


def _quota_wait():
    """File-backed throttle within a single GitHub job. No concurrency promises across IPs."""
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / "istat_sdmx_last_request.json"
    try:
        previous = float(json.loads(p.read_text(encoding="utf-8"))["at"])
    except (OSError, KeyError, TypeError, ValueError):
        previous = 0
    delay = HOST_LIMIT_SECONDS - (time.time() - previous)
    if delay > 0:
        time.sleep(delay)
    p.write_text(json.dumps({"at": time.time()}), encoding="utf-8")


def request_cached(url, *, timeout=12, max_bytes=700_000, ttl_seconds=14400, headers=None,
                   transport=None):
    """Return (bytes, final URL, content type); bounded + fail-closed.

    When supplied, transport is a test fake accepting (url, timeout, max_bytes, headers).
    """
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("HTTPS public URLs only")
    cached = _get_cached(url, ttl_seconds)
    if cached is not None and len(cached[0]) <= max_bytes:
        return cached
    if is_istat_sdmx(url):
        _quota_wait()
    chosen_headers = {"User-Agent": "ISTAT-PULSE-Newsroom/2.0", "Accept": "*/*"}
    chosen_headers.update(headers or {})
    if transport is not None:
        raw, final_url, content_type = transport(url, timeout, max_bytes, chosen_headers)
    else:
        req = Request(url, headers=chosen_headers)
        try:
            with urlopen(req, timeout=timeout) as resp:
                raw = resp.read(max_bytes + 1)
                final_url = resp.geturl()
                content_type = resp.headers.get("Content-Type", "")
        except HTTPError as exc:
            # Respect explicit back-off for throttled endpoints; do not retry here.
            if exc.code in (429, 503):
                raise RuntimeError("provider_rate_limited") from exc
            raise
    if len(raw) > max_bytes:
        raise ValueError("document_exceeds_limit")
    if urlsplit(final_url).scheme != "https":
        raise ValueError("unsafe_redirect")
    if (not is_istat_sdmx(url)) or is_istat_sdmx(final_url):
        _put_cached(url, raw, final_url, content_type)
    return raw, final_url, content_type
