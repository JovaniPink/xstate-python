#!/usr/bin/env python3
"""A typed application facade over a JSON chart and the existing sync runtime.

Run: poetry run python docs/examples/docking_controller.py --trace-md trace.md
This deterministic example issues fake drive commands; it does no hardware I/O.
"""

from __future__ import annotations

import argparse
import html
import json
import math
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Any, Literal, Protocol, TypedDict

from xstate import (
    Clock,
    HandlerArgs,
    Interpreter,
    Machine,
    MacrostepTrace,
    SimulatedClock,
    State,
    ThreadClock,
    TransitionTrace,
    assign,
    dataclass_context,
    interpret,
    to_mermaid,
)


class Phase(StrEnum):
    READY = "ready"
    STAGING = "staging"
    SCANNING = "scanning"
    DOCKING = "docking"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_PHASES = frozenset({Phase.STAGING, Phase.SCANNING, Phase.DOCKING})


@dataclass(frozen=True)
class DockingGoal:
    station_id: str

    def __post_init__(self) -> None:
        if not self.station_id:
            raise ValueError("A docking goal needs a station ID")


@dataclass(frozen=True)
class TickSample:
    staged: bool = False
    target_visible: bool = False
    docked: bool = False
    fault: bool = False


@dataclass(frozen=True)
class ControllerContext:
    goal_id: str = ""


class StartEvent(TypedDict):
    type: Literal["START"]
    goal: DockingGoal


class TickEvent(TypedDict):
    type: Literal["TICK"]
    sample: TickSample


class CancelEvent(TypedDict):
    type: Literal["CANCEL"]


type ControllerEvent = StartEvent | TickEvent | CancelEvent
type ControllerArgs = HandlerArgs[ControllerContext, ControllerEvent, None]


class Drive(Protocol):
    """The application owns this resource, outside snapshot context."""

    def begin(self, goal_id: str) -> None: ...
    def stage(self, sample: TickSample) -> None: ...
    def scan(self, sample: TickSample) -> None: ...
    def dock(self, sample: TickSample) -> None: ...
    def stop(self) -> None: ...


@dataclass
class FakeDrive:
    commands: list[str] = field(default_factory=list)

    def begin(self, goal_id: str) -> None:
        self.commands.append("begin")

    def stage(self, sample: TickSample) -> None:
        self.commands.append("stage")

    def scan(self, sample: TickSample) -> None:
        self.commands.append("scan")

    def dock(self, sample: TickSample) -> None:
        self.commands.append("dock")

    def stop(self) -> None:
        self.commands.append("stop")


@dataclass(frozen=True)
class ReplayFrame[ContextT, EventDataT, OutputT]:
    event_name: str
    snapshot: State[ContextT, EventDataT, OutputT]
    transitions: tuple[TransitionTrace, ...]
    initialization: bool = False


class TraceReplay[ContextT = Any, EventDataT = Any, OutputT = Any]:
    """Bounded example recorder. Capture now; format after execution."""

    def __init__(self) -> None:
        self.frames: list[ReplayFrame[ContextT, EventDataT, OutputT]] = []
        self.dropped_frames = 0

    def capture(self, trace: MacrostepTrace[ContextT, EventDataT, OutputT]) -> None:
        if trace.microsteps:
            for index, step in enumerate(trace.microsteps):
                self._append(
                    ReplayFrame(
                        step.event.name,
                        step.snapshot,
                        step.transitions,
                        trace.previous_snapshot is None and index == 0,
                    )
                )
        else:
            # Restoration can produce an initialization observation without
            # microsteps. It still deserves a frame, without invented edges.
            self._append(
                ReplayFrame(
                    trace.event.name,
                    trace.snapshot,
                    (),
                    trace.previous_snapshot is None,
                )
            )

    def _append(self, frame: ReplayFrame[ContextT, EventDataT, OutputT]) -> None:
        if len(self.frames) < 200:
            self.frames.append(frame)
        else:
            self.dropped_frames += 1

    def to_markdown(self, machine: Machine[ContextT, EventDataT, OutputT]) -> str:
        lines = [
            "# Chart-state replay",
            "",
            "Frames are chart-state observations before side effects complete. "
            "They do not prove command success or external rollback. "
            "Context and payload contents are omitted.",
            "",
            f"Captured {len(self.frames)} frames (limit: 200).",
            "",
        ]
        if self.dropped_frames:
            lines.extend(
                [
                    f"Truncated: {self.dropped_frames} additional frames were omitted.",
                    "",
                ]
            )
        for index, frame in enumerate(self.frames, 1):
            label = (
                "Initialization" if frame.initialization else _cell(frame.event_name)
            )
            lines.extend(
                [
                    f"## Frame {index}: {label}",
                    "",
                    "```mermaid",
                    to_mermaid(machine, snapshot=frame.snapshot).rstrip(),
                    "```",
                    "",
                    "| Event | Source ID | Target IDs | Active states |",
                    "|---|---|---|---|",
                ]
            )
            active = _cell(
                ", ".join(sorted(node.id for node in frame.snapshot.configuration))
            )
            if not frame.transitions:
                lines.append(f"| {_cell(frame.event_name)} | — | — | {active} |")
            for transition in frame.transitions:
                event = _cell(
                    transition.event_type
                    or ("xstate.init" if frame.initialization else "always")
                )
                targets = _cell(", ".join(transition.target_ids)) or "—"
                lines.append(
                    f"| {event} | {_cell(transition.source_id)} | "
                    f"{targets} | {active} |"
                )
            lines.append("")
        return "\n".join(lines)


