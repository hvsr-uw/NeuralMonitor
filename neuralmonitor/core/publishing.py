from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

EventPublisher = Callable[[str, dict], Awaitable[None]]


@dataclass(frozen=True)
class PublishResult:
    topic: str
    delivered: bool
    attempts: int
    error: str | None = None


class RetryingPublisher:
    def __init__(
        self,
        publisher: EventPublisher,
        attempts: int = 3,
        base_delay_ms: int = 25,
    ) -> None:
        self.publisher = publisher
        self.attempts = max(1, attempts)
        self.base_delay_ms = max(0, base_delay_ms)
        self.last_results: list[PublishResult] = []

    async def __call__(self, topic: str, payload: dict) -> None:
        result = await self.publish(topic, payload)
        if not result.delivered:
            logger.error(
                "failed to publish event",
                extra={"topic": topic, "attempts": result.attempts, "error": result.error},
            )

    async def publish(self, topic: str, payload: dict) -> PublishResult:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                await self.publisher(topic, payload)
                result = PublishResult(topic=topic, delivered=True, attempts=attempt)
                self._remember(result)
                return result
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "publish attempt failed",
                    extra={"topic": topic, "attempt": attempt, "error": str(exc)},
                )
                if attempt < self.attempts and self.base_delay_ms:
                    await asyncio.sleep((self.base_delay_ms / 1000) * (2 ** (attempt - 1)))

        result = PublishResult(
            topic=topic,
            delivered=False,
            attempts=self.attempts,
            error=str(last_error) if last_error else "unknown",
        )
        self._remember(result)
        return result

    def _remember(self, result: PublishResult) -> None:
        self.last_results.append(result)
        self.last_results = self.last_results[-50:]


async def noop_publish(topic: str, payload: dict) -> None:
    return None

