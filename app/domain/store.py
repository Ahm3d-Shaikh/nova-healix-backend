"""In-memory mission data (frontend `mock-database.ts`).

Holds the generated crew data plus everything written at runtime. The scoring engine reads it
synchronously; persistence of the runtime parts is done by the services, which write through to
the database (Supabase or memory) and reload the rows at startup.
"""

import math
from dataclasses import dataclass, field

from app.domain.generator import CrewBundle, ExerciseSession, generate_crew
from app.domain.metrics import CHECKIN_METRICS, METRICS
from app.domain.mission_plan import BASELINE_FROM_DAY, BASELINE_TO_DAY, CREW_IDS, MISSION_EVENTS, at
from app.domain.personas import PERSONAS
from app.domain.questionnaires import seed_assignments
from app.domain.stats import Series, mean, percentile, sd
from app.schemas.actions import ActionLogEntry, CrewMessage
from app.schemas.assessment import Resolution
from app.schemas.crew import Astronaut
from app.schemas.crewmode import Assignment
from app.schemas.echo import LonelinessAssessment
from app.schemas.mission import MissionEvent
from app.schemas.mobility import MobilityCheck
from app.schemas.nova import SharedNote
from app.schemas.telemetry import Baseline, CheckIn

# Minimum half-band per metric so baselines never collapse to a line.
MIN_HALF_BAND: dict[str, float] = {
    "sleepDuration": 0.5,
    "sleepEfficiency": 3,
    "mood": 0.45,
    "energy": 0.45,
    "sleepQuality": 0.45,
    "stress": 8,
    "workload": 8,
    "co2": 0.3,
    "reactionTime": 18,
    "visionAcuity": 0.08,
    "wbc": 0.9,
    "lymphocytes": 0.3,
    "boneMarker": 7,
    "doseRate": 12,
}


@dataclass(frozen=True)
class SafetyFlag:
    """Raised only under the safety exception. Carries no transcript, by design."""

    id: str
    crew_id: str
    at: float
    category: str
    signal: str


