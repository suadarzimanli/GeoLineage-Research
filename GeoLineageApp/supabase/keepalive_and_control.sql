-- Keep Supabase free projects from pausing + soft free-tier kill switch.
-- Run once in SQL Editor (or: npx supabase db query --linked -f supabase/keepalive_and_control.sql)

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

-- No anon policies — Worker service_role bypasses RLS.
-- If an older deploy created open policies, also run harden_control_rls.sql.
drop policy if exists "keepalive_public_all" on public.keepalive;
drop policy if exists "app_control_public_all" on public.app_control;
