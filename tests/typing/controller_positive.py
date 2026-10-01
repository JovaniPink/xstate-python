from typing import assert_type

from docs.examples.docking_controller import (
    ControllerContext,
    ControllerEvent,
    DockingController,
    DockingGoal,
    FakeDrive,
    Phase,
    TickSample,
    TraceReplay,
)
from xstate import SimulatedClock, State, to_mermaid

replay: TraceReplay[ControllerContext, ControllerEvent, None] = TraceReplay()
controller = DockingController(FakeDrive(), clock=SimulatedClock(), replay=replay)
assert_type(controller.start(DockingGoal("bay")), Phase)
assert_type(controller.tick(TickSample(staged=True)), Phase)
assert_type(controller.cancel(), Phase)
assert_type(controller.advance_time(100), Phase)
assert_type(controller.snapshot, State[ControllerContext, ControllerEvent, None])
assert_type(to_mermaid(controller.machine, snapshot=controller.snapshot), str)
controller.close()

plain_controller = DockingController(FakeDrive(), replay=TraceReplay())
assert_type(plain_controller.phase, Phase)
