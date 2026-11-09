#!/usr/bin/env bash
# Download Swiss German NTREX (Aepli et al., 2023) and the NTREX-128 German and English files.
# The data is not redistributed in this repository; it lands in data/ntrex/ (git-ignored).
#   Swiss German (Bern, Zurich): https://github.com/textshuttle/dialect_eval
#   Standard German, English:    https://github.com/MicrosoftTranslator/NTREX (CC BY-SA 4.0)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=data/ntrex
mkdir -p "$OUT"

curl -sfL -o "$OUT/references_be_zh.zip" \
  https://raw.githubusercontent.com/textshuttle/dialect_eval/main/evaluation/ntrex-128/raw/references_be_zh.zip
unzip -q -o "$OUT/references_be_zh.zip" -d "$OUT" -x "__MACOSX/*" "*.DS_Store"
rm "$OUT/references_be_zh.zip"

NTREX=https://raw.githubusercontent.com/MicrosoftTranslator/NTREX/main/NTREX-128
curl -sfL -o "$OUT/newstest2019-ref.deu.txt" "$NTREX/newstest2019-ref.deu.txt"
curl -sfL -o "$OUT/newstest2019-src.eng.txt" "$NTREX/newstest2019-src.eng.txt"

echo "NTREX ready in $OUT"
