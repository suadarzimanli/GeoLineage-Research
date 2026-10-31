-- Harden free-tier controls: Worker (service_role) only for writes/control.
-- Run once on existing projects after keepalive_and_control.sql.

-- Control tables: drop public open policies (no anon policies → Worker-only via service_role)
drop policy if exists "keepalive_public_all" on public.keepalive;
drop policy if exists "app_control_public_all" on public.app_control;

-- Demo data: public read only; inserts/updates/deletes go through the Worker
drop policy if exists "runs_public_all" on public.runs;
drop policy if exists "runs_public_select" on public.runs;
create policy "runs_public_select" on public.runs
  for select using (true);

drop policy if exists "receipts_public_all" on public.lineage_receipts;
drop policy if exists "receipts_public_select" on public.lineage_receipts;
create policy "receipts_public_select" on public.lineage_receipts
  for select using (true);

-- Atomic daily request bump (service_role only)
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
