"""Resource locking utilities."""

import asyncio
import inspect
import types
from collections import defaultdict
from functools import partial
from typing import Any, Awaitable, Callable, Hashable
from weakref import WeakValueDictionary

from loguru import logger

from bot.errors import LockedResourceError
from bot.utils import function
from bot.utils.function import command_wraps

__lock_dicts = defaultdict(WeakValueDictionary)

_IdCallableReturn = Hashable | Awaitable[Hashable]
_IdCallable = Callable[[function.BoundArgs], _IdCallableReturn]
ResourceId = Hashable | _IdCallable


class SharedEvent:
    """
    Context manager managing an internal event exposed through the wait coro.

    While any code is executing in this context manager, the underlying event will not be set;
    when all of the holders finish the event will be set.
    """

    def __init__(self):
        self._active_count = 0
        self._event = asyncio.Event()
        self._event.set()

    def __enter__(self):
        """Increment the count of the active holders and clear the internal event."""
        self._active_count += 1
        self._event.clear()

    def __exit__(self, _exc_type, _exc_val, _exc_tb):  # noqa: ANN001
        """Decrement the count of the active holders; if 0 is reached set the internal event."""
        self._active_count -= 1
        if not self._active_count:
            self._event.set()

    async def wait(self) -> None:
        """Wait for all active holders to exit."""
        await self._event.wait()


def lock(
    namespace: Hashable,
    resource_id: ResourceId,
    *,
    raise_error: bool = False,
    wait: bool = False,
) -> Callable:
    """
    Turn the decorated coroutine function into a mutually exclusive operation on a `resource_id`.

    If `wait` is True, wait until the lock becomes available. Otherwise, if any other mutually
    exclusive function currently holds the lock for a resource, do not run the decorated function
    and return None.

    If `raise_error` is True, raise `LockedResourceError` if the lock cannot be acquired.

    `namespace` is an identifier used to prevent collisions among resource IDs.

    `resource_id` identifies a resource on which to perform a mutually exclusive operation.
    It may also be a callable or awaitable which will return the resource ID given an ordered
    mapping of the parameters' names to arguments' values.

    If decorating a command, this decorator must go before (below) the `command` decorator.
    """

    def decorator(func: types.FunctionType) -> types.FunctionType:
        name = func.__name__

        @command_wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            logger.trace(f"{name}: mutually exclusive decorator called")

            if callable(resource_id):
                logger.trace(f"{name}: binding args to signature")
                bound_args = function.get_bound_args(func, args, kwargs)

                logger.trace(f"{name}: calling the given callable to get the resource ID")
                id_ = resource_id(bound_args)

                if inspect.isawaitable(id_):
                    logger.trace(f"{name}: awaiting to get resource ID")
                    id_ = await id_
            else:
                id_ = resource_id

            logger.trace(f"{name}: getting the lock object for resource {namespace!r}:{id_!r}")

            # Get the lock for the ID. Create a lock if one doesn't exist yet.
            locks = __lock_dicts[namespace]
            lock_ = locks.setdefault(id_, asyncio.Lock())

            # It's safe to check an asyncio.Lock is free before acquiring it because:
            #   1. Synchronous code like `if not lock_.locked()` does not yield execution
            #   2. `asyncio.Lock.acquire()` does not internally await anything if the lock is free
            #   3. awaits only yield execution to the event loop at actual I/O boundaries
            if wait or not lock_.locked():
                logger.debug(f"{name}: acquiring lock for resource {namespace!r}:{id_!r}...")
                async with lock_:
                    return await func(*args, **kwargs)
            else:
                logger.info(f"{name}: aborted because resource {namespace!r}:{id_!r} is locked")
                if raise_error:
                    raise LockedResourceError(str(namespace), id_)

        return wrapper

    return decorator


def lock_arg(
    namespace: Hashable,
    name_or_pos: function.Argument,
    func: Callable[[Any], _IdCallableReturn] = None,
    *,
    raise_error: bool = False,
    wait: bool = False,
) -> Callable:
    """
    Apply the `lock` decorator using the value of the arg at the given name/position as the ID.

    `func` is an optional callable or awaitable which will return the ID given the argument value.
    See `lock` docs for more information.
    """
    decorator_func = partial(lock, namespace, raise_error=raise_error, wait=wait)
    return function.get_arg_value_wrapper(decorator_func, name_or_pos, func)
