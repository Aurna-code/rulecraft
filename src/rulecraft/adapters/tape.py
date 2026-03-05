"""Adapter tape record/replay helpers."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


TAPE_VERSION = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_seed(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_payload(
    *,
    prompt: str,
    instructions: str | None,
    seed: int | None,
    extra: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "instructions": instructions,
        "seed": seed,
        "extra": _json_safe(extra or {}),
    }


def make_request_hash(
    prompt: str,
    instructions: str | None,
    seed: int | None,
    extra: Mapping[str, Any] | None,
) -> str:
    """Create a deterministic request hash for tape indexing."""
    payload = _request_payload(
        prompt=str(prompt),
        instructions=instructions if isinstance(instructions, str) else None,
        seed=_normalize_seed(seed),
        extra=extra,
    )
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def append_tape_line(path: str | Path, line: Mapping[str, Any]) -> None:
    """Append one canonical tape line to a JSONL file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(dict(line), ensure_ascii=False, sort_keys=True))
        fp.write("\n")


def _request_from_generate(prompt: str, kwargs: Mapping[str, Any], backend: str) -> tuple[dict[str, Any], str]:
    instructions_raw = kwargs.get("instructions")
    instructions = instructions_raw if isinstance(instructions_raw, str) else None
    mode_raw = kwargs.get("mode")
    mode = mode_raw if isinstance(mode_raw, str) and mode_raw else None
    seed = _normalize_seed(kwargs.get("seed"))
    extra = {
        str(key): _json_safe(value)
        for key, value in sorted(kwargs.items(), key=lambda item: str(item[0]))
        if key not in {"instructions", "seed"}
    }
    request = {
        "backend": backend,
        "request_id": str(uuid.uuid4()),
        "prompt": str(prompt),
        "instructions": instructions,
        "seed": seed,
    }
    if mode is not None:
        request["mode"] = mode
    request_hash = make_request_hash(
        str(prompt),
        instructions,
        seed,
        extra,
    )
    return request, request_hash


class TapeReplayMissError(RuntimeError):
    """Raised when replay lookup misses the request hash."""


def _coerce_response(response: Any) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(response, tuple) or len(response) != 2:
        return None
    text, meta = response
    if not isinstance(meta, Mapping):
        return str(text), {}
    return str(text), dict(meta)


def _generate_with_fallback(adapter: Any, prompt: str, kwargs: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    request_kwargs = dict(kwargs)
    response = None

    try:
        response = adapter.generate(prompt, **request_kwargs)
    except TypeError:
        response = None

    coerced = _coerce_response(response)
    if coerced is not None:
        return coerced

    if "instructions" in request_kwargs:
        try:
            response = adapter.generate(prompt, instructions=request_kwargs.get("instructions"))
        except TypeError:
            response = None
        coerced = _coerce_response(response)
        if coerced is not None:
            return coerced

    response = adapter.generate(prompt)
    coerced = _coerce_response(response)
    if coerced is not None:
        return coerced
    raise RuntimeError("Adapter generate() must return (text, meta).")


class TapeRecorderAdapter:
    """Wrap an adapter and append generate calls to a tape file."""

    def __init__(self, adapter: Any, tape_path: str | Path, backend_name: str | None = None) -> None:
        self.adapter = adapter
        self.tape_path = Path(tape_path)
        self.backend_name = backend_name or type(adapter).__name__.lower()

    def generate(self, prompt: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        request, request_hash = _request_from_generate(prompt, kwargs, self.backend_name)
        text, normalized_meta = _generate_with_fallback(self.adapter, prompt, kwargs)
        line = {
            "tape_version": TAPE_VERSION,
            "ts_utc": _utc_now_iso(),
            "request": request,
            "request_hash": request_hash,
            "response": {
                "text": str(text),
                "meta": _json_safe(normalized_meta),
            },
        }
        append_tape_line(self.tape_path, line)
        return str(text), normalized_meta


class TapeReplayAdapter:
    """Replay adapter responses from a previously recorded tape."""

    def __init__(self, tape_path: str | Path) -> None:
        self.tape_path = Path(tape_path)
        self._responses = self._load_index(self.tape_path)

    @staticmethod
    def _load_index(path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            raise ValueError(f"Tape file not found: {path}")

        index: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as fp:
            for line_no, raw_line in enumerate(fp, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid tape JSON on line {line_no} in {path}.") from exc

                if not isinstance(payload, Mapping):
                    raise ValueError(f"Tape line {line_no} in {path} must be an object.")

                request_hash = payload.get("request_hash")
                response = payload.get("response")
                if not isinstance(request_hash, str) or not request_hash:
                    raise ValueError(f"Tape line {line_no} in {path} is missing string request_hash.")
                if not isinstance(response, Mapping):
                    raise ValueError(f"Tape line {line_no} in {path} is missing object response.")

                text = response.get("text")
                meta = response.get("meta")
                normalized = {
                    "text": str(text) if text is not None else "",
                    "meta": dict(meta) if isinstance(meta, Mapping) else {},
                }

                existing = index.get(request_hash)
                if existing is not None and existing != normalized:
                    raise ValueError(
                        f"Tape hash collision with mismatched responses for request_hash={request_hash!r} at line {line_no}."
                    )
                index[request_hash] = normalized
        return index

    def generate(self, prompt: str, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        _, request_hash = _request_from_generate(prompt, kwargs, "replay")

        response = self._responses.get(request_hash)
        if response is None:
            raise TapeReplayMissError(
                f"Tape replay miss for request_hash={request_hash}. Provide a matching tape or record this request first."
            )

        text = response.get("text")
        meta = response.get("meta")
        return str(text) if text is not None else "", dict(meta) if isinstance(meta, Mapping) else {}


__all__ = [
    "TAPE_VERSION",
    "TapeRecorderAdapter",
    "TapeReplayAdapter",
    "TapeReplayMissError",
    "append_tape_line",
    "make_request_hash",
]
