"""Behavior taught by the public immutable-context example."""

from collections.abc import Iterator

import pytest

from docs.examples.typed_context import (
    ReviewContext,
    ReviewEvent,
    ReviewResult,
    build_machine,
)
from xstate import Actor, EventInput, State, create_actor

type ReviewActor = Actor[
    EventInput[ReviewEvent],
    State[ReviewContext, ReviewEvent, ReviewResult],
    ReviewResult,
]


@pytest.fixture
def review_actor() -> Iterator[ReviewActor]:
    actor = create_actor(build_machine()).start()
    try:
        yield actor
    finally:
        actor.stop()
        assert actor.system.get(actor.id) is None


def test_approval_requires_all_findings_resolved(review_actor: ReviewActor) -> None:
    blocked = review_actor.send({"type": "APPROVE"})
    assert blocked.value == "reviewing"
    assert blocked.status == "active"
    assert blocked.output is None

    review_actor.send({"type": "RESOLVE", "count": 1})
    still_blocked = review_actor.send({"type": "APPROVE"})
    assert still_blocked.value == "reviewing"
    assert still_blocked.context.remaining == 1


@pytest.mark.parametrize("count", [-1, 0, 3])
def test_invalid_resolution_keeps_the_review_unchanged(
    review_actor: ReviewActor, count: int
) -> None:
    before = review_actor.get_snapshot()
    result = review_actor.send({"type": "RESOLVE", "count": count})
    assert result.value == "reviewing"
    assert result.context == before.context
    assert result.context.remaining == 2


def test_assignment_replaces_context_and_retains_earlier_snapshots(
    review_actor: ReviewActor,
) -> None:
    original = review_actor.get_snapshot()
    first = review_actor.send({"type": "RESOLVE", "count": 1})
    second = review_actor.send({"type": "RESOLVE", "count": 1})

    assert original.context == ReviewContext("Release notes", 2)
    assert first.context == ReviewContext("Release notes", 1)
    assert second.context == ReviewContext("Release notes", 0)
    assert original.context is not first.context
    assert first.context is not second.context


def test_approved_output_is_terminal_and_releases_the_actor(
    review_actor: ReviewActor,
) -> None:
    review_actor.send({"type": "RESOLVE", "count": 2})
    done = review_actor.send({"type": "APPROVE"})
    assert done.value == "approved"
    assert done.status == "done"
    assert done.output == ReviewResult(title="Release notes", approved=True)
    assert review_actor.system.get(review_actor.id) is None
    assert review_actor.send({"type": "RESOLVE", "count": 1}) is done


def test_zero_findings_can_approve_immediately() -> None:
    actor = create_actor(build_machine("API guide", findings=0)).start()
    try:
        done = actor.send({"type": "APPROVE"})
        assert done.output == ReviewResult(title="API guide", approved=True)
    finally:
        actor.stop()


def test_negative_initial_findings_fail_clearly() -> None:
    with pytest.raises(ValueError, match="findings must be nonnegative"):
        build_machine(findings=-1)
