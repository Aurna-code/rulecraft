"""Identifier helpers for Rulecraft v0.1."""

from __future__ import annotations

import hashlib
import uuid


def new_run_id() -> str:
    return str(uuid.uuid4())


def stable_hash_id(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()
