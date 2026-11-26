#!/usr/bin/env python3
"""Track recorded CI/review evidence for one current revision, entirely offline.

The host is responsible for event authority and ordering. This teaching example
does not contact GitHub, authorize merges, or durably store a checkpoint.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, TypedDict, cast

from xstate import (
    HandlerArgs,
    Machine,
    MachineSnapshot,
    assign,
    create_actor,
    deserialize_snapshot,
    serialize_snapshot,
)

CHART = Path(__file__).with_suffix(".json")


class GateContext(TypedDict):
    head_sha: str | None
    ci_sha: str | None
    ci_result: str | None
    review_sha: str | None
    review_result: str | None


class Revision(TypedDict):
    type: Literal["REVISION"]
    sha: str


class CIResult(TypedDict):
    type: Literal["CI_RESULT"]
    sha: str
    result: Literal["success", "failure"]


class ReviewResult(TypedDict):
    type: Literal["REVIEW_RESULT"]
    sha: str
    result: Literal["approved", "changes_requested"]


type GateEvent = Revision | CIResult | ReviewResult
type GateArgs = HandlerArgs[GateContext, GateEvent, None]
type GateSnapshot = MachineSnapshot[GateContext, GateEvent, None]


def payload(args: GateArgs) -> Mapping[str, object]:
    """Read mappings defensively; typing is not runtime event validation."""
    data = args.event.data if args.event is not None else None
    return cast(Mapping[str, object], data) if isinstance(data, dict) else {}


def is_new_revision(args: GateArgs) -> bool:
    sha = payload(args).get("sha")
    return isinstance(sha, str) and bool(sha) and sha != args.context["head_sha"]


def is_current_result(args: GateArgs, outcomes: tuple[str, ...]) -> bool:
    data = payload(args)
    head = args.context["head_sha"]
    return bool(head) and data.get("sha") == head and data.get("result") in outcomes


def is_current_ci(args: GateArgs) -> bool:
    return is_current_result(args, ("success", "failure"))


def is_current_review(args: GateArgs) -> bool:
    return is_current_result(args, ("approved", "changes_requested"))


def has_current_evidence(args: GateArgs) -> bool:
    context = args.context
    head = context["head_sha"]
    return bool(
        head
        and context["ci_sha"] == head
        and context["ci_result"] == "success"
        and context["review_sha"] == head
        and context["review_result"] == "approved"
    )


def needs_evidence(args: GateArgs) -> bool:
    return not has_current_evidence(args)


def change_revision(args: GateArgs) -> dict[str, object]:
    return {
        "head_sha": payload(args)["sha"],
        "ci_sha": None,
        "ci_result": None,
        "review_sha": None,
        "review_result": None,
    }


def record_ci(args: GateArgs) -> dict[str, object]:
    data = payload(args)
    return {"ci_sha": data["sha"], "ci_result": data["result"]}


def record_review(args: GateArgs) -> dict[str, object]:
    data = payload(args)
    return {"review_sha": data["sha"], "review_result": data["result"]}


def build_machine() -> Machine[GateContext, GateEvent, None]:
    """Load the data-only chart and bind ordinary named Python functions."""
    return Machine(
        json.loads(CHART.read_text(encoding="utf-8")),
        actions={
            "changeRevision": assign(change_revision),
            "recordCI": assign(record_ci),
            "recordReview": assign(record_review),
        },
        guards={
            "isNewRevision": is_new_revision,
            "isCurrentCI": is_current_ci,
            "isCurrentReview": is_current_review,
            "hasCurrentEvidence": has_current_evidence,
            "needsEvidence": needs_evidence,
        },
        strict=True,
    )


def describe(snapshot: GateSnapshot) -> str:
    context = snapshot.context
    head = context["head_sha"]
    return (
        f"{snapshot.value} (head={head[:7] if head else 'none'}, "
        f"ci={context['ci_result'] or 'missing'}, "
        f"review={context['review_result'] or 'missing'})"
    )


def main() -> None:
    # Synthetic IDs, not revisions from a real repository.
    first, second = "a" * 40, "b" * 40
    original = create_actor(build_machine())
    try:
        original.start()
        original.send({"type": "REVISION", "sha": first})
        original.send({"type": "CI_RESULT", "sha": first, "result": "success"})
        original.send({"type": "REVIEW_RESULT", "sha": first, "result": "approved"})
        print(f"revision A: {describe(original.get_snapshot())}")

        original.send({"type": "REVISION", "sha": second})
        print(f"revision B: {describe(original.get_snapshot())}")
        original.send({"type": "CI_RESULT", "sha": first, "result": "success"})
        original.send({"type": "REVIEW_RESULT", "sha": first, "result": "approved"})
        print(f"stale A results: {describe(original.get_snapshot())}")

        original.send({"type": "CI_RESULT", "sha": second, "result": "success"})
        checkpoint = json.dumps(serialize_snapshot(original.get_snapshot()))
    finally:
        original.stop()

    # A separate machine instance has the same definition and named bindings.
    machine = build_machine()
    restored = deserialize_snapshot(machine, json.loads(checkpoint))
    resumed = create_actor(machine, snapshot=restored)
    try:
        assert resumed.get_snapshot() is restored
        resumed.start()
        print(f"restored B: {describe(resumed.get_snapshot())}")
        resumed.send({"type": "REVIEW_RESULT", "sha": second, "result": "approved"})
        print(f"review B approved: {describe(resumed.get_snapshot())}")
        resumed.send({"type": "CI_RESULT", "sha": second, "result": "failure"})
        print(f"CI rerun failed: {describe(resumed.get_snapshot())}")
        resumed.send({"type": "CI_RESULT", "sha": second, "result": "success"})
        print(f"CI rerun passed: {describe(resumed.get_snapshot())}")
    finally:
        resumed.stop()


if __name__ == "__main__":
    main()
