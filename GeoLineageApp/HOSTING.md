# Hosting — Cloudflare Pages + Worker + Supabase (Free)

This cloud rebuild replaces Streamlit + local folders with a hostable demo.

## Architecture

| Piece | Role | Free plan notes |
|-------|------|-----------------|
| **Cloudflare Pages** | Static UI (`web/`) | Free |
| **Cloudflare Worker** | Thin API: STAC proxy, runs, receipts | Free: ~10 ms CPU/request; network wait does **not** count. Keep Worker thin. |
| **Supabase** | Postgres + Storage for runs / GeoJSON | Free: 500 MB DB, 1 GB Storage, pauses after ~1 week of low activity |

## One-time setup

### 1. Supabase

1. Create a Free project at [supabase.com](https://supabase.com).
2. SQL Editor → paste and run [`supabase/schema.sql`](supabase/schema.sql).
3. Storage → confirm bucket **`outputs`** exists and is **public** (schema tries to create it).
4. Project Settings → API: copy **Project URL** and **service_role** key (server only).

**Security:** `runs` / `lineage_receipts` are **public SELECT only**; inserts and deletes go through the Worker `service_role`. `keepalive` and `app_control` have **no anon policies** (Worker-only). Do not expose `service_role` in the browser. The Worker allowlists the default STAC catalog, validates bboxes, and only fetches footprints from your public `outputs` bucket.

If the project was created before hardening, also run [`supabase/harden_control_rls.sql`](supabase/harden_control_rls.sql) (drops open write policies, adds `app_control_bump_request`).

If you already applied an older schema that created `outputs_public_insert`, remove it:

```sql
drop policy if exists "outputs_public_insert" on storage.objects;
```

**Rotate keys** if `.dev.vars` or a `service_role` JWT may have left your machine (shared zip, chat upload, etc.): Supabase Dashboard → Project Settings → API → reset `service_role`, then update Wrangler secrets / local `.dev.vars`.

### 2. Cloudflare Worker

```bash
cd worker
npm install
npx wrangler login
npx wrangler secret put SUPABASE_URL
# paste https://xxxx.supabase.co
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
# paste service_role key
npx wrangler secret put ADMIN_USERNAME
npx wrangler secret put ADMIN_PASSWORD
npx wrangler secret put ADMIN_SESSION_SECRET
npx wrangler deploy
```

Admin UI: nav link **Admin** → `/admin`. Login is checked on the Worker; the password must never go in the frontend bundle—only in Worker secrets / `worker/.dev.vars`.

For production, lock browser CORS to your Pages origin (and local UI if needed) in [`worker/wrangler.toml`](worker/wrangler.toml):

```toml
[vars]
DEFAULT_CATALOG_URL = "https://earth-search.aws.element84.com/v1"
DEFAULT_COLLECTION = "sentinel-2-c1-l2a"
ALLOWED_ORIGINS = "https://YOUR_PAGES_HOST,http://127.0.0.1:5173"
```

Leave `ALLOWED_ORIGINS` unset for permissive local `wrangler dev`.

Note the Worker URL, e.g. `https://geolineage-api.<account>.workers.dev`.

### 3. Web UI (Pages)

```bash
cd web
cp .env.example .env
# VITE_API_BASE=https://geolineage-api.<account>.workers.dev
npm install
npm run build
```

Deploy `web/dist` to Cloudflare Pages (Dashboard upload, or Wrangler):

```bash
npx wrangler pages deploy dist --project-name geolineage
```

Set production env var **`VITE_API_BASE`** in Pages build settings to the Worker URL, then rebuild.

SPA routing: add a Pages `_redirects` or “Single-page application” fallback so `/runs/:id` loads `index.html` (see `web/public/_redirects`).

## Local development

Terminal A:

```bash
cd worker && npx wrangler dev --ip 127.0.0.1 --port 8787
# http://127.0.0.1:8787
```

Put secrets in `worker/.dev.vars` (not committed):

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
```

Terminal B:

```bash
cd web
echo VITE_API_BASE=http://127.0.0.1:8787 > .env
npm run dev
```

## Free-tier reality

- **Supabase pause (keepalive):** after `npx wrangler deploy`, a Worker cron (`0 12 * * *` UTC) writes `marker = 1` into `public.keepalive` when the last DB write (run or keepalive) is older than **72 hours**. Cron does not run in local `wrangler dev` unless you trigger scheduled. Apply [`supabase/keepalive_and_control.sql`](supabase/keepalive_and_control.sql) then [`supabase/harden_control_rls.sql`](supabase/harden_control_rls.sql) on older projects. Admin → **Ping keepalive** forces a write.
- **Soft auto-close:** `app_control` (Worker-only) tracks open/closed. New `/search` and `/runs` stop when stored runs hit `MAX_RUNS` (default 400) or the atomic daily request counter hits `MAX_REQUESTS_PER_DAY` (default 80 000). Caps are in [`worker/wrangler.toml`](worker/wrangler.toml) `[vars]`. Admin can **Close** / **Reopen**; a UTC-day reset can auto-reopen after a request-cap close. Public `/health` only reports open/closed; full counters are on Admin.
- **Storage / DB caps:** keep max_items small; GeoJSON footprints stay modest. Delete old runs in Admin before reopening after a run-cap close.
- **Workers Free CPU:** if you hit Error 1102, slim the handler or move to Workers Paid (~$5/mo).
- **Not for heavy GeoPandas/Parquet on the edge** — this design uses GeoJSON in Storage on purpose.

## What stayed the same (product idea)

Search catalog → footprints product → lineage receipt → diff / reuse when inputs match — now with cloud save and a clearer UI.
