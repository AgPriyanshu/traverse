#!/usr/bin/env bash
# Load the public-domain demo corpus.
#
# Sprint 1 only fetches the texts and parks them where the ingestion pipeline
# will pick them up; uploading through the API starts in Sprint 2, and this
# script grows an upload step then.
set -euo pipefail

cd "$(dirname "$0")/.."
CORPUS_DIR="${CORPUS_DIR:-data/corpus}"
mkdir -p "$CORPUS_DIR"

# Project Gutenberg, public domain. Keyed by the demo they support.
declare -A CORPUS=(
  ["pride-and-prejudice"]="https://www.gutenberg.org/ebooks/1342.epub.noimages"
  ["anne-of-green-gables-1"]="https://www.gutenberg.org/ebooks/45.epub.noimages"
  ["anne-of-avonlea-2"]="https://www.gutenberg.org/ebooks/47.epub.noimages"
  ["anne-of-the-island-3"]="https://www.gutenberg.org/ebooks/51.epub.noimages"
)

for name in "${!CORPUS[@]}"; do
  destination="${CORPUS_DIR}/${name}.epub"
  if [ -s "$destination" ]; then
    echo "have    $destination"
    continue
  fi
  echo "fetch   $destination"
  curl -fsSL --retry 3 -o "$destination" "${CORPUS[$name]}"
done

echo
echo "Corpus in $CORPUS_DIR:"
ls -lh "$CORPUS_DIR"
echo
echo "Sprint 2 adds the upload step. Until then, ingest manually."
