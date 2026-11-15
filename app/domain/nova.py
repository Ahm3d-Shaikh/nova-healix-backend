"""Nova, the astronaut's private companion: deterministic, conservative, rule-based (frontend `nova.ts`).

Safety messages are pre-written, never model-generated. Nova is supportive, never diagnostic.
This module only reads the astronaut's OWN shared data (to personalise); it never stores anything.
"""

import math
import re
from dataclasses import dataclass, field

from app.domain.format import format_delay, to_fixed
from app.domain.mission_plan import MISSION_EVENTS, hour_to_day
from app.domain.prng import js_round
from app.domain.stats import mean
from app.domain.store import MissionData
from app.schemas.nova import (
    BreathingCard,
    ChatCard,
    CheckInCard,
    CompanionState,
    NovaReply,
    SafetyCard,
    SafetyInfo,
    ShareCard,
)
from app.schemas.telemetry import CheckInDraft

I = re.IGNORECASE  # noqa: E741

SELF_HARM = re.compile(
    r"\b(kill myself|end my life|end it all|suicid\w*|hurt myself|harm myself|don'?t want to (live|be alive|wake up)|better off dead|want to die)\b",
    I,
)
MEDICAL = re.compile(
    r"(chest pain|can'?t breathe|cannot breathe|hard to breathe|face (is |feels )?numb|arm (is |feels )?numb|slurred|worst headache|passed out|fainted|blacked out|lost (my )?vision|sudden(ly)? (blind|can'?t see)|seizure)",
    I,
)
HOPELESS = re.compile(
    r"(what'?s the point|what is the point|no point|pointless|hopeless|can'?t go on|giving up|give up on|nothing matters|can'?t do this anymore|can'?t take (it|this) anymore|no way out)",
    I,
)
YES = re.compile(r"^\s*(yes|yeah|yep|i am|i do|sometimes|maybe|kind of|a bit|i think so)\b", I)
NO = re.compile(r"^\s*(no|nope|not really|never|i'?m not|no,)\b", I)
CHECKIN = re.compile(r"(check.?in|log (my )?day|daily report|fill (in|out) my)", I)
SHARE = re.compile(r"\b(tell|share|send|let)\b.*\b(haleem|doctor|surgeon|mission control|ground)\b", I)
BREATH = re.compile(r"(breath|panic|anxious|anxiety|calm (me )?down|heart racing|overwhelm)", I)
SLEEP = re.compile(r"(sleep|slept|insomnia|can'?t rest|awake all|tired|exhausted|nightmare)", I)
HOME = re.compile(
    r"(home|family|miss (my|them|her|him|the)|lonely|alone|isolat|kids|partner|wife|husband|mum|mom|dad)", I
)
EVA = re.compile(r"(eva|spacewalk|space walk|nervous|scared|afraid|worried about)", I)
SYMPTOM = re.compile(
    r"(headache|migraine|nausea|nauseous|sick to my stomach|blurr|vision|back (pain|hurts|ache)|congest|stuffy|blocked nose)",
    I,
)
CONFLICT = re.compile(r"(argu|conflict|annoy|fight|tension|crewmate|got on my nerves|snapped at)", I)
THANKS = re.compile(r"\b(thanks|thank you|cheers|appreciate)\b", I)
HELLO = re.compile(r"^\s*(hi|hello|hey|morning|good (morning|evening|afternoon))\b", I)
SHARE_PREFIX = re.compile(
    r"^\s*(please\s+)?(can you\s+|could you\s+)?(tell|share with|send (this |it )?to|let)\s+(haleem|the doctor|my doctor|the flight surgeon|mission control|the ground)(\s+know)?(\s+that)?[\s,:]*",
    I,
)

IDLE = CompanionState()


@dataclass
class NovaContext:
    db: MissionData
    crew_id: str
    hour: float
    delay_seconds: float
    surgeon: str
    state: CompanionState
    previous_text: str | None = None  # the astronaut's previous message (for "share that with...")


@dataclass
class NovaTurnResult:
    replies: list[NovaReply]
    state: CompanionState
    safety: SafetyInfo | None = None
    # True when no rule matched: the caller may use a language model for this reply instead.
    generic: bool = False
    extras: dict[str, object] = field(default_factory=dict)


def _name(ctx: NovaContext) -> str:
    a = ctx.db.astronaut(ctx.crew_id)
    return a.name if a else "there"


