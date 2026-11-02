"""Compare the inspector with independent direct actor execution, including traces."""

import json
import re
import threading
from http.client import HTTPConnection
from urllib.parse import urlencode

import pytest

from docs.examples.fetch_with_retry import build_machine
from docs.examples.local_inspector import InspectorSession, make_server, page
from xstate import create_actor
from xstate.scheduler import SimulatedClock


def signature(trace):
    # Independent oracle projection: do not reuse inspector serialization.
    return (
        trace.event.name,
        trace.snapshot.value,
        trace.snapshot.context,
        [
            (
                step.event.name,
                step.snapshot.value,
                step.snapshot.context,
                [
                    (t.event_type, t.source_id, list(t.target_ids))
                    for t in step.transitions
                ],
            )
            for step in trace.microsteps
        ],
    )


@pytest.mark.parametrize(
    "scenario,retries,attempts,final",
    [
        ("success", 0, 1, "success"),
        ("retry-success", 2, 3, "success"),
        ("exhausted", 3, 3, "failure"),
    ],
)
def test_direct_execution_equivalence(scenario, retries, attempts, final):
    session = InspectorSession(scenario)
    direct_machine, source = build_machine(scenario)
    plain_machine, plain_source = build_machine(scenario)
    clock, plain_clock = SimulatedClock(), SimulatedClock()
    traces = []
    actor = create_actor(direct_machine, clock=clock, inspect=traces.append).start()
    plain = create_actor(plain_machine, clock=plain_clock).start()
    commands = [
        {"kind": "event", "event": {"type": "UNKNOWN", "payload": "sample"}},
        {"kind": "event", "event": {"type": "FETCH"}},
        {"kind": "advance", "ms": 999},
        {"kind": "advance", "ms": 1},
        {"kind": "advance", "ms": 1000},
    ]
    try:
        for command in commands:
            session.command(command)
            if command["kind"] == "event":
                actor.send(command["event"])
                plain.send(command["event"])
            else:
                clock.increment(command["ms"])
                plain_clock.increment(command["ms"])
            observed = session.export()
            for runtime in (actor, plain):
                snapshot = runtime.get_snapshot()
                assert observed["snapshot"] == {
                    "value": snapshot.value,
                    "context": snapshot.context,
                    "status": snapshot.status,
                }
            assert observed["attempts"] == source.attempts == plain_source.attempts
            projected = [
                (
                    f["event"],
                    f["snapshot"]["value"],
                    f["snapshot"]["context"],
                    [
                        (
                            s["event"],
                            s["snapshot"]["value"],
                            s["snapshot"]["context"],
                            [
                                (t["event"], t["source"], t["targets"])
                                for t in s["transitions"]
                            ],
                        )
                        for s in f["microsteps"]
                    ],
                )
                for f in observed["frames"]
            ]
            assert projected == [signature(t) for t in traces]
        assert observed["snapshot"]["value"] == final
        assert observed["snapshot"]["context"]["retries"] == retries
        assert observed["attempts"] == attempts
        if final == "success":
            assert observed["snapshot"]["context"]["data"] == {
                "id": 42,
                "name": "Ada Lovelace",
            }
        else:
            assert any(
                t.event_type == ""
                for step in traces[-1].microsteps
                for t in step.transitions
            )
    finally:
        session.close()
        actor.stop()
        plain.stop()


@pytest.mark.parametrize(
    "command",
    [
        {"kind": "advance", "ms": -1},
        {"kind": "advance", "ms": True},
        {"kind": "advance", "ms": 0.5},
        {"kind": "advance", "ms": 60001},
        {"kind": "event", "event": []},
        {"kind": "event", "event": {"type": ""}},
        {"kind": "event", "event": {"type": "done.invoke.getUser"}},
        {"kind": "event", "event": {"type": "FETCH", "value": float("nan")}},
        {"kind": "other"},
        {"kind": "event", "event": {"type": "\ud800"}},
    ],
)
def test_rejected_command_does_not_change_run(command):
    session = InspectorSession()
    try:
        before = json.dumps(session.export())
        with pytest.raises(ValueError):
            session.command(command)
        assert json.dumps(session.export()) == before
    finally:
        session.close()


def test_bounded_history_and_escaped_event():
    session = InspectorSession()
    try:
        for _ in range(200):
            session.command(
                {"kind": "event", "event": {"type": "<script>alert(1)</script>"}}
            )
        exported = session.export()
        assert len(exported["frames"]) == 200
        assert exported["omitted_frames"] == 1
        assert exported["frames"][0]["sequence"] == 1
        assert "<script>" not in page(session, "test-token")
        with pytest.raises(ValueError, match="limit"):
            session.command({"kind": "advance", "ms": 1})
        assert session.clock.now() == 0
    finally:
        session.close()


def test_http_commands_export_reset_and_boundaries():
    server = make_server()
    worker = threading.Thread(target=server.serve_forever)
    worker.start()
    client = HTTPConnection("127.0.0.1", server.server_port, timeout=5)

    def request(method, path="/", body=None, headers=None):
        client.request(method, path, body, headers or {})
        response = client.getresponse()
        return response.status, response.read().decode()

    try:
        status, html = request("GET")
        assert status == 200
        token = re.search(r'name="token" value="([^"]+)"', html)[1]
        assert "Active state: idle" in html
        assert request("POST", body=urlencode({"token": "wrong"}))[0] == 403
        assert request("POST", body=urlencode({"token": "é"}))[0] == 403
        assert (
            request("POST", body="x=1", headers={"Origin": "https://example.com"})[0]
            == 403
        )
        assert request("GET", headers={"Host": "example.com"})[0] == 403
        assert request("POST", body="x" * 8193)[0] == 400
        assert (
            request(
                "POST",
                body=urlencode({"token": token, "operation": "event", "event": "{"}),
            )[0]
            == 400
        )
        for operation in [
            {"operation": "event", "event": '{"type":"FETCH"}'},
            {"operation": "advance", "ms": "2000"},
        ]:
            assert (
                request("POST", body=urlencode({"token": token, **operation}))[0] == 303
            )
        status, raw = request("GET", "/export")
        exported = json.loads(raw)
        assert status == 200
        assert exported["snapshot"]["value"] == "success"
        assert exported["attempts"] == 3
        assert (
            request(
                "POST",
                body=urlencode(
                    {
                        "token": token,
                        "operation": "reset",
                        "scenario": "exhausted",
                    }
                ),
            )[0]
            == 303
        )
        reset = json.loads(request("GET", "/export")[1])
        assert reset["attempts"] == 0
        assert reset["snapshot"]["value"] == "idle"
        assert reset["commands"] == []
        assert len(reset["frames"]) == 1
    finally:
        client.close()
        server.shutdown()
        worker.join()
        server.inspector_session.close()
        server.server_close()


def test_stopping_run_cancels_pending_retry_and_fresh_run_is_independent():
    old = InspectorSession()
    old.command({"kind": "event", "event": {"type": "FETCH"}})
    assert old.source.attempts == 1
    old.close()
    fresh = InspectorSession()
    try:
        old.clock.increment(60000)
        assert old.source.attempts == 1
        assert fresh.source.attempts == 0
        assert fresh.actor.get_snapshot().value == "idle"
        fresh.command({"kind": "event", "event": {"type": "FETCH"}})
        assert fresh.source.attempts == 1
        assert fresh.actor.get_snapshot().context["retries"] == 1
    finally:
        fresh.close()
