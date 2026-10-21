-- Run once in Supabase → SQL Editor → New query.
-- Publishable keys may access tables ONLY with a signed-in user's JWT.
create table if not exists public.predictions (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 match_id text not null, league text not null, match text not null,
 kickoff_utc timestamptz not null, market text not null,
 probability double precision not null check (probability between 0 and 1),
 odds double precision check (odds > 1), bookmaker text,
 recorded_at_utc timestamptz not null default now(),
 result text not null default 'Pending' check (result in ('Pending','Won','Lost')),
 unique(user_id,match_id,market)
);
create table if not exists public.saved_parlays (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 title text not null, legs jsonb not null, created_at timestamptz not null default now()
);
create table if not exists public.watchlist (
 id uuid primary key default gen_random_uuid(),
 user_id uuid not null references auth.users(id) on delete cascade,
 match_id text not null, match text not null, kickoff_utc timestamptz,
 created_at timestamptz not null default now(), unique(user_id,match_id)
);
-- Explicitly enable row-level security on every table.
alter table public.predictions enable row level security;
alter table public.saved_parlays enable row level security;
alter table public.watchlist enable row level security;
-- Restrict privileges as well as RLS.
revoke all on public.predictions,public.saved_parlays,public.watchlist from anon;
grant select,insert,update,delete on public.predictions,public.saved_parlays,public.watchlist to authenticated;

do $$ declare t text; begin
 foreach t in array array['predictions','saved_parlays','watchlist'] loop
  execute format('drop policy if exists own_select on public.%I',t);
  execute format('drop policy if exists own_insert on public.%I',t);
  execute format('drop policy if exists own_update on public.%I',t);
  execute format('drop policy if exists own_delete on public.%I',t);
  execute format('create policy own_select on public.%I for select to authenticated using (user_id = (select auth.uid()))',t);
  execute format('create policy own_insert on public.%I for insert to authenticated with check (user_id = (select auth.uid()))',t);
  execute format('create policy own_update on public.%I for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()))',t);
  execute format('create policy own_delete on public.%I for delete to authenticated using (user_id = (select auth.uid()))',t);
 end loop; end $$;
-- This database does not use a server secret key.