def _sleep_picture(ctx: NovaContext) -> tuple[float, float] | None:
    s = ctx.db.series(ctx.crew_id, "sleepDuration").slice(ctx.hour - 5 * 24, ctx.hour)
    b = ctx.db.baseline(ctx.crew_id, "sleepDuration")
    if not len(s) or not b:
        return None
    return mean(s.v), b.mean


def _next_eva(ctx: NovaContext) -> tuple[str, int] | None:
    evas = sorted(
        (e for e in MISSION_EVENTS if e.kind == "eva" and ctx.crew_id in e.crew_ids and e.start > ctx.hour),
        key=lambda e: e.start,
    )
    if not evas:
        return None
    e = evas[0]
    return e.label.split(" ")[0], math.ceil((e.start - ctx.hour) / 24)


def _checked_in_today(ctx: NovaContext) -> bool:
    today = hour_to_day(ctx.hour)
    return any(c.day == today and c.at <= ctx.hour for c in ctx.db.check_ins(ctx.crew_id))


def _medical_contact(ctx: NovaContext) -> str:
    """CMO for acute problems (someone else if the CMO is the one who is unwell)."""
    crew = ctx.db.crew()
    cmo = next((a for a in crew if a.role == "CMO"), None)
    if cmo and cmo.id != ctx.crew_id:
        return f"{cmo.name} (crew medical officer)"
    cdr = next((a for a in crew if a.role == "CDR"), None)
    return f"{cdr.name} (commander)" if cdr else "a crewmate"


# -- check-in extraction --------------------------------------------------------------------------------
def _score_words(text: str, table: list[tuple[str, int]], fallback: int) -> int:
    for pattern, value in table:
        if re.search(pattern, text):
            return value
    return fallback


def extract_check_in(ctx: NovaContext, text: str) -> tuple[CheckInDraft, int]:
    t = text.lower()
    found = 0
    mood = _score_words(
        t,
        [
            (r"(awful|terrible|miserable|horrible|really low|very low|depressed)", 1),
            (r"(low|down|sad|flat|stressed|not great|rough|bad day|homesick|lonely)", 2),
            (r"(\bok\b|okay|alright|meh|so-so|fine-ish)", 3),
            (r"(good|fine|well|happy|positive|content)", 4),
            (r"(great|excellent|amazing|fantastic|brilliant)", 5),
        ],
        0,
    )
    found += 1 if mood else 0
    sleep = _score_words(
        t,
        [
            (r"(no sleep|didn'?t sleep|barely slept|awful night|terrible night)", 1),
            (
                r"(slept (badly|poorly|bad)|bad night|rough night|woke up (a lot|often|twice|several)|couldn'?t sleep|broken sleep|restless)",
                2,
            ),
            (r"(slept (ok|okay|alright)|average night)", 3),
            (r"(slept (well|fine|good)|good night|good sleep)", 4),
            (r"(slept (great|really well|brilliantly)|best sleep)", 5),
        ],
        0,
    )
    found += 1 if sleep else 0
    energy = _score_words(
        t,
        [
            (r"(exhausted|drained|no energy|wiped out|shattered)", 1),
            (r"(tired|sleepy|sluggish|low energy|groggy)", 2),
            (r"(energ(y|etic|ised|ized)|lively|full of beans|sharp)", 4),
        ],
        0,
    )
    found += 1 if energy else 0
    symptoms: list[str] = []
    if re.search(r"(headache|migraine)", t):
        symptoms.append("headache")
    if re.search(r"(nause|sick to my stomach|queasy)", t):
        symptoms.append("nausea")
    if re.search(r"(blurr|vision)", t):
        symptoms.append("vision")
    if re.search(r"back (pain|hurts|ache|is sore)", t):
        symptoms.append("back-pain")
    if re.search(r"(congest|stuffy|blocked nose)", t):
        symptoms.append("congestion")
    found += len(symptoms)

    # Fill gaps from the astronaut's own recent data, so the draft is sensible.
    sp = _sleep_picture(ctx)
    sleep_from_data = (2 if sp[0] < sp[1] - 1 else 3 if sp[0] < sp[1] - 0.4 else 4) if sp else 3
    draft = CheckInDraft(
        mood=mood or 3,
        sleep_quality=sleep or sleep_from_data,
        energy=energy or (2 if sleep and sleep <= 2 else 3),
        symptoms=symptoms,
        # Privacy: never attach chat text to a shared check-in. The card shows exactly what is sent.
    )
    return draft, found


