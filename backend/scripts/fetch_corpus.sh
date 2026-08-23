#!/bin/bash
# Resumable, retrying download of the OALC corpus (plain HTTP, byte-range resume).
# Writes to backend/data/ (sibling of this script's backend/scripts/ directory).
URL="https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus/resolve/main/corpus.jsonl"
cd "$(dirname "$0")/../data"
mkdir -p "$(pwd)"
for i in $(seq 1 500); do
  curl -sSL -C - --retry 5 --retry-all-errors --speed-limit 1000 --speed-time 60 -o corpus.jsonl.part "$URL" && break
  echo "attempt $i failed ($?), retrying in 30s" >> fetch.log; sleep 30
done
SIZE=$(stat -c %s corpus.jsonl.part)
if [ "$SIZE" -ge 9401179433 ]; then mv corpus.jsonl.part corpus.jsonl && echo "done $SIZE" >> fetch.log; else echo "gave up at $SIZE" >> fetch.log; fi