def _cell(value: str) -> str:
    return (
        html.escape(value)
        .replace("|", "&#124;")
        .replace("\n", "<br>")
        .replace("`", "&#96;")
    )


def _sample(args: ControllerArgs) -> TickSample:
    data = args.event.data if args.event is not None else None
    if isinstance(data, dict) and data["type"] == "TICK":
        return data["sample"]
    raise ValueError("Tick handlers require a TICK sample")


def _remember_goal(args: ControllerArgs) -> dict[str, object]:
    data = args.event.data if args.event is not None else None
    if isinstance(data, dict) and data["type"] == "START":
        return {"goal_id": data["goal"].station_id}
    raise ValueError("START requires a docking goal")


@dataclass
class _Timeout:
    underlying_id: int | None = None


class _SerializedClock(Clock):
    """Admit timer delivery before interpreter entry; invalidate cancelled work."""

    def __init__(
        self,
        clock: Clock,
        lock: RLock,
        deliver: Callable[[Callable[[], Any]], None],
    ) -> None:
        self._clock, self._lock, self._deliver = clock, lock, deliver
        self._next_id = 0
        self._timeouts: dict[int, _Timeout] = {}

    def set_timeout(self, fn: Callable[[], Any], delay_ms: float) -> int:
        with self._lock:
            timer_id = self._next_id
            self._next_id += 1
            token = _Timeout()
            self._timeouts[timer_id] = token

            def callback() -> None:
                with self._lock:
                    if self._timeouts.get(timer_id) is not token:
                        return
                    del self._timeouts[timer_id]
                    self._deliver(fn)

            try:
                token.underlying_id = self._clock.set_timeout(callback, delay_ms)
            except BaseException:
                self._timeouts.pop(timer_id, None)
                raise
            return timer_id

    def clear_timeout(self, timeout_id: int) -> None:
        with self._lock:
            token = self._timeouts.pop(timeout_id, None)
            if token is not None and token.underlying_id is not None:
                self._clock.clear_timeout(token.underlying_id)