# -- the specific safety signal (a category for the clinician, never the words) ----------------------------
def _self_harm_signal(text: str, was_asked: bool) -> str:
    if re.search(r"(want to die|better off dead|don'?t want to (live|be alive|wake up))", text, I):
        return "wish-to-die"
    if re.search(r"(kill myself|suicid|end my life|end it all)", text, I):
        return "suicidal-thoughts"
    if re.search(r"(hurt myself|harm myself)", text, I):
        return "self-harm-intent"
    return "confirmed-when-asked" if was_asked else "suicidal-thoughts"


def _medical_signal(text: str) -> str:
    if re.search(r"chest pain", text, I):
        return "chest-pain"
    if re.search(r"(breathe)", text, I):
        return "breathing"
    if re.search(r"(numb|slurred)", text, I):
        return "stroke-signs"
    if re.search(r"(passed out|fainted|blacked out)", text, I):
        return "unconscious"
    if re.search(r"(vision|blind|can'?t see)", text, I):
        return "vision-loss"
    if re.search(r"headache", text, I):
        return "severe-headache"
    return "seizure"


def safety_message(ctx: NovaContext, category: str) -> str:
    """Pre-written, never generated."""
    delay = format_delay(ctx.delay_seconds)
    if category == "medical":
        return (
            f"These symptoms need medical attention now. Please tell {_medical_contact(ctx)} straight away, or use the crew intercom. "
            f"I have alerted {ctx.surgeon}, your flight surgeon, that you need urgent medical help. I only sent that, not what you wrote. "
            f"The alert reaches Earth in about {delay}. Stay where you are and do not exercise."
        )
    return (
        "Thank you for telling me. You don’t have to carry this alone. "
        f"I have let {ctx.surgeon}, your flight surgeon, know that you need support right now. I did not share what you wrote, only that it is urgent. "
        f"The message reaches Earth in about {delay}. If you can, find a crewmate now so you are not on your own. I’m here. Will you keep talking with me while you wait?"
    )


def _safety_turn(ctx: NovaContext, category: str, signal: str) -> NovaTurnResult:
    return NovaTurnResult(
        replies=[NovaReply(text=safety_message(ctx, category), card=SafetyCard(category=category))],
        state=IDLE,
        safety=SafetyInfo(category=category, signal=signal),
    )


# -- public API ---------------------------------------------------------------------------------------------------
def greeting(ctx: NovaContext) -> NovaTurnResult:
    lines = [f"Hi {_name(ctx)}. This is a private space: only you can see what we talk about. How are you doing today?"]
    sp = _sleep_picture(ctx)
    if sp and sp[0] < sp[1] - 0.8:
        lines.append(
            f"I noticed your sleep has been shorter than usual this week ({to_fixed(sp[0], 1)} h a night, you normally get {to_fixed(sp[1], 1)} h). "
            "We can talk about that if it helps."
        )
    if not _checked_in_today(ctx):
        lines.append(
            "Your daily check-in isn’t done yet. If you like, just tell me about your day and I’ll fill it in for you to review."
        )
    return NovaTurnResult([NovaReply(text=t) for t in lines], IDLE)


