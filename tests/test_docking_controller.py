"""Application behavior and structural replay, independent of engine internals."""

import subprocess
import sys
from pathlib import Path

import pytest

from docs.examples.docking_controller import (
    DockingController,
    DockingGoal,
    FakeDrive,
    Phase,
    TickSample,
    TraceReplay,
)
from xstate import Machine, SimulatedClock, interpret, raise_

ROOT = Path(__file__).resolve().parents[1]


def test_ticks_control_only_the_current_phase_and_keep_resources_out_of_context():
    drive, clock, replay = FakeDrive(), SimulatedClock(), TraceReplay()
    controller = DockingController(drive, clock=clock, replay=replay)
    phases = []
    try:
        assert controller.phase is Phase.READY
        assert controller.start(DockingGoal("bay-7")) is Phase.STAGING
        controller.service.subscribe(lambda state: phases.append(state.value))
        for sample in [
            TickSample(),
            TickSample(staged=True),
            TickSample(),
            TickSample(target_visible=True),
            TickSample(),
            TickSample(docked=True),
        ]:
            before = len(drive.commands)
            controller.tick(sample)
            added = drive.commands[before:]
            assert (
                len(
                    [
                        command
                        for command in added
                        if command in {"stage", "scan", "dock"}
                    ]
                )
                == 1
            )
        assert phases == [
            "staging",
            "staging",
            "scanning",
            "scanning",
            "docking",
            "docking",
            "completed",
        ]
        assert drive.commands == [
            "begin",
            "stage",
            "stage",
            "scan",
            "scan",
            "dock",
            "dock",
            "stop",
        ]
        assert controller.service.state.context.goal_id == "bay-7"
        assert "bay-7" not in replay.to_markdown(controller.machine)
        assert controller.phase is Phase.COMPLETED
    finally:
        controller.close()
    assert controller.service.status == "stopped"


@pytest.mark.parametrize("phase", [Phase.STAGING, Phase.SCANNING, Phase.DOCKING])
def test_phase_timeouts_stop_control_and_cancel_timers(phase):
    drive, clock, replay = FakeDrive(), SimulatedClock(), TraceReplay()
    controller = DockingController(drive, clock=clock, replay=replay)
    controller.start(DockingGoal("bay"))
    if phase in {Phase.SCANNING, Phase.DOCKING}:
        clock.increment(900)
        controller.tick(TickSample(staged=True))
    if phase is Phase.DOCKING:
        clock.increment(900)
        controller.tick(TickSample(target_visible=True))
    assert controller.phase is phase
    clock.increment(999)
    assert controller.phase is phase
    clock.increment(1)
    assert controller.phase is Phase.FAILED
    assert drive.commands[-1] == "stop"
    controller.close()
    frames = len(replay.frames)
    clock.increment(100_000)
    assert len(replay.frames) == frames
    assert controller.service.status == "stopped"


def test_cancel_cleanup_and_new_operation_use_fresh_interpreter():
    drive, clock = FakeDrive(), SimulatedClock()
    controller = DockingController(drive, clock=clock)
    controller.start(DockingGoal("first"))
    first = controller.service
    clock.increment(900)
    assert controller.cancel() is Phase.CANCELLED
    assert controller.start(DockingGoal("second")) is Phase.STAGING
    assert first.status == "stopped"
    assert first is not controller.service
    assert controller.service.state.context.goal_id == "second"
    clock.increment(999)
    assert controller.phase is Phase.STAGING
    controller.close()
    clock.increment(100_000)
    assert controller.phase is Phase.STAGING
    assert drive.commands == ["begin", "stop", "begin", "stop"]


def test_fault_sample_fails_without_polling_the_next_phase():
    drive = FakeDrive()
    controller = DockingController(drive, clock=SimulatedClock())
    try:
        controller.start(DockingGoal("bay"))
        assert controller.tick(TickSample(staged=True, fault=True)) is Phase.FAILED
        assert drive.commands == ["begin", "stop"]
        with pytest.raises(RuntimeError, match="active"):
            controller.tick(TickSample())
    finally:
        controller.close()


