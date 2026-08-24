"""Structural actor reference boundary tests."""

from xstate import ActorRef, ActorSnapshot, SubscriptionProtocol, to_promise


class _Subscription:
    def __init__(self):
        self.unsubscribed = False

    def unsubscribe(self) -> None:
        self.unsubscribed = True


class _ActorRefDouble:
    id = "double"

    def __init__(self):
        self.snapshot = ActorSnapshot("done", output=42)

    def send(self, event: str) -> ActorSnapshot[int]:
        _ = event
        return self.snapshot

    def get_snapshot(self) -> ActorSnapshot[int]:
        return self.snapshot

    def subscribe(self, listener) -> SubscriptionProtocol:
        listener(self.snapshot)
        return _Subscription()


def test_structural_double_satisfies_actor_ref_at_runtime():
    assert isinstance(_ActorRefDouble(), ActorRef)


async def test_to_promise_accepts_structural_actor_ref():
    actor_ref: ActorRef[str, ActorSnapshot[int]] = _ActorRefDouble()

    assert await to_promise(actor_ref) == 42
