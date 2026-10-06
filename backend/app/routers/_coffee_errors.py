from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from ..services.coffee_errors import (
    CoffeeConflictError,
    CoffeeNotFoundError,
    CoffeePermissionError,
)


@contextmanager
def coffee_http_errors() -> Iterator[None]:
    try:
        yield
    except CoffeeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except CoffeeConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except CoffeePermissionError as exc:
        raise HTTPException(status_code=403, detail=exc.detail) from exc