class DockingController:
    """Serialized callers and timers; each operation gets a fresh interpreter."""

    def __init__(
        self,
        drive: Drive,
        *,
        clock: Clock | None = None,
        replay: TraceReplay[ControllerContext, ControllerEvent, None] | None = None,
    ) -> None:
        self.drive = drive
        self.clock = clock if clock is not None else ThreadClock()
        self.replay = replay
        self._lock = RLock()
        self._executing = False
        self._cleanup_pending = False
        self._runtime_clock = _SerializedClock(self.clock, self._lock, self._deliver)
        config = json.loads(Path(__file__).with_suffix(".json").read_text())
        config["context"] = ControllerContext()
        self.machine: Machine[ControllerContext, ControllerEvent, None] = Machine(
            config,
            actions={
                "rememberGoal": assign(_remember_goal),
                "begin": self._begin,
                "stage": self._stage,
                "scan": self._scan,
                "dock": self._dock,
                "halt": self._halt,
            },
            guards={
                "fault": self._fault,
                "staged": self._staged,
                "targetVisible": self._target_visible,
                "docked": self._docked,
            },
            delays={"phaseTimeout": 1_000},
            context_adapter=dataclass_context(),
            strict=True,
        )
        self._service: Interpreter[ControllerContext, ControllerEvent, None] | None = (
            None
        )

    @property
    def service(self) -> Interpreter[ControllerContext, ControllerEvent, None]:
        """Advanced diagnostics; direct mutation bypasses facade serialization."""
        with self._lock:
            if self._service is None:
                raise RuntimeError("Start an operation first")
            return self._service

    @property
    def snapshot(self) -> State[ControllerContext, ControllerEvent, None]:
        with self._lock:
            return self.service.state

    @property
    def phase(self) -> Phase:
        with self._lock:
            if self._service is None:
                return Phase.READY
            value = self._service.state.value
            if not isinstance(value, str):
                raise TypeError("This example requires a flat chart")
            return Phase(value)

    def _require_idle(self) -> None:
        if self._executing:
            raise RuntimeError("Controller callbacks cannot reenter mutating methods")

    @contextmanager
    def _execution(self) -> Iterator[None]:
        with self._lock:
            self._require_idle()
            self._executing = True
            try:
                yield
            finally:
                self._executing = False

    def _deliver(self, callback: Callable[[], Any]) -> None:
        with self._execution():
            callback()

    def start(self, goal: DockingGoal) -> Phase:
        with self._execution():
            if self._service is not None:
                if self._service.status == "running" and self.phase in ACTIVE_PHASES:
                    raise RuntimeError("An operation is already active")
                self._close_current()
            self._service = interpret(
                self.machine,
                clock=self._runtime_clock,
                inspect=self.replay.capture if self.replay is not None else None,
            )
            try:
                self._service.start()
                event: StartEvent = {"type": "START", "goal": goal}
                self._service.send(event)
            except BaseException as startup_error:
                try:
                    self._close_current()
                except BaseException as cleanup_error:
                    raise cleanup_error from startup_error
                raise
            return self.phase

    def tick(self, sample: TickSample) -> Phase:
        with self._execution():
            if self.service.status != "running" or self.phase not in ACTIVE_PHASES:
                raise RuntimeError("Tick requires an active operation")
            event: TickEvent = {"type": "TICK", "sample": sample}
            self.service.send(event)
            return self.phase

    def cancel(self) -> Phase:
        with self._execution():
            event: CancelEvent = {"type": "CANCEL"}
            self.service.send(event)
            return self.phase

    def advance_time(self, milliseconds: float) -> Phase:
        """Advance the exclusively owned simulated clock under the same lock."""
        with self._lock:
            self._require_idle()
            if not isinstance(self.clock, SimulatedClock):
                raise RuntimeError("Time advancement requires a SimulatedClock")
            if not math.isfinite(milliseconds) or milliseconds < 0:
                raise ValueError("Use finite, nonnegative milliseconds")
            # Increment delivers callbacks inline. Each callback owns its own
            # execution boundary while this outer lock prevents other callers.
            self.clock.increment(milliseconds)
            return self.phase

    def close(self) -> None:
        with self._execution():
            self._close_current()

    def _close_current(self) -> None:
        try:
            self._stop_drive()
        finally:
            if self._service is not None:
                self._service.stop()

    def _stop_drive(self) -> None:
        if self._cleanup_pending:
            self.drive.stop()
            self._cleanup_pending = False

    def _begin(self, args: ControllerArgs) -> None:
        self._cleanup_pending = True
        self.drive.begin(args.context.goal_id)

    def _stage(self, args: ControllerArgs) -> None:
        self.drive.stage(_sample(args))

    def _scan(self, args: ControllerArgs) -> None:
        self.drive.scan(_sample(args))

    def _dock(self, args: ControllerArgs) -> None:
        self.drive.dock(_sample(args))

    def _halt(self, args: ControllerArgs) -> None:
        self._stop_drive()

    def _fault(self, args: ControllerArgs) -> bool:
        return _sample(args).fault

    def _staged(self, args: ControllerArgs) -> bool:
        return _sample(args).staged

    def _target_visible(self, args: ControllerArgs) -> bool:
        return _sample(args).target_visible

    def _docked(self, args: ControllerArgs) -> bool:
        return _sample(args).docked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", choices=("success", "timeout", "cancel"), default="success"
    )
    parser.add_argument(
        "--trace-md", type=Path, help="Write structural Markdown replay after execution"
    )
    options = parser.parse_args()
    clock, drive = SimulatedClock(), FakeDrive()
    replay: TraceReplay[ControllerContext, ControllerEvent, None] | None = (
        TraceReplay() if options.trace_md else None
    )
    controller = DockingController(drive, clock=clock, replay=replay)
    try:
        controller.start(DockingGoal("demo-bay"))
        if options.scenario == "success":
            for sample in (
                TickSample(),
                TickSample(staged=True),
                TickSample(),
                TickSample(target_visible=True),
                TickSample(),
                TickSample(docked=True),
            ):
                controller.tick(sample)
                controller.advance_time(100)
        elif options.scenario == "timeout":
            controller.tick(TickSample())
            controller.advance_time(1_000)
        else:
            controller.tick(TickSample())
            controller.cancel()
        print(
            f"{options.scenario}: {controller.phase.value}; "
            f"commands: {', '.join(drive.commands)}"
        )
    finally:
        controller.close()
    if replay is not None:
        options.trace_md.write_text(replay.to_markdown(controller.machine))
        print(f"Replay: {options.trace_md}")


if __name__ == "__main__":
    main()
