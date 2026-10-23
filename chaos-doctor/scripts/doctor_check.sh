#!/usr/bin/env bash
# Check that chaos-doctor is installed and the model server answers.
set -u
URL="${CHAOS_DOCTOR_OLLAMA_URL:-http://localhost:11434}"
MODEL="${CHAOS_DOCTOR_MODEL:-qwen3:8b}"

if ! command -v chaos-doctor >/dev/null 2>&1; then
  echo "chaos-doctor is not installed. From the repo root run: pip install -e ." >&2
  exit 1
fi

if ! tags=$(curl -sf "$URL/api/tags"); then
  echo "Ollama is not reachable at $URL. Run 'ollama serve', or use --offline." >&2
  exit 2
fi

if ! grep -q "\"$MODEL\"" <<<"$tags"; then
  echo "Model $MODEL is not pulled on $URL. Run: ollama pull $MODEL" >&2
  exit 3
fi

echo "OK: chaos-doctor installed, $MODEL available at $URL"
