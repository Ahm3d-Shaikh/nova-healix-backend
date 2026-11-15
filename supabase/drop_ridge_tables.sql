-- Run ONCE, after deploying API v2, to remove the old RIDGE tables.
-- This permanently deletes: stored ECHO chat transcripts, loneliness scores, mobility checks,
-- the simulated daily records and the old mission settings. Nova v2 stores none of these.
-- Back up anything you want to keep first. Safe to re-run.

drop table if exists public.isolation_chat_messages cascade;
drop table if exists public.isolation_chat_sessions cascade;
drop table if exists public.loneliness_assessments cascade;
drop table if exists public.mobility_checks cascade;
drop table if exists public.daily_records cascade;
drop table if exists public.mission_settings cascade;
drop table if exists public.astronauts cascade;
