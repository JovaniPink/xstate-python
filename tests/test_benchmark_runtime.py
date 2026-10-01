"""The benchmark must be runnable; timings are observations, never CI gates."""

import json
import subprocess
import sys
from pathlib import Path


def test_benchmark_reports_separate_workloads_and_environment():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.benchmark_runtime",
            "--samples",
            "5",
            "--warmup",
            "1",
            "--format-samples",
            "2",
            "--json",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["python"] and report["platform"] and report["implementation"]
    assert [row["workload"] for row in report["results"]] == [
        "pure_empty",
        "sync_empty",
        "pure_list_1000",
        "pure_immutable_tuple_1000",
        "pure_microstep_trace",
        "sync_inspection_capture",
        "markdown_format_200_frames",
    ]
    for row in report["results"]:
        assert row["samples"] == (2 if row["unit"] == "us/report" else 5)
        assert row["median"] >= 0 and row["p95"] >= row["median"]
        assert row["p99"] >= row["p95"]
