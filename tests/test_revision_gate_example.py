"""Revision-aware evidence rules in the public, offline contribution example."""

import json

import pytest

from docs.examples.revision_gate import build_machine
from xstate import create_actor, deserialize_snapshot, serialize_snapshot

FIRST = "a" * 40
SECOND = "b" * 40


def at_revision(machine, sha=FIRST, *, ready=False):
    state = machine.transition(machine.initial_state, {"type": "REVISION", "sha": sha})
    if ready:
        state = machine.transition(
            state, {"type": "CI_RESULT", "sha": sha, "result": "success"}
        )
        state = machine.transition(
            state, {"type": "REVIEW_RESULT", "sha": sha, "result": "approved"}
        )
    return state


@pytest.mark.parametrize("review_first", [False, True])
def test_both_current_results_are_required_in_either_arrival_order(review_first):
    machine = build_machine()
    state = at_revision(machine)
    events = [
        {"type": "CI_RESULT", "sha": FIRST, "result": "success"},
        {"type": "REVIEW_RESULT", "sha": FIRST, "result": "approved"},
    ]
    if review_first:
        events.reverse()
    state = machine.transition(state, events[0])
    assert state.value == "collecting"
    state = machine.transition(state, events[1])
    assert state.value == "ready"
    assert state.status == "active"  # Readiness remains revocable.
    assert state.context["ci_sha"] == state.context["review_sha"] == FIRST


def test_new_revision_invalidates_all_evidence_without_mutating_old_snapshot():
    machine = build_machine()
    previous = at_revision(machine, ready=True)
    state = machine.transition(previous, {"type": "REVISION", "sha": SECOND})
    assert state.value == "collecting"
    assert state.context == {
        "head_sha": SECOND,
        "ci_sha": None,
        "ci_result": None,
        "review_sha": None,
        "review_result": None,
    }
    assert previous.value == "ready"
    assert previous.context["head_sha"] == FIRST
    assert previous.context["ci_result"] == "success"
    assert previous.context["review_result"] == "approved"


@pytest.mark.parametrize("ready", [False, True])
@pytest.mark.parametrize(
    "kind, outcome",
    [("CI_RESULT", "success"), ("REVIEW_RESULT", "approved")],
)
def test_stale_results_do_not_change_current_evidence_or_readiness(
    ready, kind, outcome
):
    machine = build_machine()
    before = at_revision(machine, SECOND, ready=ready)
    after = machine.transition(before, {"type": kind, "sha": FIRST, "result": outcome})
    assert serialize_snapshot(after) == serialize_snapshot(before)


@pytest.mark.parametrize(
    "kind, rejected, accepted",
    [
        ("CI_RESULT", "failure", "success"),
        ("REVIEW_RESULT", "changes_requested", "approved"),
    ],
)
def test_negative_current_result_revokes_readiness_and_can_be_corrected(
    kind, rejected, accepted
):
    machine = build_machine()
    state = at_revision(machine, ready=True)
    state = machine.transition(state, {"type": kind, "sha": FIRST, "result": rejected})
    assert state.value == "collecting"
    state = machine.transition(state, {"type": kind, "sha": FIRST, "result": accepted})
    assert state.value == "ready"


@pytest.mark.parametrize(
    "event",
    [
        {"type": "REVISION", "sha": FIRST},
        {"type": "CI_RESULT", "sha": FIRST, "result": "success"},
        {"type": "REVIEW_RESULT", "sha": FIRST, "result": "approved"},
    ],
)
def test_duplicate_current_events_leave_the_same_recorded_state(event):
    machine = build_machine()
    state = at_revision(machine, ready=True)
    assert serialize_snapshot(machine.transition(state, event)) == serialize_snapshot(
        state
    )


@pytest.mark.parametrize("sha", [None, "", FIRST])
def test_result_cannot_create_a_current_revision(sha):
    machine = build_machine()
    initial = machine.initial_state
    state = initial
    for kind, outcome in [("CI_RESULT", "success"), ("REVIEW_RESULT", "approved")]:
        state = machine.transition(state, {"type": kind, "sha": sha, "result": outcome})
    assert serialize_snapshot(state) == serialize_snapshot(initial)


@pytest.mark.parametrize("kind", ["CI_RESULT", "REVIEW_RESULT"])
def test_unknown_outcome_does_not_replace_current_evidence(kind):
    machine = build_machine()
    state = at_revision(machine, ready=True)
    after = machine.transition(
        state, {"type": kind, "sha": FIRST, "result": "unrecognized"}
    )
    assert serialize_snapshot(after) == serialize_snapshot(state)


def test_json_snapshot_handoff_matches_uninterrupted_processing():
    machine = build_machine()
    original = create_actor(machine)
    try:
        original.start()
        original.send({"type": "REVISION", "sha": SECOND})
        original.send({"type": "CI_RESULT", "sha": SECOND, "result": "success"})
        before = original.get_snapshot()
        checkpoint = json.dumps(serialize_snapshot(before))
    finally:
        original.stop()
    assert original.status == "stopped"

    restored_machine = build_machine()
    restored = deserialize_snapshot(restored_machine, json.loads(checkpoint))
    resumed = create_actor(restored_machine, snapshot=restored)
    continuation = [
        {"type": "REVIEW_RESULT", "sha": FIRST, "result": "approved"},
        {"type": "REVIEW_RESULT", "sha": SECOND, "result": "changes_requested"},
        {"type": "REVIEW_RESULT", "sha": SECOND, "result": "approved"},
    ]
    try:
        assert resumed.get_snapshot() is restored
        assert resumed.status == "not_started"
        resumed.start()
        expected = before
        for event, value in zip(
            continuation, ["collecting", "collecting", "ready"], strict=True
        ):
            expected = machine.transition(expected, event)
            resumed.send(event)
            assert resumed.get_snapshot().value == value
            assert serialize_snapshot(resumed.get_snapshot()) == serialize_snapshot(
                expected
            )
    finally:
        resumed.stop()
    assert resumed.status == "stopped"
