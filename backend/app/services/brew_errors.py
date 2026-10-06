from __future__ import annotations


class BrewError(Exception):
    def __init__(self, detail: str | dict[str, str]):
        self.detail = detail
        super().__init__(detail if isinstance(detail, str) else detail["message"])


class BrewNotFoundError(BrewError):
    pass


class BrewConflictError(BrewError):
    pass


class BrewPermissionError(BrewError):
    pass


class BrewValidationError(BrewError):
    pass


class UnusualBrewRatioError(BrewValidationError):
    def __init__(self, ratio: float):
        self.ratio = ratio
        super().__init__(f"Brew ratio 1:{ratio:g} requires explicit confirmation")
