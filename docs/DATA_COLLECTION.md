# Data collection

Five native speakers give two kinds of data on one phone page, `site/mitmachen.html?p=N`
(N = 1 to 5, one link per person). It takes about 35 minutes. Nothing is stored on a server:
the answers stay on the phone until the person sends them as one WhatsApp message.

## What each person does

| Part | Task | Why it is designed this way |
|---|---|---|
| About you | Canton of their dialect, how often they text in Swiss German, consent | No names; the canton is the dialect label |
| 1. Chat | Type 24 Standard German sentences as they would text a friend | Chat comes first, so it stays natural |
| 2. Careful | The same sentences again, carefully, in their dialect | A separate round, so neither version copies the other. Nothing is pre-filled, because accepting a pre-filled text would make both versions identical and hide the spelling effect |
| 3. Rate | About 45 model translations on a 1 to 5 scale; for 3 or lower, one tap on what went wrong | No reference is shown, so people judge meaning, not word overlap. "Verstehe den Satz nicht" skips dialects they cannot follow |

Each of the 112 rating items goes to two different people (`participation.assign_raters`), so every
person rates the same share and all five rater pairs overlap. Agreement is Krippendorff's alpha,
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
gsw-eval collect messages.txt  # fresh/data/fresh_v1.csv, ratings/ratings_v2.csv, participants
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
