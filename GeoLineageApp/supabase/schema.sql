-- GeoLineage cloud schema (Supabase Free)
-- Run in Supabase SQL Editor.
-- Public SELECT on runs/receipts for demo History; all writes via Worker service_role.
-- keepalive / app_control: no anon policies (Worker-only).

create extension if not exists "pgcrypto";

create table if not exists public.runs (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  catalog_url text not null,
  collection text not null,
  bbox double precision[] not null,
  max_items int not null default 10,
  input_count int not null default 0,
  output_path text,
  output_checksum text,
  reused_from_run_id uuid references public.runs (id),
  status text not null default 'complete'
    check (status in ('complete', 'reused', 'failed')),
  search_params jsonb not null default '{}'::jsonb
);

create table if not exists public.lineage_receipts (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.runs (id) on delete cascade,
  created_at timestamptz not null default now(),
  receipt jsonb not null
);

create index if not exists runs_created_at_idx on public.runs (created_at desc);
create index if not exists lineage_receipts_run_id_idx on public.lineage_receipts (run_id);

alter table public.runs enable row level security;
alter table public.lineage_receipts enable row level security;

drop policy if exists "runs_public_all" on public.runs;
drop policy if exists "runs_public_select" on public.runs;
create policy "runs_public_select" on public.runs
  for select using (true);

drop policy if exists "receipts_public_all" on public.lineage_receipts;
drop policy if exists "receipts_public_select" on public.lineage_receipts;
create policy "receipts_public_select" on public.lineage_receipts
  for select using (true);

-- Storage bucket: create "outputs" in Dashboard → Storage (public read for demo).
-- Or via SQL (requires storage schema privileges):
insert into storage.buckets (id, name, public)
values ('outputs', 'outputs', true)
on conflict (id) do nothing;

drop policy if exists "outputs_public_read" on storage.objects;
create policy "outputs_public_read" on storage.objects
  for select using (bucket_id = 'outputs');

-- Uploads go through the Worker with the service_role key (bypasses RLS).
-- Do not allow anon/public inserts into the outputs bucket.
drop policy if exists "outputs_public_insert" on storage.objects;

-- Keepalive pings (stop Supabase free pause) + soft free-tier kill switch
create table if not exists public.keepalive (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  marker int not null default 1
);

create index if not exists keepalive_created_at_idx on public.keepalive (created_at desc);

create table if not exists public.app_control (
  id int primary key default 1 check (id = 1),
  status text not null default 'open'
    check (status in ('open', 'closed')),
  reason text,
  requests_today int not null default 0,
  requests_day date not null default (timezone('utc', now()))::date,
  updated_at timestamptz not null default now()
);

insert into public.app_control (id, status, reason, requests_today, requests_day)
values (1, 'open', null, 0, (timezone('utc', now()))::date)
on conflict (id) do nothing;

alter table public.keepalive enable row level security;
alter table public.app_control enable row level security;

-- No anon policies on control tables — service_role (Worker) bypasses RLS.
drop policy if exists "keepalive_public_all" on public.keepalive;
drop policy if exists "app_control_public_all" on public.app_control;

create or replace function public.app_control_bump_request()
returns public.app_control
language plpgsql
security definer
set search_path = public
as $$
declare
  today date := (timezone('utc', now()))::date;
  row public.app_control;
begin
  insert into public.app_control (id, status, reason, requests_today, requests_day)
  values (1, 'open', null, 0, today)
  on conflict (id) do nothing;

  update public.app_control
  set
    requests_today = case
      when requests_day is distinct from today then 1
      else requests_today + 1
    end,
    requests_day = today,
    updated_at = timezone('utc', now())
  where id = 1
  returning * into row;

  return row;
end;
$$;

revoke all on function public.app_control_bump_request() from public;
revoke all on function public.app_control_bump_request() from anon, authenticated;
grant execute on function public.app_control_bump_request() to service_role;
