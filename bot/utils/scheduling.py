"""Task scheduling."""

import asyncio
import typing as t
from contextlib import suppress
from datetime import datetime
from functools import partial
from inspect import getcoroutinestate

from arrow import Arrow
from loguru import logger


class Scheduler:
    """An async task scheduler."""

    def __init__(self, name: str):
        self.name = name
        self._scheduled_tasks: t.Dict[t.Hashable, asyncio.Task] = {}

    def __contains__(self, task_id: t.Hashable) -> bool:
        return task_id in self._scheduled_tasks

    def schedule(self, task_id: t.Hashable, coroutine: t.Coroutine) -> None:
        """Schedules `coroutine` to start immediately."""
        logger.trace(f"{self.name}: Scheduling task #{task_id}")

        msg = f"Cannot schedule an already started coroutine for #{task_id}"
        assert getcoroutinestate(coroutine) == "CORO_CREATED", msg

        if task_id in self._scheduled_tasks:
            logger.debug(f"{self.name}: Did not schedule task #{task_id}; task was already scheduled")
            coroutine.close()
            return

        task = asyncio.create_task(coroutine, name=f"{self.name}_{task_id}")
        task.add_done_callback(partial(self._task_done_callback, task_id))

        self._scheduled_tasks[task_id] = task
        logger.debug(f"{self.name}: Scheduled task #{task_id} {id(task)}.")

    def schedule_at(self, time: t.Union[datetime, Arrow], task_id: t.Hashable, coroutine: t.Coroutine) -> None:
        """Schedules `coroutine` to be executed at the given `time`.

        If `time` is timezone aware, then use that timezone to calculate now()
        when subtracting. If `time` is naïve, then use UTC.

        If `time` is in the past, schedule `coroutine` immediately.

        If a task with `task_id` already exists, close `coroutine` instead of
        scheduling it. This prevents unawaited coroutine warnings. Don't pass a
        coroutine that'll be re-used elsewhere.
        """
        now_datetime = datetime.now(time.tzinfo) if time.tzinfo else datetime.utcnow()
        delay = (time - now_datetime).total_seconds()
        if delay > 0:
            coroutine = self._await_later(delay, task_id, coroutine)

        self.schedule(task_id, coroutine)

    def schedule_later(self, delay: t.Union[int, float], task_id: t.Hashable, coroutine: t.Coroutine) -> None:
        """Schedules `coroutine` to be executed after the given `delay` number
        of seconds.

        If a task with `task_id` already exists, close `coroutine` instead of
        scheduling it. This prevents unawaited coroutine warnings. Don't pass a
        coroutine that'll be re-used elsewhere.
        """
        self.schedule(task_id, self._await_later(delay, task_id, coroutine))

    def cancel(self, task_id: t.Hashable) -> None:
        """Unschedules the task identified by `task_id`. Log a warning if the
        task doesn't exist.
        """
        logger.trace(f"{self.name}: Cancelling task #{task_id}...")

        try:
            task = self._scheduled_tasks.pop(task_id)
        except KeyError:
            logger.warning(f"{self.name}: Failed to unschedule {task_id} (no task found).")
        else:
            task.cancel()

            logger.debug(f"{self.name}: Unscheduled task #{task_id} {id(task)}.")

    def cancel_all(self) -> None:
        """Unschedules all known tasks."""
        logger.debug(f"{self.name}: Unscheduling all tasks")

        for task_id in self._scheduled_tasks.copy():
            self.cancel(task_id)

    async def _await_later(self, delay: t.Union[int, float], task_id: t.Hashable, coroutine: t.Coroutine) -> None:
        """Awaits `coroutine` after the given `delay` number of seconds."""
        try:
            logger.trace(f"{self.name}: Waiting {delay} seconds before awaiting coroutine for #{task_id}.")
            await asyncio.sleep(delay)

            # Use asyncio.shield to prevent the coroutine from cancelling itself.
            logger.trace(f"{self.name}: Done waiting for #{task_id}; now awaiting the coroutine.")
            await asyncio.shield(coroutine)
        finally:
            # Close it to prevent unawaited coroutine warnings,
            # which would happen if the task was cancelled during the sleep.
            # Only close it if it's not been awaited yet. This check is important because the
            # coroutine may cancel this task, which would also trigger the finally block.
            state = getcoroutinestate(coroutine)
            if state == "CORO_CREATED":
                logger.debug(f"{self.name}: Explicitly closing the coroutine for #{task_id}.")
                coroutine.close()
            else:
                logger.debug(f"{self.name}: Finally block reached for #{task_id}; {state=}")

    def _task_done_callback(self, task_id: t.Hashable, done_task: asyncio.Task) -> None:
        """Deletes the task and raises its exception if one exists.

        If `done_task` and the task associated with `task_id` are different,
        then the latter will not be deleted. In this case, a new task was likely
        rescheduled with the same ID.
        """
        logger.trace(f"{self.name}: Performing done callback for task #{task_id} {id(done_task)}.")

        scheduled_task = self._scheduled_tasks.get(task_id)

        if scheduled_task and done_task is scheduled_task:
            # A task for the ID exists and is the same as the done task.
            # Since this is the done callback, the task is already done so no need to cancel it.
            logger.trace(f"{self.name}: Deleting task #{task_id} {id(done_task)}.")
            del self._scheduled_tasks[task_id]
        elif scheduled_task:
            # A new task was likely rescheduled with the same ID.
            logger.debug(
                f"{self.name}: "
                f"The scheduled task #{task_id} {id(scheduled_task)} "
                f"and the done task {id(done_task)} differ."
            )
        elif not done_task.cancelled():
            logger.warning(
                f"{self.name}: "
                f"Task #{task_id} not found while handling task {id(done_task)}! "
                f"A task somehow got unscheduled improperly (i.e. deleted but not cancelled)."
            )

        with suppress(asyncio.CancelledError):
            exception = done_task.exception()
            # Log the exception if one exists.
            if exception:
                logger.opt(exception=exception).error(f"{self.name}: Error in task #{task_id} {id(done_task)}!")


def create_task(
    coro: t.Awaitable,
    *,
    suppressed_exceptions: tuple[t.Type[Exception]] = (),
    event_loop: t.Optional[asyncio.AbstractEventLoop] = None,
    **kwargs,
) -> asyncio.Task:
    """Wrapper for creating asyncio `Task`s which logs exceptions raised in the
    task.

    If the loop kwarg is provided, the task is created from that event loop,
    otherwise the running loop is used.
    """
    if event_loop is not None:
        task = event_loop.create_task(coro, **kwargs)
    else:
        task = asyncio.create_task(coro, **kwargs)
    task.add_done_callback(partial(_log_task_exception, suppressed_exceptions=suppressed_exceptions))
    return task


def _log_task_exception(task: asyncio.Task, *, suppressed_exceptions: t.Tuple[t.Type[Exception]]) -> None:
    """Retrieves and logs the exception raised in `task` if one exists."""
    with suppress(asyncio.CancelledError):
        exception = task.exception()
        # Log the exception if one exists.
        if exception and not isinstance(exception, suppressed_exceptions):
            logger.opt(exception=exception).error(f"Error in task {task.get_name()} {id(task)}!")
