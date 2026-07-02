from __future__ import annotations

import os
import xml.etree.ElementTree as ET

from xstate.exceptions import InvalidConfigError
from xstate.machine import Machine

ns = {"scxml": "http://www.w3.org/2005/07/scxml"}

__all__ = ["scxml_to_machine"]


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

    def _unsupported(self) -> None:
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


def _eval_scxml_cond(event_cond_str: str):
    """Compile a safe subset of SCXML JavaScript ``cond`` into a callable."""
    result = _BooleanCondParser(event_cond_str).parse()

    def cond() -> bool:
        return result

    return cond


def get_all_state_els(element: ET.Element) -> list[ET.Element]:
    return [e for e in element if get_tag(e) == "state" or get_tag(e) == "parallel"]


def convert_scxml(element: ET.Element, parent: ET.Element | None) -> dict:
    all_state_els = get_all_state_els(element)

    initial_state_key = element.attrib.get(
        "initial",
        convert_state(all_state_els[0], parent=element).get("key"),
    )

    return {
        "id": "machine",
        "initial": initial_state_key,
        "states": accumulate_states(element, parent),
    }


def get_tag(element: ET.Element) -> str:
    _, _, tag = element.tag.rpartition("}")
    return tag


def accumulate_states(element: ET.Element, parent: ET.Element | None) -> dict:
    all_state_els = [
        e for e in element if get_tag(e) == "state" or get_tag(e) == "parallel"
    ]
    states = [convert_state(state_el, element) for state_el in all_state_els]

    states_dict = {}

    for state in states:
        states_dict[state.get("key")] = state

    return states_dict


def convert_state(element: ET.Element, parent: ET.Element | None) -> dict:
    id = element.attrib.get("id")
    transition_els = element.findall("scxml:transition", namespaces=ns)
    transitions = [convert_transition(el, element) for el in transition_els]

    state_els = element.findall("scxml:state", namespaces=ns)

    states = accumulate_states(element, parent)

    onexit_el = element.find("scxml:onexit", namespaces=ns)
    onexit = (
        convert_onexit(onexit_el, parent=element) if onexit_el is not None else None
    )
    onentry_el = element.find("scxml:onentry", namespaces=ns)
    onentry = (
        convert_onentry(onentry_el, parent=element) if onentry_el is not None else None
    )

    result: dict = {
        "type": "parallel" if get_tag(element) == "parallel" else None,
        "id": f"{id}",
        "key": id,
        "exit": onexit,
        "entry": onentry,
        "states": states,
        "initial": state_els[0].attrib.get("id") if state_els else None,
    }

    if len(transitions) > 0:
        transitions_dict: dict[str | None, list] = {}

        for t in transitions:
            transitions_dict[t.get("event")] = transitions_dict.get(t.get("event"), [])
            transitions_dict[t.get("event")].append(t)

        result["on"] = transitions_dict

    return result


def convert_transition(element: ET.Element, parent: ET.Element) -> dict:
    event_type = element.attrib.get("event")
    target_attr = element.attrib.get("target")
    event_targets = target_attr.split(" ") if target_attr else []
    event_cond_str = element.attrib.get("cond")

    event_cond = _eval_scxml_cond(event_cond_str) if event_cond_str else None

    raise_els = element.findall("scxml:raise", namespaces=ns)
    actions = [convert_raise(raise_el, element) for raise_el in raise_els]

    return {
        "event": event_type,
        "target": ["#%s" % t for t in event_targets],
        "actions": actions,
        "cond": event_cond,
    }


def convert_raise(element: ET.Element, parent: ET.Element) -> dict:
    return {"type": "xstate:raise", "event": element.attrib.get("event")}


def convert_onexit(element: ET.Element, parent: ET.Element) -> list:
    raise_els = element.findall("scxml:raise", namespaces=ns)
    return [convert_raise(raise_el, element) for raise_el in raise_els]


def convert_onentry(element: ET.Element, parent: ET.Element) -> list:
    raise_els = element.findall("scxml:raise", namespaces=ns)
    return [convert_raise(raise_el, element) for raise_el in raise_els]


def convert(element: ET.Element, parent: ET.Element | None = None) -> dict:
    _, _, element_tag = element.tag.rpartition("}")  # strip namespace
    result = elements.get(element_tag, lambda *_: f"Invalid tag: {element_tag}")
    return result(element, parent)


elements: dict = {"scxml": convert_scxml, "state": convert_state}


def scxml_to_machine(source: str | os.PathLike[str]) -> Machine:
    """Load an SCXML document from a filesystem path."""
    tree = ET.parse(source)
    root = tree.getroot()
    result = convert(root)
    machine = Machine(result)
    return machine
