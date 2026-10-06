from collections.abc import Callable
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar

from sqlalchemy.orm import Session

P = ParamSpec("P")
T = TypeVar("T")


def rollback_on_failure(
    workflow: Callable[Concatenate[Session, P], T],
) -> Callable[Concatenate[Session, P], T]:
    """Leave the session usable after a transactional command fails."""

    @wraps(workflow)
    def run(db: Session, *args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return workflow(db, *args, **kwargs)
        except BaseException:
            db.rollback()
            raise

    return run
