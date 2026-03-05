from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.verifier.verify_output import verify_output


def _contract() -> dict[str, object]:
    return {
        "type": "jsonschema",
        "schema_id": "contract.cluster.v1",
        "schema": {
            "type": "object",
            "required": ["status", "count"],
            "properties": {
                "status": {"type": "string"},
                "count": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    }


def test_failure_clusters_are_stable_for_same_signature() -> None:
    first = verify_output(mode="json", y_text='{"status":"ok","count":"1"}', contract=_contract())
    second = verify_output(mode="json", y_text='{"status":"ok","count":"2"}', contract=_contract())

    assert first["failure_cluster_id"]
    assert first["failure_cluster_id"] == second["failure_cluster_id"]


def test_failure_clusters_change_for_different_violations() -> None:
    parse_fail = verify_output(mode="json", y_text="not-json", contract=None)
    schema_fail = verify_output(mode="json", y_text='{"status":"ok","count":"1"}', contract=_contract())

    assert parse_fail["failure_cluster_id"]
    assert schema_fail["failure_cluster_id"]
    assert parse_fail["failure_cluster_id"] != schema_fail["failure_cluster_id"]
