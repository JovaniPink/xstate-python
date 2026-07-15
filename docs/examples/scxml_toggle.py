#!/usr/bin/env python3
"""Import and run a self-contained SCXML toggle machine."""

from pathlib import Path

from xstate.scxml import scxml_to_machine


def main() -> None:
    source = Path(__file__).with_name("scxml_toggle.scxml")
    machine = scxml_to_machine(source)

    state = machine.initial_state
    assert state.matches("off")

    state = machine.transition(state, "TOGGLE")
    assert state.matches("on")

    state = machine.transition(state, "TOGGLE")
    assert state.matches("off")

    print("SCXML toggle returned to off")


if __name__ == "__main__":
    main()
