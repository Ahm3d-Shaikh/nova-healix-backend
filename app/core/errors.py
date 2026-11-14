"""Domain errors, mapped to HTTP responses in one place (app.main)."""


class DomainError(Exception):
    """Base class for expected, client-visible errors."""


class UnknownAstronautError(DomainError):
    def __init__(self, astronaut_id: str) -> None:
        super().__init__(f"Unknown astronaut '{astronaut_id}'")


class InvalidDayError(DomainError):
    def __init__(self, day: int, mission_days: int) -> None:
        super().__init__(f"Mission day {day} is outside 1-{mission_days}")


class NoValidResponsesError(DomainError):
    def __init__(self) -> None:
        super().__init__("Every response was a false start; nothing to score")
