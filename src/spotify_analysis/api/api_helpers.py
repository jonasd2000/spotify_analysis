import asyncio
import logging
from typing import Optional, Callable, Awaitable
import time


logger = logging.getLogger(__name__)


def retry(func: Callable, *args, retries: int=3, delay: float=1, backoff: Optional[float]=2, on_exceptions: Optional[list[type[Exception]]]=None, **kwargs):
    def wrapper(*args, **kwargs):
        for i in range(retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if (on_exceptions is not None) and (type(e) not in on_exceptions):
                    raise
                sleep_time = delay * ((backoff or 1) ** i)
                logger.debug(f"Retrying {func.__name__} in {sleep_time} seconds...")
                time.sleep(sleep_time)
    return wrapper

def async_retry(func: Awaitable, *args, retries: int=3, delay: float=1, backoff: Optional[float]=2, on_exceptions: Optional[list[type[Exception]]]=None, **kwargs):
    async def wrapper(*args, **kwargs):
        exc = None
        for i in range(retries):
            try:
                return (await func(*args, **kwargs))
            except Exception as e:
                if (on_exceptions is not None) and (type(e) not in on_exceptions):
                    raise
                exc = e
                sleep_time = delay * ((backoff or 1) ** i)
                logger.debug(f"Retrying {func.__name__} in {sleep_time} seconds due to {str(e)}...")
                await asyncio.sleep(sleep_time)
        raise exc
    return wrapper