@dataclass
class MissionData:
    _bundles: dict[str, CrewBundle] = field(default_factory=dict)
    _baselines: dict[tuple[str, str], Baseline | None] = field(default_factory=dict)
    _submitted: dict[str, list[CheckIn]] = field(default_factory=dict)
    _derived: dict[tuple[str, str, int], Series] = field(default_factory=dict)
    _extra_events: list[MissionEvent] = field(default_factory=list)
    _assignments: list[Assignment] = field(default_factory=seed_assignments)
    _safety: list[SafetyFlag] = field(default_factory=list)
    _notes: list[SharedNote] = field(default_factory=list)
    _log: list[ActionLogEntry] = field(default_factory=list)
    _outbox: list[CrewMessage] = field(default_factory=list)
    _mobility: list[MobilityCheck] = field(default_factory=list)
    _echo: list[LonelinessAssessment] = field(default_factory=list)
    _resolutions: dict[str, Resolution] = field(default_factory=dict)
    version: int = 0

    # -- crew -----------------------------------------------------------------
    def crew(self) -> list[Astronaut]:
        return [PERSONAS[i].astronaut for i in CREW_IDS]

    def astronaut(self, crew_id: str) -> Astronaut | None:
        p = PERSONAS.get(crew_id)
        return p.astronaut if p else None

    def bundle(self, crew_id: str) -> CrewBundle:
        b = self._bundles.get(crew_id)
        if b is None:
            b = self._bundles[crew_id] = generate_crew(crew_id)
        return b

    # -- series -------------------------------------------------------------------
    def series(self, crew_id: str, metric: str) -> Series:
        """Full series (all generated hours). Callers slice to 'now'."""
        if metric in CHECKIN_METRICS:
            key = (crew_id, metric, self.version)
            s = self._derived.get(key)
            if s is None:
                s = Series()
                for c in self.check_ins(crew_id):
                    s.add(c.at, getattr(c, "sleep_quality" if metric == "sleepQuality" else metric))
                self._derived[key] = s
            return s
        return self.bundle(crew_id).series.get(metric) or self.bundle(crew_id).series.setdefault(metric, Series())

    def add_sample(self, crew_id: str, metric: str, t: float, v: float) -> None:
        """Insert a new measurement in time order (e.g. a questionnaire score)."""
        self.bundle(crew_id).series.setdefault(metric, Series()).insert_sorted(t, v)
        self._bump()

    # -- check-ins ---------------------------------------------------------------
    def check_ins(self, crew_id: str) -> list[CheckIn]:
        generated = self.bundle(crew_id).check_ins
        extra = self._submitted.get(crew_id, [])
        if not extra:
            return generated
        replaced = {c.day for c in extra}
        return sorted([*(c for c in generated if c.day not in replaced), *extra], key=lambda c: c.at)

    def add_check_in(self, check_in: CheckIn) -> None:
        lst = self._submitted.get(check_in.crew_id, [])
        self._submitted[check_in.crew_id] = [*(c for c in lst if c.day != check_in.day), check_in]
        self._bump()

    def exercise(self, crew_id: str) -> list[ExerciseSession]:
        return self.bundle(crew_id).exercise

    # -- events ----------------------------------------------------------------------
    def events(self) -> list[MissionEvent]:
        return [*MISSION_EVENTS, *self._extra_events]

    def set_external_events(self, events: list[MissionEvent]) -> None:
        """Events that come from real NASA data (replaced wholesale on every refresh)."""
        self._extra_events = list(events)
        self._bump()

    def touch(self) -> None:
        """Something the analysis depends on changed outside the store (e.g. the trajectory)."""
        self._bump()

    # -- crew mode --------------------------------------------------------------------
    def assignments(self, crew_id: str | None = None) -> list[Assignment]:
        return [a for a in self._assignments if crew_id is None or a.crew_id == crew_id]

    def upsert_assignment(self, a: Assignment) -> None:
        """Replace the assignment with the same id, or add it."""
        if any(x.id == a.id for x in self._assignments):
            self._assignments = [a if x.id == a.id else x for x in self._assignments]
        else:
            self._assignments = [*self._assignments, a]
        self._bump()

    def safety_flags(self) -> list[SafetyFlag]:
        return self._safety

    def add_safety_flag(self, f: SafetyFlag) -> None:
        self._safety.append(f)
        self._bump()

    def shared_notes(self) -> list[SharedNote]:
        return self._notes

    def add_shared_note(self, n: SharedNote) -> None:
        self._notes.append(n)
        self._bump()

    def mobility_checks(self, crew_id: str | None = None) -> list[MobilityCheck]:
        """Mobility & Balance checks, oldest first."""
        return [c for c in self._mobility if crew_id is None or c.crew_id == crew_id]

    def add_mobility_check(self, c: MobilityCheck) -> None:
        self._mobility = sorted([*self._mobility, c], key=lambda x: x.at)
        self._bump()

    def echo_assessments(self, crew_id: str | None = None) -> list[LonelinessAssessment]:
        """ECHO loneliness assessments, oldest first."""
        return [a for a in self._echo if crew_id is None or a.crew_id == crew_id]

    def add_echo_assessment(self, a: LonelinessAssessment) -> None:
        self._echo = sorted([*self._echo, a], key=lambda x: x.at)
        self._bump()

    # -- mission control -----------------------------------------------------------------
    def action_log(self, insight_id: str | None = None) -> list[ActionLogEntry]:
        return [e for e in self._log if insight_id is None or e.insight_id == insight_id]

    def add_log(self, e: ActionLogEntry) -> None:
        self._log.append(e)
        self._bump()

    def resolution(self, insight_id: str) -> Resolution | None:
        return self._resolutions.get(insight_id)

    def resolve(self, insight_id: str, r: Resolution) -> None:
        self._resolutions[insight_id] = r
        self._bump()

    def reopen(self, insight_id: str) -> None:
        self._resolutions.pop(insight_id, None)
        self._bump()

    def crew_messages(self, crew_id: str) -> list[CrewMessage]:
        return [m for m in self._outbox if m.crew_id == crew_id]

    def add_message(self, m: CrewMessage) -> None:
        self._outbox.append(m)
        self._bump()

    # -- activity + baselines -----------------------------------------------------------
    def is_active(self, crew_id: str, hour: float) -> bool:
        """Is the astronaut doing scheduled exercise or EVA at this hour (excluded from baselines)?"""
        b = self.bundle(crew_id)
        h = math.floor(hour)
        in_range = 0 <= h < len(b.exercise_load)
        return in_range and (b.exercise_load[h] > 0 or b.eva[h] > 0)

    def baseline(self, crew_id: str, metric: str) -> Baseline | None:
        """Personal baseline from the astronaut's own data. None where a band is not meaningful."""
        key = (crew_id, metric)
        if key not in self._baselines:
            self._baselines[key] = self._compute_baseline(crew_id, metric)
        return self._baselines[key]

    def _compute_baseline(self, crew_id: str, metric: str) -> Baseline | None:
        d = METRICS[metric]
        series = self.series(crew_id, metric)
        if metric in ("radDose", "medKit"):
            return None
        if d.cadence == "monthly":
            vals = series.slice(at(1, 0), at(60, 23.99)).v
            m = mean(vals)
            half = max(1.4 * sd(vals), MIN_HALF_BAND.get(metric, 0))
            return Baseline(mean=m, low=m - half, high=m + half, source="Early-mission labs D15–D45")
        if metric in ("boneDensity", "muscleMass", "legStrength"):
            if not len(series):
                return None
            pre = series.v[0]
            tol = 0.03 if metric == "legStrength" else 0.015
            return Baseline(mean=pre, low=pre * (1 - tol), high=pre * (1 + tol), source="Preflight / first measurement")
        window = series.slice(at(BASELINE_FROM_DAY, 0), at(BASELINE_TO_DAY, 23.99))
        if d.cadence == "hourly":
            vals = [v for t, v in window.pairs() if not self.is_active(crew_id, t)]
            return Baseline(
                mean=mean(vals),
                low=percentile(vals, 0.05),
                high=percentile(vals, 0.95),
                source=f"In-flight D{BASELINE_FROM_DAY}–D{BASELINE_TO_DAY}, resting",
            )
        if d.cadence == "weekly":
            window = series.slice(at(7, 0), at(42, 23.99))
        vals = window.v
        m = mean(vals)
        half = max(1.4 * sd(vals), MIN_HALF_BAND.get(metric, 0))
        source = "In-flight D7–D42" if d.cadence == "weekly" else f"In-flight D{BASELINE_FROM_DAY}–D{BASELINE_TO_DAY}"
        return Baseline(mean=m, low=m - half, high=m + half, source=source)

    def _bump(self) -> None:
        self.version += 1
