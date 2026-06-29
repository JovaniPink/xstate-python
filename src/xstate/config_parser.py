from __future__ import annotations

import warnings
from typing import Any, Literal, cast

from xstate.action import (
    ASSIGN_TYPE,
    CHOOSE_TYPE,
    PURE_TYPE,
    Action,
    build_action,
)
from xstate.exceptions import InvalidConfigError
from xstate.handlers import GuardReference, adapt_handler
from xstate.state_node import StateNode
from xstate.transition import Transition


class StateNodeConfigParser:
    """Build the resolved state tree from a raw XState-compatible dict config."""

    def __init__(self, machine: Any) -> None:
        self.machine = machine

    def parse(self, config: dict[str, Any]) -> StateNode:
        root = self._build_node(
            config,
            key=str(config.get("id", "(machine)")),
            parent=None,
            path="",
        )
        self._resolve_node(root, path="")
        return root

    def _build_node(
        self,
        config: Any,
        *,
        key: str,
        parent: StateNode | None,
        path: str,
    ) -> StateNode:
        if not isinstance(config, dict):
            raise InvalidConfigError(
                f"State node config at {self._display_path(path)} must be a dict."
            )

        states_config = config.get("states")
        if states_config is None:
            states_config = {}
        elif not isinstance(states_config, dict):
            raise InvalidConfigError(
                f"{self._path(path, 'states')} must be a dict of child states."
            )

        node_type = config.get("type")
        if node_type is None:
            node_type = "atomic" if not states_config else "compound"
        if node_type not in {"atomic", "compound", "parallel", "final", "history"}:
            raise InvalidConfigError(
                f"{self._path(path, 'type')} has unsupported state type {node_type!r}."
            )

        node_id = (
            config.get("id", f"{parent.id}.{key}")
            if parent is not None
            else config.get("id", f"{self.machine.id}.{key}")
        )
        node = StateNode(
            config=config,
            machine=self.machine,
            key=key,
            parent=parent,
            order=self.machine._get_order(),
            id=node_id,
            type=cast(
                Literal["atomic", "compound", "parallel", "final", "history"],
                node_type,
            ),
        )
        self.machine._register(node)

        for child_key, child_config in states_config.items():
            child_path = self._path(self._path(path, "states"), str(child_key))
            node.states[str(child_key)] = self._build_node(
                child_config,
                key=str(child_key),
                parent=node,
                path=child_path,
            )
        return node

    def _resolve_node(self, node: StateNode, *, path: str) -> None:
        for child_key, child in node.states.items():
            child_path = self._path(self._path(path, "states"), child_key)
            self._resolve_node(child, path=child_path)

        config = node.config
        node.entry = self._build_actions(config.get("entry"), self._path(path, "entry"))
        node.exit = self._build_actions(config.get("exit"), self._path(path, "exit"))

        node.history = (
            config.get("history", "shallow") if node.type == "history" else None
        )
        if node.type == "history" and config.get("target") is not None:
            node.transition = self._make_transition(
                config.get("target"),
                source=node,
                event=None,
                order=-1,
                path=self._path(path, "target"),
            )

        node.tags = self._build_tags(config.get("tags"), self._path(path, "tags"))

        node.donedata = self._build_output(node, path)
        self._build_configured_transitions(node, path)
        self._build_initial_transition(node, path)

    def _build_tags(self, tags_config: Any, path: str) -> tuple[str, ...]:
        if tags_config is None:
            return ()
        if isinstance(tags_config, str):
            return (tags_config,)
        if isinstance(tags_config, (list, tuple)):
            if not all(isinstance(t, str) for t in tags_config):
                raise InvalidConfigError(
                    f"{path}: every tag must be a string, got {tags_config!r}."
                )
            return tuple(tags_config)
        raise InvalidConfigError(
            f"{path}: 'tags' must be a string or a list of strings, "
            f"got {type(tags_config)!r}."
        )

    def _build_output(self, node: StateNode, path: str) -> Any:
        if node.type != "final":
            return None
        config = node.config
        if "data" in config:
            warnings.warn(
                "`data` on a final state is deprecated; use `output` "
                "(XState v5 naming). `data` still works but will be removed "
                "in a future release.",
                DeprecationWarning,
                stacklevel=4,
            )
        output = config.get("output", config.get("data"))
        return adapt_handler(
            output,
            kind="final output",
            strict=self.machine.strict,
            path=self._path(path, "output"),
        )

    def _build_configured_transitions(self, node: StateNode, path: str) -> None:
        config = node.config
        on_config = config.get("on")
        if on_config is None:
            on_config = {}
        elif not isinstance(on_config, dict):
            raise InvalidConfigError(f"{self._path(path, 'on')} must be a dict.")

        for event_name, transition_config in on_config.items():
            for index, raw_transition in enumerate(self._as_list(transition_config)):
                self._add_transition(
                    node,
                    None if event_name is None else str(event_name),
                    raw_transition,
                    self._path(self._path(path, "on"), str(event_name), index),
                )

        always_configs = config.get("always")
        if always_configs is not None:
            for index, always_config in enumerate(self._as_list(always_configs)):
                self._add_transition(
                    node,
                    "",
                    always_config,
                    self._path(path, "always", index),
                )

        on_done_configs = config.get("onDone")
        if on_done_configs is not None:
            done_event = f"done.state.{node.id}"
            for index, done_config in enumerate(self._as_list(on_done_configs)):
                self._add_transition(
                    node,
                    done_event,
                    done_config,
                    self._path(path, "onDone", index),
                )

        self._build_invoke(node, path)
        self._build_after(node, path)

    def _build_invoke(self, node: StateNode, path: str) -> None:
        invoke_configs = node.config.get("invoke")
        if invoke_configs is None:
            return

        for index, invoke_config in enumerate(self._as_list(invoke_configs)):
            invoke_path = self._path(path, "invoke", index)
            if not isinstance(invoke_config, dict):
                raise InvalidConfigError(f"{invoke_path} must be a dict.")

            raw_id = invoke_config.get("id")
            invoke_id = (
                raw_id if raw_id is not None else f"{node.id}:invocation[{index}]"
            )
            src = invoke_config.get("src")
            if src is None:
                raise InvalidConfigError(
                    f"{self._path(invoke_path, 'src')} is required: invoke on "
                    f"state '{node.id}' is missing a 'src'. Provide actor logic "
                    "or a name registered via Machine(config, actors={...})."
                )

            input_spec = adapt_handler(
                invoke_config.get("input"),
                kind="invoke input",
                strict=self.machine.strict,
                path=self._path(invoke_path, "input"),
            )
            node.invoke.append({"id": invoke_id, "src": src, "input": input_spec})

            for event_name, handler_key in (
                (f"done.invoke.{invoke_id}", "onDone"),
                (f"error.platform.{invoke_id}", "onError"),
                (f"snapshot.invoke.{invoke_id}", "onSnapshot"),
            ):
                handler = invoke_config.get(handler_key)
                if handler is None:
                    continue
                for handler_index, handler_config in enumerate(self._as_list(handler)):
                    self._add_transition(
                        node,
                        event_name,
                        handler_config,
                        self._path(invoke_path, handler_key, handler_index),
                    )

    def _build_after(self, node: StateNode, path: str) -> None:
        after_config = node.config.get("after")
        if after_config is None:
            after_config = {}
        elif not isinstance(after_config, dict):
            raise InvalidConfigError(f"{self._path(path, 'after')} must be a dict.")

        for delay, transition_config in after_config.items():
            after_event = f"xstate.after({delay})#{node.id}"
            for index, raw_transition in enumerate(self._as_list(transition_config)):
                self._add_transition(
                    node,
                    after_event,
                    raw_transition,
                    self._path(self._path(path, "after"), str(delay), index),
                )
            node.after.append((delay, after_event))

    def _build_initial_transition(self, node: StateNode, path: str) -> None:
        if node.type == "compound":
            initial_key = node.config.get("initial")
            target: StateNode
            if not initial_key:
                if not node.states:
                    raise InvalidConfigError(
                        f"State '#{node.id}' of type 'compound' has no child states."
                    )
                target = next(iter(node.states.values()))
            else:
                maybe_target = node.states.get(initial_key)
                if maybe_target is None:
                    raise InvalidConfigError(
                        f"Initial state '{initial_key}' at "
                        f"{self._path(path, 'initial')} is not a child of '#{node.id}'."
                    )
                target = maybe_target
            node.initial_transition = Transition(
                event=None,
                source=node,
                config=target,
                order=-1,
                target_nodes=[target],
            )
        elif node.type == "parallel":
            node.initial_transition = Transition(
                event=None,
                source=node,
                config=node,
                order=-1,
                target_nodes=[node],
            )

    def _add_transition(
        self,
        node: StateNode,
        event: str | None,
        raw_transition: Any,
        path: str,
    ) -> Transition:
        transition = self._make_transition(
            raw_transition,
            source=node,
            event=event,
            order=self.machine._get_order(),
            path=path,
        )
        node.on.setdefault(event or "", []).append(transition)
        node.transitions.append(transition)
        return transition

    def _make_transition(
        self,
        raw_transition: Any,
        *,
        source: StateNode,
        event: str | None,
        order: int,
        path: str,
    ) -> Transition:
        cond = None
        in_state = None
        transition_type: Literal["internal", "external"] = "external"
        actions: list[Action] = []
        target_spec = raw_transition

        if isinstance(raw_transition, dict):
            if "cond" in raw_transition:
                warnings.warn(
                    "`cond` is deprecated; use `guard` (XState v5 naming). "
                    "`cond` still works but will be removed in a future release.",
                    DeprecationWarning,
                    stacklevel=4,
                )
            cond = self._build_guard(
                raw_transition.get("guard", raw_transition.get("cond")),
                self._path(path, "guard"),
            )
            in_state = raw_transition.get("in")
            transition_type = self._resolve_transition_type(
                raw_transition.get("type", "external"),
                self._path(path, "type"),
            )
            actions = self._build_actions(
                raw_transition.get("actions"),
                self._path(path, "actions"),
            )
            target_spec = raw_transition.get("target")

        target_nodes = self._resolve_targets(source, target_spec, path)
        return Transition(
            event=event,
            source=source,
            config=raw_transition,
            order=order,
            target_nodes=target_nodes,
            actions=actions,
            cond=cond,
            in_state=in_state,
            type=transition_type,
        )

    def _resolve_transition_type(
        self, transition_type: Any, path: str
    ) -> Literal["internal", "external"]:
        if transition_type == "internal":
            return "internal"
        if transition_type == "external":
            return "external"
        raise InvalidConfigError(
            f"{path} must be 'internal' or 'external', got {transition_type!r}."
        )

    def _build_guard(self, guard: Any, path: str) -> Any:
        if isinstance(guard, dict):
            guard_name = guard.get("type")
            if guard_name is None:
                raise InvalidConfigError(f"{path}.type is required for guard objects.")
            if self.machine.strict and guard_name not in self.machine.guards:
                raise InvalidConfigError(
                    f"Guard '{guard_name}' referenced at {path} is not registered."
                )
            return GuardReference(
                name=str(guard_name),
                params=guard.get("params"),
                path=path,
            )

        if (
            isinstance(guard, str)
            and self.machine.strict
            and guard not in self.machine.guards
        ):
            raise InvalidConfigError(
                f"Guard '{guard}' referenced at {path} is not registered."
            )

        return adapt_handler(
            guard,
            kind="guard",
            strict=self.machine.strict,
            path=path,
        )

    def _build_actions(self, raw_actions: Any, path: str) -> list[Action]:
        actions: list[Action] = []
        for index, raw_action in enumerate(self._as_list(raw_actions)):
            action = build_action(raw_action, self.machine.actions)
            actions.append(self._adapt_action(action, self._path(path, index)))
        return actions

    def _adapt_action(self, action: Action, path: str) -> Action:
        action.data = dict(action.data)
        if action.type == ASSIGN_TYPE:
            assignment = action.data.get("assignment", {})
            if callable(assignment):
                action.data["assignment"] = adapt_handler(
                    assignment,
                    kind="assign",
                    strict=self.machine.strict,
                    path=self._path(path, "assignment"),
                )
            elif isinstance(assignment, dict):
                action.data["assignment"] = {
                    key: adapt_handler(
                        value,
                        kind="assign",
                        strict=self.machine.strict,
                        path=self._path(self._path(path, "assignment"), str(key)),
                    )
                    for key, value in assignment.items()
                }
            action.data["_context_adapter"] = self.machine.context_adapter
        elif action.type == CHOOSE_TYPE:
            self._adapt_choose(action, path)
        elif action.type == PURE_TYPE:
            # Returned actions are built lazily at execution time; stash the
            # registry so string names / inline callables can be resolved then.
            action.data["_actions"] = self.machine.actions
        elif callable(action.type):
            action.type = adapt_handler(
                action.type,
                kind="action",
                strict=self.machine.strict,
                path=path,
            )
        return action

    def _adapt_choose(self, action: Action, path: str) -> None:
        raw_branches = action.data.get("branches") or []
        branches: list[dict[str, Any]] = []
        for index, raw_branch in enumerate(raw_branches):
            branch_path = self._path(path, index)
            if not isinstance(raw_branch, dict):
                raise InvalidConfigError(
                    f"{branch_path}: each choose branch must be a dict with "
                    f"'actions' (and optional 'guard'), got {type(raw_branch)!r}."
                )
            guard = raw_branch.get("guard", raw_branch.get("cond"))
            if callable(guard):
                guard = adapt_handler(
                    guard,
                    kind="guard",
                    strict=self.machine.strict,
                    path=self._path(branch_path, "guard"),
                )
            sub_actions = self._build_actions(
                raw_branch.get("actions"), self._path(branch_path, "actions")
            )
            branches.append({"guard": guard, "actions": sub_actions})
        action.data["branches"] = branches
        action.data["_guards"] = self.machine.guards

    def _resolve_targets(
        self, source: StateNode, target_spec: Any, path: str
    ) -> list[StateNode]:
        if target_spec is None:
            return []
        if isinstance(target_spec, StateNode):
            return [target_spec]
        if isinstance(target_spec, str):
            return [self._resolve_target(source, target_spec, path)]
        if isinstance(target_spec, list):
            return [
                self._resolve_target(source, target, self._path(path, "target", index))
                for index, target in enumerate(target_spec)
            ]
        raise InvalidConfigError(
            f"{self._path(path, 'target')} must be a string or list."
        )

    def _resolve_target(self, source: StateNode, target: Any, path: str) -> StateNode:
        if isinstance(target, StateNode):
            return target
        if not isinstance(target, str):
            raise InvalidConfigError(
                f"{path} target must be a string, got {type(target)!r}."
            )
        try:
            return source._get_relative(target)
        except InvalidConfigError as exc:
            raise InvalidConfigError(f"{path}: {exc}") from exc

    def _as_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _path(self, path: str, part: object, index: int | None = None) -> str:
        part_text = str(part)
        joined = part_text if not path else f"{path}.{part_text}"
        if index is None:
            return joined
        return f"{joined}[{index}]"

    def _display_path(self, path: str) -> str:
        return path or "<root>"
