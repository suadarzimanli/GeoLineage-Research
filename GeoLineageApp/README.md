# GeoLineage

Portfolio demo: pick a place, search a public satellite catalog (Earth Search / STAC), save scene footprints and a lineage receipt in the cloud.

| Piece | Role |
|-------|------|
| **web/** | Vite + React UI (Cloudflare Pages) |
| **worker/** | Cloudflare Worker API (STAC proxy, runs, receipts, diff/reuse) |
| **supabase/** | Postgres schema + storage notes |

See **[HOSTING.md](HOSTING.md)** for free-tier setup and limits.

## Quick local try

1. Apply [`supabase/schema.sql`](supabase/schema.sql) in a Supabase project.
2. Copy `worker/.dev.vars.example` → `worker/.dev.vars` and set `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.
3. `cd worker && npm install && npx wrangler dev --ip 127.0.0.1 --port 8787`
4. Copy `web/.env.example` → `web/.env` with `VITE_API_BASE=http://127.0.0.1:8787`
5. `cd web && npm install && npm run dev`

## Layout

```
.
  web/                 # SPA
  worker/              # API
  supabase/schema.sql
  HOSTING.md
```

Secrets (`.dev.vars`, `web/.env`) are gitignored and not shipped in this folder—create them locally.
