# Deploy the website and the arena

The site and the arena run on Vercel with a Postgres database from Neon. Both have free plans for
non-commercial use. Check the current limits on their pages first.

## 1. Create the project

1. Log in to [vercel.com](https://vercel.com) with your own GitHub account.
2. "Add New", "Project", and import `Eroavt/gsw-eval`. A private repository works.
3. Pick the branch to deploy under "Settings", "Environments" (or merge to `main` first).
4. Keep the defaults: `vercel.json` sets everything. Root directory stays the repository root.

## 2. Add the database

1. In the project, open "Storage" and add **Neon** from the Marketplace.
2. Connect it to the project. This sets `DATABASE_URL`. If the variable has another name, such as
   `POSTGRES_URL`, add `DATABASE_URL` with the same value.

The tables are created on the first vote.

## 3. Set the secret

Create a secret, then add it under "Settings", "Environment Variables" as `ARENA_SECRET`:

```bash
openssl rand -hex 32
```

Without `DATABASE_URL` and `ARENA_SECRET` the site works and the arena says that voting is closed.
Changing the secret later invalidates only duels that are currently open.

## 4. Optional: live mode

Live mode needs at least two models. Each key below switches models on.

| Variable | Models |
|---|---|
| `ANTHROPIC_API_KEY` | Claude Sonnet 5.5 |
| `OPENROUTER_API_KEY` | Llama 3.1 8B, Gemma 3 27B |
| `PUBLICAI_API_KEY` | Apertus 8B |
| `LIVE_DAILY_CALLS` | Maximum model calls per day, default 300 |

`PUBLICAI_BASE_URL` and `OPENROUTER_BASE_URL` override the default endpoints. Set a spending limit
with each provider as well.

## 5. Check it

```bash
curl https://YOUR-URL/api/status
```

This should return `{"open":true,"live":false}`, or `"live":true` with two models. Then vote once on
`/arena.html` and check that it appears in `/api/export`.

## 6. Get the votes

```bash
curl -o votes.csv https://YOUR-URL/api/export
gsw-eval arena votes.csv
gsw-eval arena votes.csv --native-only
```

## Without Vercel

GitHub Pages also serves `site/`, without the arena, through `.github/workflows/pages.yml`. It needs a
public repository and "Settings", "Pages", "Source: GitHub Actions".
