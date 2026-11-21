#!/usr/bin/env bash
# Start N parallel ZeroGPT site labelers (isolated Chrome profiles + shard queues).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
SHARDS="${ZEROGPT_SITE_SHARDS:-4}"
PY="${ROOT}/venv/bin/python"
OUT="${ROOT}/data/zerogpt_site_dpo"
LOGDIR="${ROOT}/logs"
mkdir -p "$OUT" "$LOGDIR" browser_profiles
POOL_DIR="$OUT"
PIDFILE="$OUT/pool.pids"

if [[ -f "$PIDFILE" ]]; then
  while read -r pid; do
    kill "$pid" 2>/dev/null || true
  done < "$PIDFILE"
  rm -f "$PIDFILE"
fi

: > "$PIDFILE"
for i in $(seq 0 $((SHARDS - 1))); do
  log="$LOGDIR/zerogpt_site_shard_${i}_$(date +%Y%m%d).log"
  nohup "$PY" scripts/zerogpt_site_labels.py \
    --candidates data/zerogpt_dpo_run1/candidates.jsonl \
    --out-dir "$OUT" \
    --resume \
    --shard-index "$i" \
    --shard-count "$SHARDS" \
    >>"$log" 2>&1 &
  echo $! >>"$PIDFILE"
  echo "started shard $i pid=$! log=$log"
done

echo "pool pids: $(tr '\n' ' ' <"$PIDFILE")"