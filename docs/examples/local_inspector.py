#!/usr/bin/env python3
"""Optional loopback inspector for the synthetic fetch example (stdlib only)."""

from __future__ import annotations

import argparse
import hmac
import json
import secrets
from collections import deque
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs

from xstate import MacrostepTrace, State, create_actor
from xstate.scheduler import SimulatedClock

if TYPE_CHECKING or __package__:
    from docs.examples.fetch_with_retry import SCENARIOS, build_machine
else:
    from fetch_with_retry import SCENARIOS, build_machine


def snapshot_data(snapshot: State) -> dict[str, Any]:
    # Copy at capture time; JSON is sufficient for this synthetic example only.
    return cast(
        dict[str, Any],
        json.loads(
            json.dumps(
                {
                    "value": snapshot.value,
                    "context": snapshot.context,
                    "status": snapshot.status,
                }
            )
        ),
    )


def trace_data(trace: MacrostepTrace) -> dict[str, Any]:
    return {
        "event": trace.event.name,
        "snapshot": snapshot_data(trace.snapshot),
        "microsteps": [
            {
                "event": step.event.name,
                "snapshot": snapshot_data(step.snapshot),
                "transitions": [
                    {
                        "event": t.event_type,
                        "source": t.source_id,
                        "targets": list(t.target_ids),
                    }
                    for t in step.transitions
                ],
            }
            for step in trace.microsteps
        ],
    }


class InspectorSession:
    """Single-owner session; HTTPServer serializes commands on its serving thread."""

    def __init__(self, scenario: str = "retry-success") -> None:
        self.scenario = scenario
        self.machine, self.source = build_machine(scenario)
        self.clock = SimulatedClock()
        self.frames: deque[dict[str, Any]] = deque(maxlen=200)
        self.total_frames = 0
        self.commands: list[dict[str, Any]] = []
        self.actor = create_actor(self.machine, clock=self.clock, inspect=self.capture)
        self.actor.start()

    def capture(self, trace: MacrostepTrace) -> None:
        frame = trace_data(trace)
        frame["sequence"] = self.total_frames
        frame["time_ms"] = self.clock.now()
        self.frames.append(frame)
        self.total_frames += 1

    def command(self, command: dict[str, Any]) -> None:
        if len(self.commands) >= 200:
            raise ValueError("Run limit reached. Export and reset to continue.")
        if command.get("kind") == "event" and set(command) == {"kind", "event"}:
            event = command["event"]
            if (
                not isinstance(event, dict)
                or not isinstance(event.get("type"), str)
                or not event["type"]
                or len(event["type"]) > 100
            ):
                raise ValueError("Event must be a JSON object with a nonempty type.")
            if event["type"].startswith(("xstate.", "done.", "error.", "snapshot.")):
                raise ValueError("Runtime lifecycle events cannot be injected.")
            # Validate/copy before admitting the command; no live objects accepted.
            encoded = json.dumps(command, allow_nan=False, ensure_ascii=False).encode(
                "utf-8"
            )
            command = json.loads(encoded)
            self.actor.send(command["event"])
        elif command.get("kind") == "advance" and set(command) == {"kind", "ms"}:
            ms = command["ms"]
            if type(ms) is not int or not 0 <= ms <= 60000:
                raise ValueError("Time must be an integer from 0 through 60000 ms.")
            self.clock.increment(ms)
        else:
            raise ValueError("Unknown command.")
        self.commands.append(command)

    def export(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "scenario": self.scenario,
            "config": self.machine.config,
            "commands": self.commands,
            "time_ms": self.clock.now(),
            "attempts": self.source.attempts,
            "snapshot": snapshot_data(self.actor.get_snapshot()),
            "frames": list(self.frames),
            "omitted_frames": self.total_frames - len(self.frames),
        }

    def close(self) -> None:
        self.actor.stop()


def pretty(value: Any) -> str:
    return escape(json.dumps(value, indent=2, ensure_ascii=False))


