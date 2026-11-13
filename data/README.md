# data/

Nothing here is committed (see `.gitignore`).

- `data/swissdial/` SwissDial v1.1 from ETH Zurich (CC BY-NC 4.0: credit the authors, no
  commercial use). Request it from ETH, or take `swissdial.zip` from the team's Drive folder
  and unzip it here, so that `data/swissdial/data1.1/sentences_ch_de_transcribed.json` and
  `sentences_ch_de_numerics.json` exist. Needed by `scripts/reproduce.sh`.
- `data/ntrex/` Swiss German NTREX. `scripts/reproduce.sh` downloads it (`scripts/get_ntrex.sh`).
- `data/ratings/` the rating sheet and the key that maps items to models. The key stays private
  until the ratings are in, then moves to `ratings/`.
- `data/submissions/` answers that helpers sent by WhatsApp (personal, never shared).

The fresh set is not here: it lives in `fresh/` and is committed once data collection ends.
The results website needs none of this: `python3 -m http.server 8123 --directory site`.
