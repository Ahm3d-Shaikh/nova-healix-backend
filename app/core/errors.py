"""Domain errors, mapped to HTTP responses in one place (app.main)."""


class DomainError(Exception):
    """Base class for expected, client-visible errors."""


class UnknownAstronautError(DomainError):
    def __init__(self, astronaut_id: str) -> None:
        super().__init__(f"Unknown astronaut '{astronaut_id}'")


class InvalidDayError(DomainError):
    def __init__(self, day: int, mission_days: int) -> None:
        super().__init__(f"Mission day {day} is outside 1-{mission_days}")


class SessionNotFoundError(DomainError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"Unknown check-in session '{session_id}'")


class SessionClosedError(DomainError):
    def __init__(self) -> None:
        super().__init__("This check-in session is already completed; start a new one")


class SessionTurnLimitError(DomainError):
    def __init__(self, max_turns: int) -> None:
        super().__init__(f"Reply limit of {max_turns} reached; complete the check-in to get a score")


class NotEnoughTurnsError(DomainError):
    def __init__(self, have: int, need: int) -> None:
        super().__init__(f"Need at least {need} astronaut replies to score the check-in (have {have})")


class CompanionUnavailableError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"AI check-in companion unavailable: {reason}")
