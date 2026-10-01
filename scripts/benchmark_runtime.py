#!/usr/bin/env python3
"""Local warmed baselines, with no timing thresholds or application I/O.

Run from the repository root:
    poetry run python -m scripts.benchmark_runtime --samples 3000 --json
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypedDict

from docs.examples.docking_controller import (
    DockingController,
    DockingGoal,
    TickSample,
    TraceReplay,
)
from xstate import (
    Machine,
    MacrostepTrace,
    SimulatedClock,
    dataclass_context,
    get_microsteps,
    interpret,
)


@dataclass(frozen=True)
class ImmutableContext:
    values: tuple[int, ...]


@dataclass
class CountingDrive:
    """Constant-memory bookkeeping; no application I/O or command retention."""

    commands: int = 0

    def begin(self, goal_id: str) -> None:
        self.commands += 1

    def stage(self, sample: TickSample) -> None:
        self.commands += 1

    def scan(self, sample: TickSample) -> None:
        self.commands += 1

    def dock(self, sample: TickSample) -> None:
        self.commands += 1

    def stop(self) -> None:
        self.commands += 1


class Result(TypedDict):
    workload: str
    unit: str
    samples: int
    warmup: int
    median: float
    p95: float
    p99: float


class BenchmarkReport(TypedDict):
    python: str
    implementation: str
    platform: str
    machine: str
    percentiles: str
    results: list[Result]


def _measure(
    name: str,
    operation: Callable[[], object],
    *,
    samples: int,
    warmup: int,
    divisor: int = 2,
) -> Result:
    for _ in range(warmup):
        operation()
    timings = []
    for _ in range(samples):
        before = time.perf_counter_ns()
        operation()
        timings.append((time.perf_counter_ns() - before) / (1_000 * divisor))
    timings.sort()
    return {
        "workload": name,
        "unit": "us/report" if divisor == 1 else "us/event-equivalent",
        "samples": samples,
        "warmup": warmup,
        "median": statistics.median(timings),
        "p95": timings[math.ceil(samples * 0.95) - 1],
        "p99": timings[math.ceil(samples * 0.99) - 1],
    }


def _machine(*, large_list: bool = False, immutable: bool = False) -> Machine:
    return Machine(
        {
            "id": "benchmark",
            "context": ImmutableContext(tuple(range(1_000)))
            if immutable
            else {"values": list(range(1_000))}
            if large_list
            else {},
            "initial": "a",
            "states": {"a": {"on": {"GO": "b"}}, "b": {"on": {"BACK": "a"}}},
        },
        context_adapter=dataclass_context() if immutable else None,
    )


def _pure_cycle(machine: Machine, *, traced: bool = False) -> Callable[[], None]:
    state = machine.initial_state

    def cycle() -> None:
        nonlocal state
        for event in ("GO", "BACK"):
            state = (
                get_microsteps(machine, state, event)[-1].snapshot
                if traced
                else machine.transition(state, event)
            )

    return cycle


def benchmark(samples: int, warmup: int, format_samples: int) -> list[Result]:
    results = []
    results.append(
        _measure("pure_empty", _pure_cycle(_machine()), samples=samples, warmup=warmup)
    )
    service = interpret(_machine()).start()
    try:

        def sync_cycle() -> None:
            service.send("GO")
            service.send("BACK")

        results.append(
            _measure("sync_empty", sync_cycle, samples=samples, warmup=warmup)
        )
    finally:
        service.stop()
    controller = DockingController(CountingDrive(), clock=SimulatedClock())
    sample = TickSample()
    try:
        controller.start(DockingGoal("benchmark"))

        def controller_cycle() -> None:
            controller.tick(sample)
            controller.tick(sample)

        results.append(
            _measure(
                "controller_serialized_tick",
                controller_cycle,
                samples=samples,
                warmup=warmup,
            )
        )
    finally:
        controller.close()
    for name, machine in (
        ("pure_list_1000", _machine(large_list=True)),
        ("pure_immutable_tuple_1000", _machine(immutable=True)),
        ("pure_microstep_trace", _machine()),
    ):
        results.append(
            _measure(
                name,
                _pure_cycle(machine, traced=name == "pure_microstep_trace"),
                samples=samples,
                warmup=warmup,
            )
        )

    # Rolling capture measures retention on every event rather than mostly
    # measuring the example recorder's fast path after its 200-frame limit.
    captured: deque[MacrostepTrace] = deque(maxlen=200)
    inspected = interpret(_machine(), inspect=captured.append).start()
    try:

        def capture_cycle() -> None:
            inspected.send("GO")
            inspected.send("BACK")

        results.append(
            _measure(
                "sync_inspection_capture", capture_cycle, samples=samples, warmup=warmup
            )
        )
    finally:
        inspected.stop()

    # Report formatting is measured separately, outside interpreter callbacks,
    # in microseconds per whole report rather than per event-equivalent.
    machine = _machine()
    replay: TraceReplay = TraceReplay()
    replay_service = interpret(machine, inspect=replay.capture).start()
    try:
        for _ in range(100):
            replay_service.send("GO")
            replay_service.send("BACK")
    finally:
        replay_service.stop()
    results.append(
        _measure(
            "markdown_format_200_frames",
            lambda: replay.to_markdown(machine),
            samples=format_samples,
            warmup=1,
            divisor=1,
        )
    )
    return results


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Use a positive integer")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=_positive_int, default=3_000)
    parser.add_argument("--warmup", type=_positive_int, default=200)
    parser.add_argument("--format-samples", type=_positive_int, default=20)
    parser.add_argument("--json", action="store_true")
    options = parser.parse_args()
    report: BenchmarkReport = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "percentiles": (
            "nearest rank; two-event cycles divided by two; formatting per report"
        ),
        "results": benchmark(options.samples, options.warmup, options.format_samples),
    }
    if options.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['implementation']} {report['python']} on {report['platform']}")
        print(report["percentiles"])
        print("workload | samples | unit | median | p95 | p99")
        for result in report["results"]:
            print(
                f"{result['workload']} | {result['samples']} | {result['unit']} | "
                f"{result['median']:.2f} | {result['p95']:.2f} | {result['p99']:.2f}"
            )


if __name__ == "__main__":
    main()
