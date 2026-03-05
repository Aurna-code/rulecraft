from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rulecraft.analysis.counterexamples import generate_counterexamples


def test_generate_counterexamples_is_deterministic_for_same_seed() -> None:
    task = {
        "task_id": "task-json",
        "prompt": "Return JSON with fields status and count.",
        "mode": "json",
        "bucket_key": "contracts",
        "flow_tags": ["batch", "contract"],
        "contract": {"type": "jsonschema", "schema_id": "contract.status_count.v1", "schema": {"type": "object"}},
    }

    first = generate_counterexamples(task, cluster_id="fc_schema", seed=1337, n=3)
    second = generate_counterexamples(task, cluster_id="fc_schema", seed=1337, n=3)

    assert [item["task_id"] for item in first] == [item["task_id"] for item in second]
    assert [item["prompt"] for item in first] == [item["prompt"] for item in second]


def test_generate_counterexamples_preserve_core_fields_and_unique_ids() -> None:
    task = {
        "task_id": "task-json",
        "prompt": "Return JSON with fields status and count.",
        "mode": "json",
        "bucket_key": "contracts",
        "flow_tags": ["batch", "contract"],
        "contract": {"type": "jsonschema", "schema_id": "contract.status_count.v1", "schema": {"type": "object"}},
    }
    generated = generate_counterexamples(task, cluster_id="fc_schema", seed=7, n=3)

    ids = [item["task_id"] for item in generated]
    assert len(ids) == len(set(ids))
    assert all(task_id.startswith("task-json__ce_fc_schema_") for task_id in ids)
    for item in generated:
        assert item["mode"] == "json"
        assert item["bucket_key"] == "contracts"
        assert item["flow_tags"] == ["batch", "contract"]
        assert item["contract"] == task["contract"]
