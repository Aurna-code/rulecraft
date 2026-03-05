"""Verifier package."""

from __future__ import annotations

from typing import Any


def verify_text(*args: Any, **kwargs: Any) -> Any:
    from .l1 import verify_text as _verify_text

    return _verify_text(*args, **kwargs)


def verify_jsonschema(*args: Any, **kwargs: Any) -> Any:
    from .l3_jsonschema import verify_jsonschema as _verify_jsonschema

    return _verify_jsonschema(*args, **kwargs)


def verify_output(*args: Any, **kwargs: Any) -> Any:
    from .verify_output import verify_output as _verify_output

    return _verify_output(*args, **kwargs)


__all__ = ["verify_text", "verify_jsonschema", "verify_output"]