def test_action_failure_leaves_chart_destination_committed_and_can_be_cleaned_up():
    class FailingDrive(FakeDrive):
        def stage(self, sample):
            super().stage(sample)
            raise RuntimeError("command failed")

    drive, replay = FailingDrive(), TraceReplay()
    controller = DockingController(drive, clock=SimulatedClock(), replay=replay)
    try:
        controller.start(DockingGoal("bay"))
        with pytest.raises(RuntimeError, match="command failed"):
            controller.tick(TickSample(staged=True))
        assert controller.phase is Phase.SCANNING
        assert replay.frames[-1].snapshot.value == "scanning"
        assert drive.commands == ["begin", "stage"]
    finally:
        controller.close()
    assert drive.commands[-1] == "stop"
    assert controller.service.status == "stopped"


def test_replay_preserves_eventless_and_internal_event_order_without_data():
    replay = TraceReplay()
    machine = Machine(
        {
            "id": "replay",
            "context": {"secret": "CONTEXT_SECRET"},
            "initial": "a",
            "states": {
                "a": {
                    "on": {
                        "GO": {
                            "target": "b",
                            "actions": [raise_("IGNORED"), raise_("NEXT")],
                        }
                    }
                },
                "b": {"always": "c"},
                "c": {"on": {"NEXT": "d"}},
                "d": {},
            },
        }
    )
    service = interpret(machine, inspect=replay.capture).start()
    try:
        service.send({"type": "GO", "secret": "PAYLOAD_SECRET"})
        assert [frame.snapshot.value for frame in replay.frames] == [
            "a",
            "b",
            "c",
            "c",
            "d",
        ]
        assert [frame.event_name for frame in replay.frames] == [
            "xstate.init",
            "GO",
            "GO",
            "IGNORED",
            "NEXT",
        ]
        assert replay.frames[3].transitions == ()
        report = replay.to_markdown(machine)
        assert report.count("```mermaid") == 5
        assert "| xstate.init | replay | replay.a |" in report
        assert "| always | replay.b | replay.c |" in report
        assert "| IGNORED | — | — |" in report
        assert "CONTEXT_SECRET" not in report and "PAYLOAD_SECRET" not in report
        assert "before side effects" in report
    finally:
        service.stop()


def test_replay_lists_all_parallel_transitions_in_selection_order():
    replay = TraceReplay()
    machine = Machine(
        {
            "id": "parallel-replay",
            "type": "parallel",
            "states": {
                key: {"initial": "a", "states": {"a": {"on": {"GO": "b"}}, "b": {}}}
                for key in ("left", "right")
            },
        }
    )
    service = interpret(machine, inspect=replay.capture).start()
    try:
        service.send("GO")
        transitions = replay.frames[-1].transitions
        assert [transition.source_id for transition in transitions] == [
            "parallel-replay.left.a",
            "parallel-replay.right.a",
        ]
        report = replay.to_markdown(machine)
        assert report.index("| GO | parallel-replay.left.a") < report.index(
            "| GO | parallel-replay.right.a"
        )
        assert 'state "b [active]"' in report
    finally:
        service.stop()


def test_replay_is_bounded_and_escapes_table_cells():
    replay = TraceReplay()
    machine = Machine({"id": "bounded", "initial": "a", "states": {"a": {}}})
    service = interpret(machine, inspect=replay.capture).start()
    try:
        service.send("ODD|EVENT\n<text>")
        for _ in range(204):
            service.send("IGNORED")
        assert len(replay.frames) == 200
        assert replay.dropped_frames == 6
        report = replay.to_markdown(machine)
        assert "Truncated: 6 additional frames" in report
        assert "ODD|EVENT\n<text>" not in report
        assert "ODD&#124;EVENT<br>&lt;text&gt;" in report
    finally:
        service.stop()


@pytest.mark.parametrize(
    "scenario, expected",
    [("success", "completed"), ("timeout", "failed"), ("cancel", "cancelled")],
)
def test_controller_cli_runs_and_writes_opt_in_replay(tmp_path, scenario, expected):
    report = tmp_path / "trace.md"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "docs/examples/docking_controller.py"),
            "--scenario",
            scenario,
            "--trace-md",
            str(report),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert expected in result.stdout
    assert f'state "{expected} [active]"' in report.read_text()
