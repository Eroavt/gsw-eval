# data/

Nothing here is committed (see `.gitignore`).

- `data/swissdial/` SwissDial v1.1 from ETH Zurich (CC BY-NC 4.0: credit the authors, no
  commercial use). Request it from ETH and unzip it here, so that `data/swissdial/data1.1/sentences_ch_de_transcribed.json` and
  `sentences_ch_de_numerics.json` exist. Needed by `scripts/reproduce.sh`.
- `data/ntrex/` Swiss German NTREX. `scripts/reproduce.sh` downloads it (`scripts/get_ntrex.sh`).
- `data/ratings/` where `gsw-eval rating-sheet` writes a new blind rating sheet and its key. The
  sheet and key used in the report are committed in `ratings/`.
- `data/submissions/` raw answers sent outside the phone page (personal, never shared).

The fresh set is not here: it is committed in `fresh/` (see `docs/DATA_COLLECTION.md`).
The results website needs none of this: `python3 -m http.server 8123 --directory site`.
