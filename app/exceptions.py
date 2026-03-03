"""Custom exceptions for NexusAPI."""


class InsufficientCreditsError(Exception):
    """Raised when an organisation does not have enough credits."""

    def __init__(self, balance: int, required: int):
        self.balance = balance
        self.required = required
        super().__init__(
            f"Insufficient credits: balance={balance}, required={required}"
        )


class OrganisationAccessError(Exception):
    """Raised when a user tries to access another organisation's data."""

    def __init__(self, message: str = "Access denied to this organisation's data"):
        super().__init__(message)


class IdempotencyConflictError(Exception):
    """Raised when an idempotency key has already been used."""

    def __init__(self, idempotency_key: str):
        self.idempotency_key = idempotency_key
        super().__init__(f"Idempotency key already used: {idempotency_key}")
