from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from ..calculations import NORMAL_BREW_RATIO_MAX, NORMAL_BREW_RATIO_MIN
from ..services.brew_errors import (
    BrewConflictError,
    BrewNotFoundError,
    BrewPermissionError,
    BrewValidationError,
    UnusualBrewRatioError,
)


@contextmanager
def brew_http_errors() -> Iterator[None]:
    try:
        yield
    except UnusualBrewRatioError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Brew ratio 1:{exc.ratio:g} is outside the normal "
                f"1:{NORMAL_BREW_RATIO_MIN:g}–1:{NORMAL_BREW_RATIO_MAX:g} range. "
                "Check that coffee dose and water are total batch amounts, or retry with "
                "X-Confirm-Unusual-Ratio: true."
            ),
        ) from exc
    except BrewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=exc.detail) from exc
    except BrewConflictError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except BrewPermissionError as exc:
        raise HTTPException(status_code=403, detail=exc.detail) from exc
    except BrewValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
