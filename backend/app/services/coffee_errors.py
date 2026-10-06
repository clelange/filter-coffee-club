class CoffeeError(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class CoffeeNotFoundError(CoffeeError):
    pass


class CoffeeConflictError(CoffeeError):
    pass


class CoffeePermissionError(CoffeeError):
    pass
