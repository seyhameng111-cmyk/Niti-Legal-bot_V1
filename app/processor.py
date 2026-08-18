from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from app.handlers import BotHandlers

logger = logging.getLogger(__name__)


class QueueFullError(RuntimeError):
    pass


class UpdateProcessor:
    """Acknowledge Telegram quickly, then process updates with async workers."""

    def __init__(
        self, handlers: BotHandlers, queue_size: int = 500, worker_count: int = 4
    ) -> None:
        self.handlers = handlers
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_size)
        self.worker_count = worker_count
        self._workers: list[asyncio.Task[None]] = []
        self._seen_ids: set[int] = set()
        self._seen_order: deque[int] = deque()
        self._seen_limit = max(2000, queue_size * 2)

    async def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"telegram-worker-{index}")
            for index in range(self.worker_count)
        ]

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    def enqueue(self, update: dict[str, Any]) -> bool:
        update_id = update.get("update_id")
        if isinstance(update_id, int) and update_id in self._seen_ids:
            return False
        try:
            self.queue.put_nowait(update)
        except asyncio.QueueFull as exc:
            raise QueueFullError from exc
        if isinstance(update_id, int):
            self._remember(update_id)
        return True

    def _remember(self, update_id: int) -> None:
        if len(self._seen_order) >= self._seen_limit:
            oldest = self._seen_order.popleft()
            self._seen_ids.discard(oldest)
        self._seen_order.append(update_id)
        self._seen_ids.add(update_id)

    async def _worker(self, index: int) -> None:
        while True:
            update = await self.queue.get()
            try:
                await self.handlers.handle(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Unhandled update error worker=%s update_id=%s",
                    index,
                    update.get("update_id"),
                )
            finally:
                self.queue.task_done()
