"""Domain errors, mapped to HTTP responses in one place (app.main)."""


class DomainError(Exception):
    """Base class for expected, client-visible errors. Maps to 400 unless a subclass is registered."""


class NotFoundError(DomainError):
    """404."""


class ConflictError(DomainError):
    """409."""


class UnavailableError(DomainError):
    """503: something we depend on (database, Gemini) is not available."""


class UnknownAstronautError(NotFoundError):
    def __init__(self, astronaut_id: str) -> None:
        super().__init__(f"Unknown astronaut '{astronaut_id}'")


class UnknownMetricError(NotFoundError):
    def __init__(self, metric: str) -> None:
        super().__init__(f"Unknown metric '{metric}'")


class UnknownHazardError(NotFoundError):
    def __init__(self, hazard: str) -> None:
        super().__init__(f"Unknown hazard '{hazard}'")


class UnknownAssignmentError(NotFoundError):
    def __init__(self, assignment_id: str) -> None:
        super().__init__(f"Unknown assignment '{assignment_id}'")


class AlreadySubmittedError(ConflictError):
    def __init__(self) -> None:
        super().__init__("This questionnaire is already submitted")


class InvalidAnswersError(DomainError):
    pass


class CompanionUnavailableError(UnavailableError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"Companion unavailable: {reason}")
