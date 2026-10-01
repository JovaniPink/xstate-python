"""Forced controller interleavings and resource failure boundaries."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock, get_ident
from typing import Any

import pytest

from docs.examples.docking_controller import (
    DockingController,
    DockingGoal,
    FakeDrive,
    Phase,
    TickSample,
    TraceReplay,
)
from xstate import Clock, SimulatedClock


class BlockingDrive(FakeDrive):
    def __init__(self, blocked: str = "stage"):
        super().__init__()
        self.blocked = blocked
        self.entered, self.release, self.stopped = Event(), Event(), Event()
        self.lock = Lock()
        self.active = self.maximum = 0
        self.threads = []

    def command(self, name):
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self.commands.append(f"{name}:enter")
            self.threads.append(get_ident())
        try:
            if name == self.blocked and not self.entered.is_set():
                self.entered.set()
                assert self.release.wait(5), "Drive barrier timed out"
        finally:
            with self.lock:
                self.commands.append(f"{name}:exit")
                self.active -= 1
            if name == "stop":
                self.stopped.set()

    def begin(self, goal_id):
        self.command("begin")

    def stage(self, sample):
        self.command("stage")

    def scan(self, sample):
        self.command("scan")

    def dock(self, sample):
        self.command("dock")

    def stop(self):
        self.command("stop")


class DispatchClock(Clock):
    """Deliver a callback already taken by a scheduler, even after cancellation."""

    def __init__(self):
        self.lock = Lock()
        self.callbacks: dict[int, Callable[[], Any]] = {}
        self.next_id = 0

    def set_timeout(self, fn, delay_ms):
        with self.lock:
            timer_id = self.next_id
            self.next_id += 1
            self.callbacks[timer_id] = fn
            return timer_id

    def clear_timeout(self, timeout_id):
        with self.lock:
            self.callbacks.pop(timeout_id, None)

    def take(self):
        with self.lock:
            timer_id = min(self.callbacks)
            return self.callbacks.pop(timer_id)


def test_two_starts_admit_only_one_operation():
    drive = BlockingDrive("begin")
    controller = DockingController(drive, clock=SimulatedClock())
    attempted = Event()

    def second_start():
        attempted.set()
        return controller.start(DockingGoal("second"))

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(controller.start, DockingGoal("first"))
        try:
            assert drive.entered.wait(5)
            second = pool.submit(second_start)
            assert attempted.wait(5)
        finally:
            drive.release.set()
        assert first.result(5) is Phase.STAGING
        with pytest.raises(RuntimeError, match="already active"):
            second.result(5)
    assert controller.snapshot.context.goal_id == "first"
    controller.close()
    assert drive.commands.count("begin:enter") == 1
    assert drive.maximum == 1


def test_concurrent_ticks_complete_in_phase_order():
    drive = BlockingDrive()
    controller = DockingController(drive, clock=SimulatedClock())
    controller.start(DockingGoal("bay"))
    attempted = Event()

    def second_tick():
        attempted.set()
        return controller.tick(TickSample(target_visible=True))

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(controller.tick, TickSample(staged=True))
        try:
            assert drive.entered.wait(5)
            second = pool.submit(second_tick)
            assert attempted.wait(5)
        finally:
            drive.release.set()
        assert first.result(5) is Phase.SCANNING
        assert second.result(5) is Phase.DOCKING
    controller.close()
    assert drive.commands == [
        "begin:enter",
        "begin:exit",
        "stage:enter",
        "stage:exit",
        "scan:enter",
        "scan:exit",
        "stop:enter",
        "stop:exit",
    ]
    assert drive.maximum == 1


@pytest.mark.parametrize("method", ["cancel", "close"])
def test_cleanup_waits_for_inflight_tick_and_allows_fresh_reuse(method):
    drive, clock = BlockingDrive(), SimulatedClock()
    controller = DockingController(drive, clock=clock)
    controller.start(DockingGoal("first"))
    previous = controller.service
    attempted = Event()

    def cleanup():
        attempted.set()
        result = getattr(controller, method)()
        drive.commands.append("cleanup:return")
        return result

    with ThreadPoolExecutor(2) as pool:
        tick = pool.submit(controller.tick, TickSample())
        try:
            assert drive.entered.wait(5)
            closing = pool.submit(cleanup)
            assert attempted.wait(5)
        finally:
            drive.release.set()
        assert tick.result(5) is Phase.STAGING
        closing.result(5)
    assert drive.commands.index("stage:exit") < drive.commands.index("stop:enter")
    assert drive.commands.index("stop:exit") < drive.commands.index("cleanup:return")
    with pytest.raises(RuntimeError, match="active"):
        controller.tick(TickSample())
    controller.close()
    assert drive.maximum == 1
    assert drive.commands.count("stop:enter") == 1
    assert controller.start(DockingGoal("second")) is Phase.STAGING
    assert controller.service is not previous
    assert previous.status == "stopped"
    controller.advance_time(999)
    assert controller.phase is Phase.STAGING
    controller.close()


@pytest.mark.parametrize("first", ["timeout", "cancel"])
def test_timeout_and_cancellation_serialize_terminal_cleanup(first):
    drive, clock = BlockingDrive("stop"), DispatchClock()
    controller = DockingController(drive, clock=clock)
    controller.start(DockingGoal("bay"))
    timeout = clock.take()
    attempted = Event()

    def contender():
        attempted.set()
        return controller.cancel() if first == "timeout" else timeout()

    with ThreadPoolExecutor(2) as pool:
        winner = pool.submit(timeout if first == "timeout" else controller.cancel)
        try:
            assert drive.entered.wait(5)
            waiting = pool.submit(contender)
            assert attempted.wait(5)
        finally:
            drive.release.set()
        winner.result(5)
        waiting.result(5)
    assert controller.phase is (Phase.FAILED if first == "timeout" else Phase.CANCELLED)
    controller.close()
    assert drive.commands.count("stop:enter") == 1
    assert drive.maximum == 1


def test_dispatched_cancelled_timer_is_discarded_before_admission_and_reuse():
    drive, clock, replay = BlockingDrive(), DispatchClock(), TraceReplay()
    controller = DockingController(drive, clock=clock, replay=replay)
    controller.start(DockingGoal("first"))
    old_service = controller.service
    stale = clock.take()
    attempted = Event()

    def dispatched():
        attempted.set()
        stale()

    with ThreadPoolExecutor(2) as pool:
        tick = pool.submit(controller.tick, TickSample(staged=True))
        try:
            assert drive.entered.wait(5)
            timer = pool.submit(dispatched)
            assert attempted.wait(5)
        finally:
            drive.release.set()
        assert tick.result(5) is Phase.SCANNING
        timer.result(5)
    assert [frame.event_name for frame in replay.frames] == [
        "xstate.init",
        "START",
        "TICK",
    ]
    controller.close()
    controller.start(DockingGoal("second"))
    before = len(replay.frames), list(drive.commands)
    stale()
    assert (len(replay.frames), drive.commands) == before
    assert old_service.status == "stopped"
    assert controller.phase is Phase.STAGING
    controller.close()


@pytest.mark.parametrize("source", ["drive", "inspector", "subscriber"])
@pytest.mark.parametrize("method", ["start", "tick", "cancel", "close", "advance_time"])
def test_callback_reads_are_allowed_and_mutating_reentry_is_rejected(source, method):
    controller = None
    observed = []

    def callback():
        assert controller is not None
        observed.append((controller.phase.value, controller.snapshot.value))
        arguments = {
            "start": (DockingGoal("nested"),),
            "tick": (TickSample(),),
            "cancel": (),
            "close": (),
            "advance_time": (1,),
        }
        with pytest.raises(RuntimeError, match="reenter"):
            getattr(controller, method)(*arguments[method])

    class ReadingDrive(FakeDrive):
        def stage(self, sample):
            callback()
            super().stage(sample)

    class ReadingReplay(TraceReplay):
        def capture(self, trace):
            callback()
            super().capture(trace)

    replay = ReadingReplay() if source == "inspector" else None
    drive = ReadingDrive() if source == "drive" else FakeDrive()
    controller = DockingController(drive, clock=SimulatedClock(), replay=replay)
    controller.start(DockingGoal("bay"))
    if source == "subscriber":
        # Subscription's immediate observation is not an executing facade call.
        controller.service.subscribe(
            lambda state: callback() if state.event.name == "TICK" else None
        )
    assert controller.tick(TickSample()) is Phase.STAGING
    assert observed and all(phase == value for phase, value in observed)
    assert drive.commands == ["begin", "stage"]
    assert controller.cancel() is Phase.CANCELLED
    controller.close()


def test_default_thread_clock_delivers_timeout_and_releases_execution():
    drive = BlockingDrive("unused")
    controller = DockingController(drive)
    try:
        assert controller.start(DockingGoal("bay")) is Phase.STAGING
        assert drive.stopped.wait(5), "Real timer did not deliver"
        assert controller.phase is Phase.FAILED
        assert drive.threads[0] != drive.threads[-1]
    finally:
        controller.close()
    assert drive.maximum == 1
    assert drive.commands.count("stop:enter") == 1


@pytest.mark.parametrize(
    "milliseconds", [-1, float("inf"), float("-inf"), float("nan")]
)
def test_simulated_time_rejects_invalid_values_without_advancing(milliseconds):
    clock = SimulatedClock()
    controller = DockingController(FakeDrive(), clock=clock)
    with pytest.raises(ValueError, match="finite"):
        controller.advance_time(milliseconds)
    assert clock.now() == 0
    assert controller.advance_time(0) is Phase.READY


def test_time_advancement_requires_simulated_clock():
    controller = DockingController(FakeDrive())
    with pytest.raises(RuntimeError, match="SimulatedClock"):
        controller.advance_time(1)
    controller.close()


def test_external_snapshot_read_waits_for_the_admitted_command():
    drive = BlockingDrive()
    controller = DockingController(drive, clock=SimulatedClock())
    controller.start(DockingGoal("bay"))
    attempted = Event()

    def observe():
        attempted.set()
        snapshot = controller.snapshot
        drive.commands.append("observation:return")
        return snapshot

    with ThreadPoolExecutor(2) as pool:
        tick = pool.submit(controller.tick, TickSample(staged=True))
        try:
            assert drive.entered.wait(5)
            reading = pool.submit(observe)
            assert attempted.wait(5)
        finally:
            drive.release.set()
        assert tick.result(5) is Phase.SCANNING
        assert reading.result(5).value == "scanning"
    controller.close()
    assert drive.commands.index("stage:exit") < drive.commands.index(
        "observation:return"
    )


def test_command_exception_releases_a_waiting_close_and_ownership():
    class FailingDrive(BlockingDrive):
        def stage(self, sample):
            self.command("stage")
            raise RuntimeError("drive failure")

    drive = FailingDrive()
    controller = DockingController(drive, clock=SimulatedClock())
    controller.start(DockingGoal("first"))
    attempted = Event()

    def close():
        attempted.set()
        controller.close()

    with ThreadPoolExecutor(2) as pool:
        tick = pool.submit(controller.tick, TickSample(staged=True))
        try:
            assert drive.entered.wait(5)
            closing = pool.submit(close)
            assert attempted.wait(5)
        finally:
            drive.release.set()
        with pytest.raises(RuntimeError, match="drive failure"):
            tick.result(5)
        closing.result(5)
    assert controller.phase is Phase.SCANNING
    assert controller.service.status == "stopped"
    assert drive.commands.index("stage:exit") < drive.commands.index("stop:enter")
    assert drive.maximum == 1
    assert controller.start(DockingGoal("second")) is Phase.STAGING
    controller.close()
