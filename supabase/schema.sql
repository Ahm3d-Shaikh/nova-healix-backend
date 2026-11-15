-- Nova Healix - Supabase schema (API v2).
-- Run once in the Supabase SQL editor (Dashboard -> SQL Editor -> New query -> paste -> Run).
-- Safe to re-run: every statement is idempotent.
--
-- The simulated crew (vitals, sleep, dose, ...) is generated in-process from a fixed seed, so it is NOT
-- stored. These tables hold only what the app writes at runtime. There is deliberately NO table for
-- Nova chat: conversations are never stored.
--
-- Row Level Security is OFF on every table. The backend uses the service-role key.
-- WARNING: with RLS off, anyone holding this project's anon key can read and write these tables
-- through the Data API. Never put the anon key in a public frontend while RLS is off.
--
-- Coming from the old RIDGE API? Run supabase/drop_ridge_tables.sql once (it deletes the old chat
-- transcripts and loneliness scores).

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
