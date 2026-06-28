from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xstate.machine import Machine
    from xstate.state_node import StateNode
    from xstate.transition import Transition

__all__ = ["to_mermaid"]


def to_mermaid(machine: Machine) -> str:
    """Return a dependency-free Mermaid ``stateDiagram-v2`` representation."""
    lines = ["stateDiagram-v2"]
    if machine.root.initial_transition is not None:
        for target in machine.root.initial.target:
            lines.append(f"  [*] --> {_alias(target)}")
    _emit_states(machine.root, lines, indent="  ")
    _emit_transitions(machine.root, lines, indent="  ")
    return "\n".join(lines) + "\n"


def _emit_states(node: StateNode, lines: list[str], *, indent: str) -> None:
    for child in node.states.values():
        lines.append(f'{indent}state "{_escape(child.key)}" as {_alias(child)}')
        if child.states:
            lines.append(f"{indent}state {_alias(child)} {{")
            if child.initial_transition is not None:
                for target in child.initial.target:
                    lines.append(f"{indent}  [*] --> {_alias(target)}")
            _emit_states(child, lines, indent=f"{indent}  ")
            lines.append(f"{indent}}}")


def _emit_transitions(node: StateNode, lines: list[str], *, indent: str) -> None:
    for transition in node.transitions:
        _emit_transition(transition, lines, indent=indent)
    for child in node.states.values():
        _emit_transitions(child, lines, indent=indent)


def _emit_transition(
    transition: Transition,
    lines: list[str],
    *,
    indent: str,
) -> None:
    label = _transition_label(transition)
    if not transition.target:
        lines.append(f"{indent}%% {_alias(transition.source)} handles {label}")
        return
    for target in transition.target:
        lines.append(
            f"{indent}{_alias(transition.source)} --> {_alias(target)}: {label}"
        )


def _transition_label(transition: Transition) -> str:
    label = transition.event or "always"
    if transition.cond is not None:
        label = f"{label} [guard]"
    if transition.in_state is not None:
        label = f"{label} [in {transition.in_state!r}]"
    return _escape(label)


def _alias(node: StateNode) -> str:
    return "s_" + re.sub(r"[^0-9A-Za-z_]", "_", node.id)


def _escape(value: object) -> str:
    return str(value).replace('"', r"\"")
