-- OPTIONAL, run once, only if this Supabase project was set up with the earlier RIDGE schema.
-- The backend no longer uses these tables (their jobs moved into the tables of supabase/schema.sql).
-- This permanently deletes the old simulated crew rows, mission settings, old chat transcripts, old loneliness
-- scores and old mobility checks. Back up anything you want to keep first. Safe to re-run.

drop table if exists public.isolation_chat_messages cascade;
drop table if exists public.isolation_chat_sessions cascade;
drop table if exists public.loneliness_assessments cascade;
drop table if exists public.mobility_checks cascade;
drop table if exists public.daily_records cascade;
drop table if exists public.mission_settings cascade;
drop table if exists public.astronauts cascade;