def respond(ctx: NovaContext, text: str) -> NovaTurnResult:
    s = ctx.state

    # 1. Safety always comes first.
    if SELF_HARM.search(text) or (s.pending_safety_check and YES.search(text)):
        return _safety_turn(ctx, "self-harm", _self_harm_signal(text, s.pending_safety_check))
    if MEDICAL.search(text):
        return _safety_turn(ctx, "medical", _medical_signal(text))
    if s.pending_safety_check and NO.search(text):
        return NovaTurnResult(
            [
                NovaReply(
                    text="Thank you for being honest with me. It still sounds really heavy. What has been weighing on you the most?"
                )
            ],
            IDLE,
        )
    if HOPELESS.search(text):
        return NovaTurnResult(
            [
                NovaReply(
                    text="That sounds really hard, and I want to make sure I understand. Are you having any thoughts of hurting yourself or of not wanting to be alive?"
                )
            ],
            CompanionState(pending_safety_check=True, awaiting_check_in=False),
        )

    # 2. Explicit requests.
    if SHARE.search(text):
        # Share what follows the request ("tell Haleem I'd like a call" -> "I'd like a call"),
        # otherwise the previous message, otherwise a neutral default.
        rest = SHARE_PREFIX.sub("", text, count=1).strip()
        own = rest[:1].upper() + rest[1:] if rest and rest != text.strip() and len(rest) > 6 else ""
        shared = own or (ctx.previous_text or "").strip() or "I would like to talk when you have time."
        return NovaTurnResult(
            [
                NovaReply(
                    text=f"I can send a note to {ctx.surgeon}. Here is what would be shared. Nothing else from our conversation goes with it. Send it?",
                    card=ShareCard(text=shared, status="proposed"),
                )
            ],
            IDLE,
        )

    if CHECKIN.search(text) or s.awaiting_check_in:
        draft, found = extract_check_in(ctx, text)
        if found == 0 and not s.awaiting_check_in:
            return NovaTurnResult(
                [
                    NovaReply(
                        text="Sure. In a sentence or two: how did you sleep, how is your mood and energy, and any symptoms like headache or nausea?"
                    )
                ],
                CompanionState(pending_safety_check=False, awaiting_check_in=True),
            )
        return NovaTurnResult(
            [
                NovaReply(
                    text="Here is your check-in from what you told me. Check-ins are shared with Mission Control, so review it before sending.",
                    card=CheckInCard(draft=draft, status="proposed"),
                )
            ],
            IDLE,
        )

    if BREATH.search(text):
        return NovaTurnResult(
            [
                NovaReply(
                    text="Let’s slow things down together. Breathe in for 4, hold for 4, out for 6. Follow the circle for a minute; I’ll be here after.",
                    card=BreathingCard(),
                )
            ],
            IDLE,
        )

    # 3. Topics, with the astronaut's own context.
    replies: list[NovaReply] = []
    generic = False
    if SYMPTOM.search(text):
        draft, _ = extract_check_in(ctx, text)
        vision = "vision" in draft.symptoms
        replies.append(
            NovaReply(
                text=(
                    f"Changes in vision are worth checking early in microgravity. Please mention it to {_medical_contact(ctx)} today. "
                    f"I can also log it in your check-in so {ctx.surgeon} sees it."
                    if vision
                    else "I’m sorry, that’s unpleasant. Logging symptoms helps spot patterns: CO₂ levels and fluid shift can both cause headaches up here. Want me to add it to today’s check-in?"
                ),
                card=CheckInCard(draft=draft, status="proposed"),
            )
        )
    elif SLEEP.search(text):
        sp = _sleep_picture(ctx)
        eva = _next_eva(ctx)
        msg = "Poor sleep is one of the hardest parts of a long flight."
        if sp and sp[0] < sp[1] - 0.5:
            msg += f" Your wearable shows about {to_fixed(sp[0], 1)} h a night lately, against your usual {to_fixed(sp[1], 1)} h."
        if eva and eva[1] <= 5:
            msg += f" With {eva[0]} in {eva[1]} days, protecting the next few nights matters."
        msg += " A few things that tend to help: dim the module lights an hour before, keep the sleep station cool, and park work thoughts on a list. Want a short breathing routine to wind down?"
        replies.append(NovaReply(text=msg))
    elif HOME.search(text):
        replies.append(
            NovaReply(
                text=(
                    "Missing home is completely normal this far out, and it often gets harder around the middle of a mission. "
                    "Some crews record a short video for family before each downlink window, so there is always something on its way. "
                    f"You could also ask {ctx.surgeon} for a private conference with the psychologist. Would talking about the people you miss help right now?"
                )
            )
        )
    elif EVA.search(text):
        eva = _next_eva(ctx)
        replies.append(
            NovaReply(
                text=(
                    f"Feeling nervous before {eva[0] if eva else 'a spacewalk'} is a sign you take it seriously. "
                    "It can help to walk through the timeline once more with your EVA partner and name the one step you are least sure about. "
                    "Sleep is the biggest single thing that improves performance outside. What part is on your mind?"
                )
            )
        )
    elif CONFLICT.search(text):
        replies.append(
            NovaReply(
                text=(
                    "Friction is almost guaranteed with four people in a small space for months. "
                    "If it helps, we can rehearse what you want to say: start with what you noticed, how it affected you, and one thing you would like to change. Want to try?"
                )
            )
        )
    elif THANKS.search(text):
        replies.append(NovaReply(text="Any time. I’m here whenever you want to talk, day or night."))
    elif HELLO.search(text):
        replies.append(NovaReply(text=f"Hi {_name(ctx)}. How are you feeling today?"))
    else:
        generic = True
        replies.append(
            NovaReply(
                text=(
                    "Thank you for telling me. That sounds like a lot to carry. Would you like to say more, or would something practical help: "
                    "a breathing exercise, a wind-down routine, or turning this into today’s check-in?"
                )
            )
        )
    return NovaTurnResult(replies, IDLE, generic=generic)


__all__ = [
    "ChatCard",
    "NovaContext",
    "NovaTurnResult",
    "extract_check_in",
    "greeting",
    "js_round",
    "respond",
    "safety_message",
]
