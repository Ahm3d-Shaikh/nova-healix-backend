-- RIDGE Monitor - Supabase schema.
-- Run once in the Supabase SQL editor (Dashboard -> SQL Editor -> New query -> paste -> Run).
-- Safe to re-run: every statement is idempotent.
--
-- Row Level Security is OFF on every table. The backend uses the service-role key.
-- WARNING: with RLS off, anyone holding this project's anon key can read and write these tables
-- through the Data API. Never put the anon key in a public frontend while RLS is off.

create extension if not exists pgcrypto;  -- gen_random_uuid()

-- ---------------------------------------------------------------------------
-- Crew roster and daily health records (seeded with the simulated crew on first start)
-- ---------------------------------------------------------------------------
create table if not exists public.astronauts (
    id          text primary key,
    name        text not null,
    role        text not null,
    story       text not null default '',
    created_at  timestamptz not null default now()
);

create table if not exists public.daily_records (
    astronaut_id      text not null references public.astronauts (id) on delete cascade,
    day               integer not null check (day >= 1),
    sleep_hours       double precision not null,
    resting_hr        double precision not null,
    sys_bp            double precision not null,
    dia_bp            double precision not null,
    exercise_min      double precision not null,
    co2_mmhg_1h       double precision not null,
    co2_mmhg_7d       double precision not null,
    cabin_temp_c      double precision not null,
    loneliness_q1     smallint not null check (loneliness_q1 between 1 and 3),
    loneliness_q2     smallint not null check (loneliness_q2 between 1 and 3),
    loneliness_q3     smallint not null check (loneliness_q3 between 1 and 3),
    self_rating       smallint not null check (self_rating between 1 and 10),
    pvt_mean_rt       double precision not null,
    pvt_mean_speed    double precision not null,
    pvt_lapses        integer not null,
    pvt_false_starts  integer not null,
    dose_msv          double precision not null,
    source            text not null default 'simulated',  -- 'simulated' | 'sensor' | 'manual'
    created_at        timestamptz not null default now(),
    primary key (astronaut_id, day)
);

