#!/usr/bin/env bash
set -euo pipefail

PROJECT="${1:-.}"
CONFIG="${2:-examples/local_models_jit.json}"
SEQUENCE="${3:-qwen,nemotron,qwen}"
OUTPUT="${4:-${PROJECT%/}/.office/benchmarks/model-cold-start.json}"

office model cold-start "$PROJECT" --config "$CONFIG" --sequence "$SEQUENCE" --output "$OUTPUT"
office model status "$PROJECT" --config "$CONFIG"
printf '\nCold-start evidence: %s\n' "$OUTPUT"
