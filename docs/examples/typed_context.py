#!/usr/bin/env python3
"""Review release notes with typed events and immutable Python context.

Run after installing this checkout: python docs/examples/typed_context.py
All data is local and scripted; the example performs no external review.
"""

from dataclasses import dataclass
from typing import Literal, TypedDict

from xstate import (
    HandlerArgs,
    Machine,
    MachineConfig,
    MachineSetup,
    assign,
    create_actor,
    dataclass_context,
    setup,
)


@dataclass(frozen=True)
class ReviewContext:
    title: str
    remaining: int


class ResolveEvent(TypedDict):
    type: Literal["RESOLVE"]
    count: int


class ApproveEvent(TypedDict):
    type: Literal["APPROVE"]


@dataclass(frozen=True)
class ReviewResult:
    title: str
    approved: bool


type ReviewEvent = ResolveEvent | ApproveEvent
type ReviewArgs = HandlerArgs[ReviewContext, ReviewEvent, ReviewResult]


def resolution_count(args: ReviewArgs) -> int:
    data = args.event.data if args.event is not None else None
    if isinstance(data, dict) and data["type"] == "RESOLVE":
        return data["count"]
    raise ValueError("This handler requires a RESOLVE event")


def can_resolve(args: ReviewArgs) -> bool:
    return 0 < resolution_count(args) <= args.context.remaining


def resolve_findings(args: ReviewArgs) -> dict[str, int]:
    # assign + dataclass_context uses dataclasses.replace, not field mutation.
    return {"remaining": args.context.remaining - resolution_count(args)}


def can_approve(args: ReviewArgs) -> bool:
    return args.context.remaining == 0


def approved_review(args: ReviewArgs) -> ReviewResult:
    return ReviewResult(title=args.context.title, approved=True)


def build_machine(
    title: str = "Release notes", findings: int = 2
) -> Machine[ReviewContext, ReviewEvent, ReviewResult]:
    if findings < 0:
        raise ValueError("findings must be nonnegative")

    config: MachineConfig[ReviewContext, ReviewEvent, ReviewResult] = {
        "id": "typed-review",
        "context": ReviewContext(title=title, remaining=findings),
        "initial": "reviewing",
        "states": {
            "reviewing": {
                "on": {
                    "RESOLVE": {
                        "guard": "canResolve",
                        "actions": "resolveFindings",
                    },
                    "APPROVE": {"target": "approved", "guard": "canApprove"},
                }
            },
            "approved": {"type": "final", "output": approved_review},
        },
    }
    configured: MachineSetup[ReviewContext, ReviewEvent, ReviewResult] = setup(
        actions={"resolveFindings": assign(resolve_findings)},
        guards={"canResolve": can_resolve, "canApprove": can_approve},
        # This adapter shares context values. Use immutable fields throughout;
        # frozen dataclasses alone do not freeze a nested list or dictionary.
        context_adapter=dataclass_context(),
    )
    return configured.create_machine(config)


def main() -> None:
    actor = create_actor(build_machine())
    try:
        actor.start()
        original = actor.get_snapshot()

        blocked = actor.send({"type": "APPROVE"})
        print(
            f"Before resolution: {blocked.value}; remaining={blocked.context.remaining}"
        )

        resolved = actor.send({"type": "RESOLVE", "count": 2})
        print(
            f"After resolution: original remaining={original.context.remaining}; "
            f"current remaining={resolved.context.remaining}"
        )

        completed = actor.send({"type": "APPROVE"})
        print(f"After approval: {completed.status}; output={completed.output}")
    finally:
        actor.stop()


if __name__ == "__main__":
    main()
