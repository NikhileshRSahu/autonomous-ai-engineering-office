# Local Runtime Optimization

The Engineering Office treats faster inference strategies as benchmark candidates, not assumptions. The deterministic verifier and acceptance gates never change because a faster runtime is selected.

## Residency priority

The intended priority is:

1. reuse the exact already-ready local model;
2. wake a benchmark-approved sleeping/CPU-resident model;
3. use a benchmark-approved warm llama.cpp path;
4. fall back to the existing PID-owned cold-load lifecycle.

Unknown processes are never killed. Exact `/v1/models` identity and loopback-only endpoint checks remain mandatory.

## vLLM sleep / CPU residency

vLLM sleep/offload is optional. Benchmark it on the target laptop; do not install or promote it during a normal Office run. A strategy is eligible only after support, correctness, stability, RAM guardrails, and speed improvement are measured for the current hardware/model/runtime fingerprint.

## Qwen speculative decoding

Record real measurements, then ingest them:

```bash
office benchmark speculative qwen /path/to/project --results qwen-speculative-results.json
```

Baseline, n-gram and compatible draft-model candidates may be compared. Promotion requires at least 15% median latency improvement with deterministic/tool-call correctness and stability preserved.

## Nemotron TensorRT-LLM / NVFP4

Treat TensorRT-LLM/NVFP4 as a challenger, not a guaranteed RTX laptop path:

```bash
office benchmark nemotron-runtime /path/to/project --results nemotron-runtime-results.json
```

`SKIPPED_UNSUPPORTED`, `NOT_INSTALLED`, or a slower benchmark simply keeps llama.cpp as the fallback. The Office must never fabricate support or timing numbers.

## Residency benchmark

```bash
office benchmark residency /path/to/project --results residency-results.json
```

All benchmark decisions are fingerprinted by hardware/runtime/model/config so a result from a different machine or quantization is not silently reused.

## Model-load timing

For real Qwen/Nemotron cold-start evidence on the model host:

```bash
office model cold-start /path/to/project --config examples/local_models_jit.json --sequence qwen,nemotron,qwen
```

The resulting timestamps are evidence for tuning; they are not replaced by a fixed ETA in the UI.
