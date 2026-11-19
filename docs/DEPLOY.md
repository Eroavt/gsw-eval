# Deploy

## The website: GitHub Pages

This is all the project needs. No account, no database, no cost.

1. Merge the code into `main` and make the repository public.
2. Under "Settings", "Pages", set "Source" to "GitHub Actions".
3. `.github/workflows/pages.yml` publishes `site/` on every push to `main`.

The address is `https://eroavt.github.io/gsw-eval/`.

## The server for the phone page: Vercel

The phone page sends answers to `/api/submit`, which stores them in Postgres. The export
`/api/submissions?key=...` returns the latest answers per person and who is done. It needs:

| Variable | What |
|---|---|
| `DATABASE_URL` | Set by the Neon integration |
| `EXPORT_KEY` | A long random key; only with it can anyone read the answers |
| `SUBMIT_ORIGINS` | Optional, more sites allowed to post besides `https://eroavt.github.io` |

Then `gsw-eval participation-page --submit-url https://YOUR-PROJECT.vercel.app/api/submit` points the
page at the server.