def page(session: InspectorSession, token: str, error: str = "") -> str:
    data = session.export()
    active = data["snapshot"]["value"]
    # Layout is deliberately limited to this example; topology comes from Machine.
    positions = {
        "idle": (90, 70),
        "loading": (280, 70),
        "retrying": (280, 190),
        "success": (480, 70),
        "failure": (480, 190),
    }
    edges = []
    nodes = []
    for name, node in session.machine.states.items():
        x, y = positions[name]
        for transition in node.transitions:
            for target in transition.target:
                tx, ty = positions[target.key]
                dx, dy = tx - x, ty - y
                scale = min(65 / abs(dx) if dx else 100, 22 / abs(dy) if dy else 100)
                sx, sy = x + dx * scale, y + dy * scale
                ex, ey = tx - dx * scale, ty - dy * scale
                if not dx:
                    sx += 20 if dy > 0 else -20
                    ex = sx
                edges.append(
                    f'<path d="M{sx},{sy} L{ex},{ey}" stroke="currentColor" '
                    'marker-end="url(#arrow)"/>'
                )
        selected = name == active
        nodes.append(
            f'<g><rect x="{x - 65}" y="{y - 22}" width="130" height="44" '
            f'rx="12" fill="{"#d5f3e6" if selected else "#fff"}" '
            f'stroke="currentColor" stroke-width="{3 if selected else 1}"/>'
            f'<text x="{x}" y="{y + 5}" text-anchor="middle">'
            f"{escape(name)}{' •' if selected else ''}</text></g>"
        )
    history = []
    for frame in data["frames"]:
        steps = []
        for step in frame["microsteps"]:
            transitions = step["transitions"]
            rows = (
                "".join(
                    f"<li>{escape(t['source'])} → "
                    f"{escape(', '.join(t['targets']))} "
                    f"({escape(t['event'] or 'always')})</li>"
                    for t in transitions
                )
                or "<li>No transition selected</li>"
            )
            steps.append(
                f"<p>Event: {escape(step['event'] or 'always')}</p>"
                f"<ul>{rows}</ul><pre>{pretty(step['snapshot'])}</pre>"
            )
        history.append(
            f"<details><summary>#{frame['sequence']} · {frame['time_ms']:g} ms · "
            f"{escape(frame['event'])} → {escape(str(frame['snapshot']['value']))}"
            f"</summary>{''.join(steps)}</details>"
        )
    hidden = f'<input type="hidden" name="token" value="{token}">'
    options = "".join(
        f"<option {'selected' if s == session.scenario else ''}>{s}</option>"
        for s in SCENARIOS
    )
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fetch inspector · xstate-python</title>
<style>
body{{font:16px system-ui;margin:0;background:#f4f6f8;color:#203340}}
main{{max-width:1100px;margin:32px auto;padding:0 20px}}
h1{{font-size:2.2rem;margin-bottom:8px}} h2{{font-size:1.2rem}}
.grid{{display:grid;grid-template-columns:1.4fr 1fr;gap:20px}}
section{{background:white;border:1px solid #dbe2e7;border-radius:14px;
padding:20px;margin:18px 0}}
svg{{width:100%;height:auto}} form{{margin:16px 0}} button,a{{color:#075b4d}}
button,input,select,textarea{{font:inherit;padding:9px;border:1px solid #8b9da7;
border-radius:6px}}
button{{background:#e3f4ee;cursor:pointer}}
textarea{{width:90%;display:block;margin:8px 0}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}
summary{{cursor:pointer;padding:12px 0}} details{{border-top:1px solid #dbe2e7}}
.error{{color:#a21919}} label{{display:block}}
:focus-visible{{outline:3px solid #106db5}}
@media(max-width:750px){{.grid{{display:block}}}}
</style><main><p>XSTATE-PYTHON / LOCAL EXAMPLE</p><h1>Watch a fetch recover.</h1>
<p>Send an event, advance time, and inspect the runtime’s decisions.
Synthetic data · no network fetches · scenario: {escape(session.scenario)}</p>
<p role="alert" class="error">{escape(error)}</p><div class="grid"><div><section>
<h2>Active state: {escape(str(active))}</h2>
<svg viewBox="0 0 580 250" role="img"
aria-label="Fetch chart; active state {escape(str(active))}">
<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="8" refY="4"
orient="auto">
<path d="M0,0 L8,4 L0,8" fill="currentColor"/></marker></defs>
{"".join(edges)}{"".join(nodes)}</svg>
<p>idle → loading → success; failures enter retrying, then loading or failure.
Exact selected edges appear in the history.</p>
<p>Simulated time: {data["time_ms"]:g} ms · Fetch attempts: {data["attempts"]}</p>
<form method="post">{hidden}<input type="hidden" name="operation" value="event">
<label for="event">Event JSON</label>
<textarea id="event" name="event" rows="2">{{"type":"FETCH"}}</textarea>
<button>Send event</button></form><form method="post">{hidden}
<input type="hidden" name="operation" value="advance">
<label for="ms">Advance time (ms)</label>
<input id="ms" name="ms" type="number" min="0" max="60000" value="1000" required>
<button>Advance time</button></form></section><section><h2>Execution history</h2>
<p>Frames observe chart state before side effects complete. Each event expands
into its ordered microsteps. Retained {len(data["frames"])};
omitted {data["omitted_frames"]}.</p>
{"".join(history)}</section></div><div><section><h2>Current snapshot</h2>
<pre>{pretty(data["snapshot"])}</pre></section><section><h2>Run controls</h2>
<p><a href="/export" download="fetch-run.json">Export run as JSON</a></p>
<form method="post">{hidden}<input type="hidden" name="operation" value="reset">
<label for="scenario">Scenario</label>
<select id="scenario" name="scenario">{options}</select>
<button>Reset run</button></form>
<p>Reset discards this run. Export first to keep a copy.</p>
</section><section><h2>XState JSON</h2><p>The chart is read-only in this example.</p>
<details><summary>View definition</summary><pre>{pretty(data["config"])}</pre></details>
</section></div></div></main></html>"""


class InspectorServer(HTTPServer):
    inspector_session: InspectorSession


def make_server(port: int = 0) -> InspectorServer:
    session = InspectorSession()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, format: str, *args: Any) -> None:
            pass

        def respond(self, status: int, body: str, content_type: str) -> None:
            payload = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; "
                "style-src 'unsafe-inline'; form-action 'self'; "
                "frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self) -> bool:
            return (
                self.headers.get("Host")
                == f"127.0.0.1:{cast(InspectorServer, self.server).server_port}"
            )

        def do_GET(self) -> None:
            if not self.valid_host():
                self.respond(403, "Invalid host", "text/plain")
            elif self.path == "/":
                self.respond(200, page(session, token), "text/html")
            elif self.path == "/export":
                self.respond(200, json.dumps(session.export()), "application/json")
            else:
                self.respond(404, "Not found", "text/plain")

        def do_POST(self) -> None:
            nonlocal session
            origin = (
                f"http://127.0.0.1:{cast(InspectorServer, self.server).server_port}"
            )
            if (
                not self.valid_host()
                or self.path != "/"
                or self.headers.get("Origin") not in (None, origin)
            ):
                self.respond(403, "Invalid origin", "text/plain")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 8192:
                    raise ValueError("Request must contain at most 8192 bytes.")
                form = parse_qs(self.rfile.read(size).decode(), strict_parsing=True)
                if not hmac.compare_digest(
                    form.get("token", [""])[0].encode(), token.encode()
                ):
                    self.respond(403, "Invalid token", "text/plain")
                    return
                op = form.get("operation", [""])[0]
                if op == "reset":
                    scenario = form.get("scenario", [""])[0]
                    if scenario not in SCENARIOS:
                        raise ValueError("Unknown scenario.")
                    replacement = InspectorSession(scenario)
                    session.close()
                    session = replacement
                    cast(InspectorServer, self.server).inspector_session = session
                elif op == "event":
                    session.command(
                        {"kind": "event", "event": json.loads(form["event"][0])}
                    )
                elif op == "advance":
                    session.command({"kind": "advance", "ms": int(form["ms"][0])})
                else:
                    raise ValueError("Unknown operation.")
            except (ValueError, KeyError, UnicodeError) as exc:
                self.respond(400, page(session, token, str(exc)), "text/html")
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

    try:
        server = InspectorServer(("127.0.0.1", port), Handler)
    except BaseException:
        session.close()
        raise
    server.inspector_session = session
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f"Fetch inspector: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.inspector_session.close()
        server.server_close()


if __name__ == "__main__":
    main()
