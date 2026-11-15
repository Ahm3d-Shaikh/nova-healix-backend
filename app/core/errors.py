"""Domain errors, mapped to HTTP responses in one place (app.main)."""


class DomainError(Exception):
    """Base class for expected, client-visible errors. Maps to 400 unless a subclass is registered."""


class NotFoundError(DomainError):
    """404."""


class ConflictError(DomainError):
    """409."""


class UnavailableError(DomainError):
    """503: something we depend on (database, Gemini) is not available."""


class InvalidInputError(DomainError):
    """422: the request is well-formed but its values are not acceptable."""


class UnknownAstronautError(NotFoundError):
    def __init__(self, astronaut_id: str) -> None:
        super().__init__(f"Unknown astronaut '{astronaut_id}'")


# -- Nova Healix API v2 ---------------------------------------------------------------------------------------
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


class InvalidAnswersError(InvalidInputError):
    pass


class CompanionUnavailableError(UnavailableError):
    """A companion (Nova or ECHO) cannot answer: not configured, rate limited, timed out or blocked."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Companion unavailable: {reason}")


# -- ECHO check-in chat -------------------------------------------------------------------------------------------
class SessionNotFoundError(NotFoundError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Unknown check-in session '{session_id}'")


class SessionClosedError(ConflictError):
    def __init__(self) -> None:
        super().__init__("This check-in session is already completed; start a new one")


class SessionTurnLimitError(ConflictError):
    def __init__(self, max_turns: int) -> None:
        super().__init__(f"Reply limit of {max_turns} reached; complete the check-in to get a score")


class NotEnoughTurnsError(ConflictError):
    def __init__(self, have: int, need: int) -> None:
        super().__init__(f"Need at least {need} astronaut replies to score the check-in (have {have})")
