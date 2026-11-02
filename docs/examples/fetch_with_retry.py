#!/usr/bin/env python3
"""Run a JSON fetch/retry chart with named Python implementations.

All fetches are synthetic. Each factory owns its attempt counter; neither the
CLI nor the local inspector contacts a network service. The JSON contains literal
invoke input for user 42; dynamic input callables remain a Python binding concern.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xstate import HandlerArgs, Machine, assign, create_actor, from_promise
from xstate.scheduler import SimulatedClock

SCENARIOS = {"retry-success": 2, "success": 0, "exhausted": 3}
CHART = Path(__file__).with_suffix(".json")


@dataclass
class FetchSource:
    failures: int
    attempts: int = 0

    def fetch(self, input: dict[str, Any]) -> dict[str, Any]:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RuntimeError("503 Service Unavailable")
        return {"id": input["user_id"], "name": "Ada Lovelace"}


def can_retry(args: HandlerArgs) -> bool:
    return bool(args.context["retries"] < args.context["max_retries"])


def retries_exhausted(args: HandlerArgs) -> bool:
    return bool(args.context["retries"] >= args.context["max_retries"])


def build_machine(scenario: str = "retry-success") -> tuple[Machine, FetchSource]:
    """Construct independent runtime resources for one deterministic run."""
    source = FetchSource(SCENARIOS[scenario])
    config = json.loads(CHART.read_text())
    machine = Machine(
        config,
        actions={
            "rememberData": assign({"data": lambda c, e: e.data}),
            "rememberError": assign(
                {
                    "error": lambda c, e: str(e.data),
                    "retries": lambda c, e: c["retries"] + 1,
                }
            ),
        },
        guards={"canRetry": can_retry, "exhausted": retries_exhausted},
        delays={"backoff": 1000},
        actors={"fetchUser": from_promise(source.fetch)},
    )
    return machine, source


def main() -> None:
    machine, _source = build_machine()
    clock = SimulatedClock()
    actor = create_actor(machine, clock=clock)
    try:
        actor.start()
        actor.send("FETCH")
        clock.increment(1000)
        clock.increment(1000)
        snap = actor.get_snapshot()
        print(f"final value : {snap.value}")
        print(f"loaded data : {snap.context['data']}")
    finally:
        actor.stop()


if __name__ == "__main__":
    main()
