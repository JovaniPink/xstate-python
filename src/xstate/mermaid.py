from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from xstate.machine import Machine
    from xstate.state_node import StateNode
    from xstate.transition import Transition

__all__ = ["to_mermaid"]


def to_mermaid(machine: Machine) -> str:
    """Return a dependency-free Mermaid ``stateDiagram-v2`` representation."""
    return _MermaidExporter(machine).render()


class _MermaidExporter:
    def __init__(self, machine: Machine) -> None:
        self.machine = machine
        self.aliases: dict[StateNode, str] = {}

    def render(self) -> str:
        lines = ["stateDiagram-v2"]
        self._emit_initial(self.machine.root, lines, indent="  ")
        self._emit_states(self.machine.root, lines, indent="  ")
        self._emit_transitions(self.machine.root, lines, indent="  ")
        return "\n".join(lines) + "\n"

    def _emit_initial(
        self,
        node: StateNode,
        lines: list[str],
        *,
        indent: str,
    ) -> None:
        if node.initial_transition is None:
            return
        for target in node.initial.target:
            if target is node:
                continue
            lines.append(f"{indent}[*] --> {self._alias(target)}")

    def _emit_states(self, node: StateNode, lines: list[str], *, indent: str) -> None:
        for child in node.states.values():
            lines.append(
                f'{indent}state "{_escape(child.key)}" as {self._alias(child)}'
            )
            if child.states:
                lines.append(f"{indent}state {self._alias(child)} {{")
                self._emit_initial(child, lines, indent=f"{indent}  ")
                self._emit_states(child, lines, indent=f"{indent}  ")
                lines.append(f"{indent}}}")

    def _emit_transitions(
        self,
        node: StateNode,
        lines: list[str],
        *,
        indent: str,
    ) -> None:
        for transition in node.transitions:
            self._emit_transition(transition, lines, indent=indent)
        for child in node.states.values():
            self._emit_transitions(child, lines, indent=indent)

    def _emit_transition(
        self,
        transition: Transition,
        lines: list[str],
        *,
        indent: str,
    ) -> None:
        label = _transition_label(transition)
        if not transition.target:
            lines.append(f"{indent}%% {self._alias(transition.source)} handles {label}")
            return
        for target in transition.target:
            lines.append(
                f"{indent}{self._alias(transition.source)} --> "
                f"{self._alias(target)}: {label}"
            )

    def _alias(self, node: StateNode) -> str:
        try:
            return self.aliases[node]
        except KeyError:
            alias = "s_" + node.id.encode("utf-8").hex()
            self.aliases[node] = alias
            return alias


def _transition_label(transition: Transition) -> str:
    label = transition.event or "always"
    if transition.cond is not None:
        label = f"{label} [guard]"
    if transition.in_state is not None:
        label = f"{label} [in {transition.in_state!r}]"
    return _escape(label)


def _escape(value: object) -> str:
    return str(value).replace('"', r"\"")
