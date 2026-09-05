# Running Kivi

Exact steps to get the system running, seeded, exercised, evaluated, and reset.

## 1. Required runtimes

- Docker Engine and Docker Compose v2 (the `docker compose` subcommand, not the standalone `docker-compose` binary)
- Nothing else needs to be installed on the host — Python 3.11, `uv`, and all dependencies run inside the app container.

## 2. Environment variables

Copy the example file and fill in the one real secret:

```bash
cp .env.example .env
```

| Variable | Meaning |
|---|---|
| `DB_URL` | Async SQLAlchemy connection string. Default (`postgresql+asyncpg://postgres:postgres@db:5432/kivi`) points at the `db` service in `docker-compose.yml` — leave as-is unless you change the compose file. |
| `GEMINI_API_KEY` | Google Gemini API key, used only for the upstream ASR → formatted-text cleanup step. Kivi's own memory/retrieval/abstention logic never calls it, so a placeholder value is fine for exercising this repo's endpoints directly. |
| `USER_ID` | UUID used as the single demo user across every endpoint (no auth layer). Default `00000000-0000-0000-0000-000000000000` matches the seed script. |

`.env` is git-ignored — never commit it.

## 3. Install dependencies / build the image

```bash
docker compose build
```

## 4. Start the system

```bash
docker compose up -d
```

Wait for the `db` service to report healthy (compose's healthcheck handles this automatically — `app` won't start until `db` is ready). Then apply migrations:

```bash
docker compose exec app uv run alembic upgrade head
```

Confirm it's up:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## 5. Seed the database

```bash
docker compose exec app uv run python seed/seed.py
```

This creates the default user and two example memories (`Aaditya`/`Aditya`, `Kivi`/`Kiwi`). It's idempotent — running it again skips entries that already exist rather than duplicating them.

## 6. Open the interface

```
http://localhost:8000/
```

## 7. Primary interactions to try

- **Add a term** — fill in canonical form, category, and comma-separated bad variants, click "Add term". It appears in the memory table below.
- **Process a transcript** — paste an ASR output and a formatted output containing one of the seeded bad variants (e.g. formatted output `Ask Aditya to review the pull request.`). Click "Process" to see the memory-aware output and the full per-token decision log (APPLY / ABSTAIN / PASS with a reason each).
- **Submit a correction** — paste an original formatted transcript and your corrected version of it (e.g. original `Ask Adithya to join the call.`, corrected `Ask Aaditya to join the call.`). Click "Submit correction" to see what memory was created or updated, then re-run "Process" on a sentence with that bad form to see it now applies.
- **Suppress / reactivate / delete** — use the per-row buttons in the memory table, then re-run "Process" to see the resulting behaviour change.
- **Reset** — clears all memory for the user (confirms before executing).

## 8. Run the evaluation

```bash
docker compose exec app uv run python evaluation/run_eval.py
```

This drives every case in `evaluation/cases.json` against the running API, prints a summary (pass/fail count, precision, recall, abstention correctness), and exits non-zero if any case fails. It resets memory before each case and again when it finishes, so it's safe to run repeatedly.

## 9. Where results are written

`evaluation/results.json` — per-case input, expected output, actual output, decision log, and pass/fail, plus a `summary` block with the aggregate metrics.

## 10. Resetting the system

- **Clear memory only** (keeps schema and containers running): click "Reset all memory" in the UI, or:
  ```bash
  curl -X POST http://localhost:8000/memory/reset
  ```
- **Full reset from scratch (wipe the database)**: `docker compose down -v` (the `-v` removes the named `postgres_data` volume) then repeat from step 4. A plain `docker compose down` (without `-v`) stops the containers but keeps the database intact for next time.
