import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from app.contracts.events import EventEnvelope, EventType


def event_message(event_type: EventType, **data: str) -> EventEnvelope:
    return EventEnvelope(type=event_type, emitted_at=datetime.now(UTC), data=data)


@dataclass(eq=False)
class Subscription:
    events: asyncio.Queue[EventEnvelope]
    overflow: asyncio.Event


class EventBroker:
    def __init__(self, queue_size: int = 32):
        self._queue_size = queue_size
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscriptions: set[Subscription] = set()

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()

    def stop(self) -> None:
        self._loop = None
        self._subscriptions.clear()

    @contextmanager
    def subscribe(self) -> Iterator[Subscription]:
        subscription = Subscription(asyncio.Queue(maxsize=self._queue_size), asyncio.Event())
        self._subscriptions.add(subscription)
        try:
            yield subscription
        finally:
            self._subscriptions.discard(subscription)

    def notify(self, event: EventEnvelope) -> None:
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(self._broadcast, event)
            except RuntimeError:
                # The loop can close during shutdown after an incident has committed.
                if not loop.is_closed():
                    raise

    def _broadcast(self, event: EventEnvelope) -> None:
        for subscription in tuple(self._subscriptions):
            try:
                subscription.events.put_nowait(event)
            except asyncio.QueueFull:
                self._subscriptions.discard(subscription)
                subscription.overflow.set()
