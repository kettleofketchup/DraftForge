from collections.abc import Sequence
from typing import Any


class ImmutableFieldError(ValueError): ...


class LedgerAppendOnlyError(RuntimeError): ...


class SpotTransferRefused(ValueError):
    def __init__(
        self, code: str, message: str, reasons: Sequence[dict[str, Any]] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.reasons = reasons
