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
from xstate import SimulatedClock, to_mermaid

replay: TraceReplay[ControllerContext, ControllerEvent, None] = TraceReplay()
controller = DockingController(FakeDrive(), clock=SimulatedClock(), replay=replay)
assert_type(controller.start(DockingGoal("bay")), Phase)
assert_type(controller.tick(TickSample(staged=True)), Phase)
assert_type(controller.cancel(), Phase)
assert_type(to_mermaid(controller.machine, snapshot=controller.service.state), str)
controller.close()

plain_controller = DockingController(FakeDrive(), replay=TraceReplay())
assert_type(plain_controller.phase, Phase)
