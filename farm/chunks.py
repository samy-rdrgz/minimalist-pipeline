"""Render chunks: a render's range cut into chunks of frames, each claimed by
one machine at a time -- see NOTES.md, "Farm 1.1.0: chunks replace
placeholders"."""

import json
import os
import re
import shutil
from pathlib import Path

from ..lib import ConfigCache, read_json_quiet, retry_shared_io, write_json_atomic

_CLAIM_NAME = re.compile(r"claim_(\d+)\.json")


def chunk_frames(start: int, end: int, size: int, k: int) -> tuple[int, int] | None:
    """(first, last) frame of chunk k (from 0) of the range start-end, both
    inclusive -- the last chunk cut short at end. None past the range. Pure."""
    s = start + k * size
    if s > end:
        return None
    e = s + size - 1
    return (s, min(end, e))


def chunks_number(start: int, end: int, size: int) -> int:
    """How many chunks the range start-end (inclusive) has. Pure."""
    return (end - start + size) // size


def free_chunks(start: int, size: int, missing: list[int], claimed) -> list[int]:
    """Chunks of a range starting at start with a frame still missing and no
    claim, in order. Pure."""
    return sorted({(f - start) // size for f in missing} - set(claimed))


def claims_dir(job_id: str) -> Path:
    """The folder of job_id's claims, one file per chunk in progress."""
    return ConfigCache.get_path("farm_claims") / job_id


def claim_path(job_id: str, k: int) -> Path:
    """Chunk k's claim: there while a machine renders it, gone once done."""
    return claims_dir(job_id) / f"claim_{k}.json"


def try_claim(job_id: str, k: int, data: dict) -> bool:
    """Claim chunk k for this machine: its claim file created exclusively,
    data in it. False if another machine holds it (or is releasing it:
    Windows refuses to open a file pending deletion). Any other error is
    raised -- the render fails visibly, rather than finding "nothing left"
    on a share it can't reach -- its claim removed if it got created."""
    path = claim_path(job_id, k)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        f = open(path, "x", encoding="utf-8")
    except (FileExistsError, PermissionError):
        return False
    try:
        with f:
            json.dump(data, f)
    except Exception:
        release_claim(job_id, k)  # never leave a claim nobody holds
        raise
    return True


def write_claim(job_id: str, k: int, data: dict) -> None:
    """Rewrite chunk k's claim (frame in progress, frames done): its holder
    is its only writer, so no lock."""
    write_json_atomic(claim_path(job_id, k), data)


def release_claim(job_id: str, k: int) -> None:
    """Delete chunk k's claim. Already gone is fine (the host freed it)."""
    try:
        retry_shared_io(claim_path(job_id, k).unlink)
    except FileNotFoundError:
        pass


def read_claims(job_id: str) -> dict[int, dict]:
    """{k: claim data} of every chunk of job_id claimed right now -- one
    listing of its folder. A claim unreadable this instant (just created,
    not written yet) is {}: claimed all the same, by an unknown machine."""
    try:
        entries = list(os.scandir(claims_dir(job_id)))
    except FileNotFoundError:
        return {}
    claims = {}
    for entry in entries:
        match = _CLAIM_NAME.fullmatch(entry.name)
        if match:
            claims[int(match.group(1))] = read_json_quiet(entry.path) or {}
    return claims


def remove_claims(job_id: str) -> None:
    """Delete job_id's claims folder, once nothing renders it. Best effort."""
    shutil.rmtree(claims_dir(job_id), ignore_errors=True)
