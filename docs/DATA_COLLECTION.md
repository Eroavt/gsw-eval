# Data collection

Up to eight native speakers give two kinds of data on one phone page, `site/mitmachen.html?p=N`
(N = 1 to 8, one link per person; links 6 to 8 were added later). It takes about 35 minutes. One tap on «Absenden» stores the
answers on our server (`/api/submit`, Vercel and Postgres). How nothing gets lost:

- The phone keeps every answer, and copies all of them to the server a few seconds after each change
  and whenever the page is left.
- Opening the link on another phone or browser restores the saved answers (`/api/progress`).
- The server keeps every copy. Per person the most complete copy counts, so an older or emptier one
  never replaces a fuller one.
- If the server cannot be reached at the end, the page says so and offers WhatsApp as a backup.

Progress for the organiser: `status.html#key=EXPORT_KEY` shows how far each link is.

## What each person does

| Part | Task | Why it is designed this way |
|---|---|---|
| About you | Canton of their dialect, how often they text in Swiss German, consent | No names; the canton is the dialect label |
| 1. Chat | Type 24 Standard German sentences as they would text a friend | Chat comes first, so it stays natural |
| 2. Careful | The same sentences again, carefully, in their dialect | A separate round, so neither version copies the other. Nothing is pre-filled, because accepting a pre-filled text would make both versions identical and hide the spelling effect |
| 3. Rate | About 45 model translations on a 1 to 5 scale; for 3 or lower, one tap on what went wrong | No reference is shown, so people judge meaning, not word overlap. "Verstehe den Satz nicht" skips dialects they cannot follow |

Each of the 112 rating items goes to two of persons 1 to 5 (`participation.assign_raters`), so each
of them rates the same share and all five rater pairs overlap. Persons 6, 7 and 8 rate exactly the
items of persons 1, 2 and 3, so agreement can be measured as soon as either of two such people has
finished. Agreement is Krippendorff's alpha,
which allows different rater pairs and skipped items.

The 112 items are all four models on 24 test inputs (16 careful, 8 chat style) plus 16 model
rewrites of Standard German input, which show how much of the gap to a perfect score is harmless
paraphrase. The key that maps items to models stays in `data/ratings/` (not in git) until the
ratings are in.

## Run it

```bash
gsw-eval participation-page    # writes site/data/mitmachen.json
```

Send each person their own link. To test a link on your own phone and start it again afterwards,
open it with `&reset=1` at the end. Answers live on each phone, so testing never affects the
helpers. Save the forwarded messages in one or more text files, then:

```bash
gsw-eval collect --server        # reads SUBMISSIONS_URL with EXPORT_KEY from .env
gsw-eval collect messages.txt  # or WhatsApp messages; both together also work
gsw-eval run --model claude-sonnet-5.5 --split fresh
gsw-eval ratings
```

`collect` reports who is complete and who is missing. A message that was cut or changed fails its
checksum and is refused, naming the person where possible, so nothing is lost silently. A later
message from the same person replaces the earlier one.

Phones cut shared text at about 4,096 characters. The page therefore sends the answers compactly and
gzipped (format `GSW2`, about 1,500 characters for a full set) and splits them into numbered parts
if they are still too long. The first format, `GSW1`, still imports. A person whose message arrived
cut only needs to open their link again and tap send: the answers stay on their phone.