-- ---------------------------------------------------------------------------
-- Demo settings (single row, id = 1)
-- ---------------------------------------------------------------------------
create table if not exists public.mission_settings (
    id               smallint primary key default 1 check (id = 1),
    mission          text not null default 'mars' check (mission in ('iss', 'moon', 'mars')),
    deep_space_mode  boolean not null default false,
    current_day      integer not null default 5 check (current_day >= 1),
    updated_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Isolation: AI check-in chats and the loneliness scores derived from them
-- ---------------------------------------------------------------------------
create table if not exists public.isolation_chat_sessions (
    id            uuid primary key default gen_random_uuid(),
    astronaut_id  text not null references public.astronauts (id) on delete cascade,
    mission_day   integer not null check (mission_day >= 1),
    status        text not null default 'active' check (status in ('active', 'completed')),
    created_at    timestamptz not null default now(),
    completed_at  timestamptz
);
create index if not exists isolation_chat_sessions_astronaut_idx
    on public.isolation_chat_sessions (astronaut_id, created_at);

create table if not exists public.isolation_chat_messages (
    id          uuid primary key default gen_random_uuid(),
    session_id  uuid not null references public.isolation_chat_sessions (id) on delete cascade,
    role        text not null check (role in ('assistant', 'astronaut')),
    content     text not null check (char_length(content) between 1 and 8000),
    created_at  timestamptz not null default now()
);
create index if not exists isolation_chat_messages_session_idx
    on public.isolation_chat_messages (session_id, created_at);

create table if not exists public.loneliness_assessments (
    id                              uuid primary key default gen_random_uuid(),
    session_id                      uuid not null unique references public.isolation_chat_sessions (id) on delete cascade,
    astronaut_id                    text not null references public.astronauts (id) on delete cascade,
    mission_day                     integer not null check (mission_day >= 1),
    q1                              smallint not null check (q1 between 1 and 3),  -- lack companionship
    q2                              smallint not null check (q2 between 1 and 3),  -- left out
    q3                              smallint not null check (q3 between 1 and 3),  -- isolated
    score                           smallint not null check (score between 3 and 9),
    confidence                      double precision not null check (confidence between 0 and 1),
    reliable                        boolean not null,
    safety_concern                  boolean not null default false,
    level                           text not null check (level in ('green', 'amber', 'red')),
    consecutive_days_at_or_above_7  integer not null default 0,
    rationale                       text not null default '',
    evidence                        jsonb not null default '[]'::jsonb,
    alert                           jsonb not null,
    model                           text not null,
    created_at                      timestamptz not null default now()
);
create index if not exists loneliness_assessments_astronaut_day_idx
    on public.loneliness_assessments (astronaut_id, mission_day, created_at);

-- ---------------------------------------------------------------------------
-- Gravity: Mobility & Balance Check (numbers measured in the browser; no video is stored)
-- ---------------------------------------------------------------------------
create table if not exists public.mobility_checks (
    id                 uuid primary key default gen_random_uuid(),
    astronaut_id       text not null references public.astronauts (id) on delete cascade,
    mission_day        integer not null check (mission_day >= 1),
    balance_hold_s     double precision not null check (balance_hold_s between 0 and 30),
    sway_pct_height    double precision not null check (sway_pct_height between 0 and 50),
    sit_to_stand_5x_s  double precision not null check (sit_to_stand_5x_s > 1),
    knee_flexion_deg   double precision not null check (knee_flexion_deg between 0 and 150),
    pose_confidence    double precision not null check (pose_confidence between 0 and 1),
    reliable           boolean not null,
    created_at         timestamptz not null default now()
);
create index if not exists mobility_checks_astronaut_idx
    on public.mobility_checks (astronaut_id, created_at);

-- ---------------------------------------------------------------------------
-- Last-good copies of external feeds (NASA DONKI, JPL Horizons), survive restarts
-- ---------------------------------------------------------------------------
create table if not exists public.external_data_cache (
    key         text primary key,           -- e.g. 'donki:2024-05-08:2024-05-12', 'horizons:mars:...'
    payload     jsonb not null,
    fetched_at  timestamptz not null,
    updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Row Level Security: off (also undoes an earlier run of this script that enabled it)
-- ---------------------------------------------------------------------------
alter table public.astronauts               disable row level security;
alter table public.daily_records            disable row level security;
alter table public.mission_settings         disable row level security;
alter table public.isolation_chat_sessions  disable row level security;
alter table public.isolation_chat_messages  disable row level security;
alter table public.loneliness_assessments   disable row level security;
alter table public.mobility_checks          disable row level security;
alter table public.external_data_cache      disable row level security;


-- =============================================================================
-- Nova Healix API v2 tables (check-ins, questionnaires, Nova safety flags, notes, mission control,
-- mobility). They sit beside the RIDGE tables above; nothing is dropped.
-- Nova chat is never stored: there is deliberately no chat table in this section.
-- =============================================================================
-- ---------------------------------------------------------------------------
-- Mission clock: single row. Keeps stored mission hours aligned across restarts.
-- ---------------------------------------------------------------------------
create table if not exists public.mission (
    id               smallint primary key default 1 check (id = 1),
    launch_epoch_ms  bigint not null,
    updated_at       timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Crew Mode: daily check-ins (one per astronaut per day) and questionnaire assignments
-- ---------------------------------------------------------------------------
create table if not exists public.checkins (
    id             text primary key,                 -- ci-<crewId>-<day>
    crew_id        text not null,
    day            integer not null check (day >= 1),
    "at"           double precision not null,        -- mission hour submitted
    mood           smallint not null check (mood between 1 and 5),
    sleep_quality  smallint not null check (sleep_quality between 1 and 5),
    energy         smallint not null check (energy between 1 and 5),
    symptoms       text[] not null default '{}',
    note           text,
    unique (crew_id, day)
);

create table if not exists public.assignments (
    id                text primary key,
    crew_id           text not null,
    questionnaire_id  text not null check (questionnaire_id in ('wellbeing', 'sleep', 'workload', 'team')),
    assigned_by       text not null,
    note              text,
    assigned_at       double precision not null,
    due_day           integer not null,
    status            text not null check (status in ('assigned', 'in-progress', 'done')),
    answers           jsonb not null default '{}'::jsonb,
    current_index     integer not null default 0,
    completed_at      double precision,
    score             smallint check (score between 0 and 100)
);
create index if not exists assignments_crew_idx on public.assignments (crew_id);

-- Measurements added at runtime (a submitted stress / workload questionnaire becomes a sample).
create table if not exists public.samples (
    id       bigint generated always as identity primary key,
    crew_id  text not null,
    metric   text not null,
    t        double precision not null,
    v        double precision not null
);
create index if not exists samples_crew_metric_t_idx on public.samples (crew_id, metric, t);

-- Mobility & Balance Check (numbers measured in the browser with MediaPipe; no video is stored)
create table if not exists public.mobility_sessions (
    id                 text primary key,
    crew_id            text not null,
    day                integer not null check (day >= 1),
    "at"               double precision not null,
    balance_hold_s     double precision not null check (balance_hold_s between 0 and 30),
    sway_pct_height    double precision not null check (sway_pct_height between 0 and 50),
    sit_to_stand_s  double precision not null check (sit_to_stand_s > 1),
    knee_flexion_deg   double precision not null check (knee_flexion_deg between 0 and 150),
    pose_confidence    double precision not null check (pose_confidence between 0 and 1),
    reliable           boolean not null
);
create index if not exists mobility_sessions_crew_idx on public.mobility_sessions (crew_id, "at");

-- ---------------------------------------------------------------------------
-- Nova safety exception: a flag carries a category and a signal, NEVER any chat text
-- ---------------------------------------------------------------------------
create table if not exists public.safety_flags (
    id        text primary key,
    crew_id   text not null,
    "at"      double precision not null,
    category  text not null check (category in ('self-harm', 'medical')),
    signal    text not null
);

-- Notes the astronaut chose to share with the flight surgeon (after confirming a share card)
create table if not exists public.shared_notes (
    id       text primary key,
    crew_id  text not null,
    "at"     double precision not null,
    text     text not null check (char_length(text) between 1 and 2000)
);

-- ---------------------------------------------------------------------------
-- Mission Control: action log, crew messages (with signal delay), resolutions
-- ---------------------------------------------------------------------------
create table if not exists public.action_log (
    id          text primary key,
    insight_id  text not null,
    crew_id     text,
    "at"        double precision not null,
    "by"        text not null,
    kind        text not null,
    label       text not null,
    detail      text
);
create index if not exists action_log_insight_idx on public.action_log (insight_id);

create table if not exists public.crew_messages (
    id          text primary key,
    crew_id     text not null,
    "from"      text not null,
    text        text not null check (char_length(text) between 1 and 2000),
    sent_at     double precision not null,
    deliver_at  double precision not null,
    insight_id  text
);
create index if not exists crew_messages_crew_idx on public.crew_messages (crew_id, sent_at);

create table if not exists public.resolutions (
    insight_id  text primary key,
    "at"        double precision not null,
    "by"        text not null,
    note        text not null,
    severity    text not null check (severity in ('alert', 'watch', 'info'))
);

-- ---------------------------------------------------------------------------
-- Last-good copies of external feeds (NASA DONKI, JPL Horizons), survive restarts
-- ---------------------------------------------------------------------------
create table if not exists public.external_data_cache (
    key         text primary key,           -- e.g. 'donki:2024-05-08:2024-05-12', 'horizons:mars-arrival:2027-07-15'
    payload     jsonb not null,
    fetched_at  timestamptz not null,
    updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Row Level Security: off
-- ---------------------------------------------------------------------------
alter table public.mission              disable row level security;
alter table public.checkins             disable row level security;
alter table public.assignments          disable row level security;
alter table public.samples              disable row level security;
alter table public.mobility_sessions      disable row level security;
alter table public.safety_flags         disable row level security;
alter table public.shared_notes         disable row level security;
alter table public.action_log           disable row level security;
alter table public.crew_messages        disable row level security;
alter table public.resolutions          disable row level security;
alter table public.external_data_cache  disable row level security;
