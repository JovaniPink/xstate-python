from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any, NoReturn, cast

from xstate.exceptions import InvalidConfigError
from xstate.handlers import HandlerArgs
from xstate.machine import Machine
from xstate.schema import ActionSpec, MachineConfig, StateNodeConfig, TransitionConfig

__all__ = ["scxml_to_machine"]

_STATE_TAGS = frozenset({"state", "parallel"})


class _BooleanCondParser:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokens = self._tokenize(source)
        self.pos = 0

    def parse(self) -> bool:
        if not self.tokens:
            self._unsupported()
        result = self._parse_or()
        if self._peek() is not None:
            self._unsupported()
        return result

    def _parse_or(self) -> bool:
        result = self._parse_and()
        while self._match("||"):
            rhs = self._parse_and()
            result = result or rhs
        return result

    def _parse_and(self) -> bool:
        result = self._parse_not()
        while self._match("&&"):
            rhs = self._parse_not()
            result = result and rhs
        return result

    def _parse_not(self) -> bool:
        if self._match("!"):
            return not self._parse_not()
        return self._parse_atom()

    def _parse_atom(self) -> bool:
        token = self._peek()
        if token == "true":
            self.pos += 1
            return True
        if token == "false":
            self.pos += 1
            return False
        if self._match("("):
            result = self._parse_or()
            if not self._match(")"):
                self._unsupported()
            return result
        self._unsupported()

    def _peek(self) -> str | None:
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def _match(self, token: str) -> bool:
        if self._peek() == token:
            self.pos += 1
            return True
        return False

    def _unsupported(self) -> NoReturn:
        raise InvalidConfigError(
            "Unsupported SCXML JavaScript cond expression "
            f"{self.source!r}. Supported subset: true, false, !, &&, ||, "
            "and parentheses."
        )

    @staticmethod
    def _tokenize(source: str) -> list[str]:
        tokens: list[str] = []
        index = 0
        while index < len(source):
            char = source[index]
            if char.isspace():
                index += 1
                continue
            if source.startswith("&&", index) or source.startswith("||", index):
                tokens.append(source[index : index + 2])
                index += 2
                continue
            if char in "!()":
                tokens.append(char)
                index += 1
                continue
            if char.isalpha():
                start = index
                while index < len(source) and source[index].isalpha():
                    index += 1
                word = source[start:index]
                if word not in {"true", "false"}:
                    raise InvalidConfigError(
                        "Unsupported SCXML JavaScript cond expression "
                        f"{source!r}. Unsupported token {word!r}."
                    )
                tokens.append(word)
                continue
            raise InvalidConfigError(
                "Unsupported SCXML JavaScript cond expression "
                f"{source!r}. Unsupported token {char!r}."
            )
        return tokens


def _eval_scxml_cond(source: str) -> Callable[[HandlerArgs | None], bool]:
    """Compile the safe SCXML Boolean subset into a canonical guard."""
    result = _BooleanCondParser(source).parse()

    def guard(_args: HandlerArgs | None = None) -> bool:
        return result

    return guard


def get_tag(element: ET.Element) -> str:
    return element.tag.rpartition("}")[2]


def _children(element: ET.Element, tags: frozenset[str]) -> list[ET.Element]:
    return [child for child in element if get_tag(child) in tags]


def get_all_state_els(element: ET.Element) -> list[ET.Element]:
    return _children(element, _STATE_TAGS)


def _required_attribute(element: ET.Element, name: str) -> str:
    value = element.attrib.get(name)
    if value is None or not value.strip():
        raise InvalidConfigError(
            f"SCXML <{get_tag(element)}> requires a non-empty {name!r} attribute."
        )
    return value


def accumulate_states(element: ET.Element) -> dict[str, StateNodeConfig]:
    states: dict[str, StateNodeConfig] = {}
    for state_element in get_all_state_els(element):
        state_id = _required_attribute(state_element, "id")
        if state_id in states:
            raise InvalidConfigError(
                f"Duplicate SCXML state id {state_id!r} under "
                f"<{get_tag(element)}> element."
            )
        states[state_id] = convert_state(state_element)
    return states


def _validate_state_ids(element: ET.Element) -> None:
    seen: set[str] = set()
    for state_element in element.iter():
        if get_tag(state_element) not in _STATE_TAGS:
            continue
        state_id = _required_attribute(state_element, "id")
        if state_id in seen:
            raise InvalidConfigError(f"Duplicate SCXML state id {state_id!r}.")
        seen.add(state_id)


def convert_scxml(element: ET.Element) -> MachineConfig:
    _validate_state_ids(element)
    states = accumulate_states(element)
    if not states:
        raise InvalidConfigError(
            "SCXML document must contain at least one <state> or <parallel>."
        )
    initial = element.attrib.get("initial") or next(iter(states))
    return {"id": "machine", "initial": initial, "states": states}


def convert_state(element: ET.Element) -> StateNodeConfig:
    state_id = _required_attribute(element, "id")
    child_elements = get_all_state_els(element)
    states = accumulate_states(element)

    result: StateNodeConfig = {"id": state_id}
    if get_tag(element) == "parallel":
        result["type"] = "parallel"
    if states:
        result["states"] = states
        if get_tag(element) != "parallel":
            result["initial"] = element.attrib.get("initial") or _required_attribute(
                child_elements[0], "id"
            )

    transition_map: dict[
        str | None,
        TransitionConfig | str | list[TransitionConfig | str],
    ] = {}
    for transition_element in _children(element, frozenset({"transition"})):
        transition = convert_transition(transition_element)
        event = transition_element.attrib.get("event")
        bucket = transition_map.setdefault(event, [])
        if not isinstance(bucket, list):
            raise AssertionError("SCXML transition bucket must be a list")
        bucket.append(transition)
    if transition_map:
        result["on"] = transition_map

    entry_element = next(iter(_children(element, frozenset({"onentry"}))), None)
    if entry_element is not None:
        entry = convert_executable_content(entry_element)
        if entry:
            result["entry"] = entry

    exit_element = next(iter(_children(element, frozenset({"onexit"}))), None)
    if exit_element is not None:
        exit_actions = convert_executable_content(exit_element)
        if exit_actions:
            result["exit"] = exit_actions

    return result


def convert_transition(element: ET.Element) -> TransitionConfig:
    result: TransitionConfig = {}
    target = element.attrib.get("target")
    if target is not None:
        result["target"] = [f"#{target_id}" for target_id in target.split()]

    condition = element.attrib.get("cond")
    if condition is not None:
        result["guard"] = _eval_scxml_cond(condition)

    actions = convert_executable_content(element)
    if actions:
        result["actions"] = actions
    return result


def convert_raise(element: ET.Element) -> dict[str, str]:
    return {
        "type": "xstate:raise",
        "event": _required_attribute(element, "event"),
    }


def convert_executable_content(element: ET.Element) -> list[ActionSpec]:
    return [
        convert_raise(raise_element)
        for raise_element in _children(element, frozenset({"raise"}))
    ]


def convert(element: ET.Element) -> MachineConfig:
    if get_tag(element) != "scxml":
        raise InvalidConfigError(
            f"Expected an <scxml> document root, got <{get_tag(element)}> instead."
        )
    return convert_scxml(element)


def scxml_to_machine(source: str | os.PathLike[str]) -> Machine:
    """Load a focused SCXML subset from a filesystem path."""
    try:
        root = ET.parse(source).getroot()
    except ET.ParseError as exc:
        raise InvalidConfigError(
            f"Invalid SCXML XML in {os.fspath(source)!r}: {exc}"
        ) from exc
    return Machine(cast(dict[str, Any], convert(root)))
