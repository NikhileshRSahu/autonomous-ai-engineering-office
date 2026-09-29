# Local Qwen + Nemotron JIT lifecycle

The Office can keep large local models off RAM until the routed task needs them. This is intended for machines where Qwen3-Coder-30B-A3B and NVIDIA Nemotron 3 Nano 30B-A3B fit on disk but should not remain resident together.

## Roles

- `LOW` / `MEDIUM` -> Qwen (`qwen` lifecycle target): routine code, ROS 2/config editing, tests, repository work.
- `HIGH` / `ESCALATION` -> Nemotron (`nemotron` lifecycle target): difficult diagnosis, controls/physics reasoning, adversarial review.
- PASS/FAIL remains deterministic: `Verifier` executes immutable acceptance gates and does not ask an LLM to decide PASS.

## Configuration

Copy `examples/local_models_jit.json` and edit the GGUF paths and API model IDs to match the exact IDs returned by your local `llama-server /v1/models` endpoint. The example uses the user's pendrive path as a starting template; filenames must match the files actually downloaded.

Important settings:

- `startup_timeout`: 600 seconds by default for slow USB cold loads.
- `model_bindings`: connects Office complexity tiers to lifecycle targets.
- `local_runtime_dir`: stores PID ownership records, server logs, and `lifecycle-events.jsonl`.
- endpoints must be loopback (`127.0.0.1`, `localhost`, or `::1`).

## Safety behavior

Before a model is considered ready, the Office calls `/v1/models` and requires the exact configured model ID. A stale 1.5B server on the expected port therefore produces a conflict rather than being silently accepted.

Only processes created by the Office are stopped automatically. PID recovery validates both the command fingerprint and Linux process start identity to reduce PID-reuse risk. An unowned model on another configured endpoint blocks a heavy-model switch instead of being killed or allowing two large models to compete for RAM.

All in-process switches are serialized. The task scheduler groups currently-ready tasks by model family so compatible Qwen work is batched together and Nemotron work is batched together where dependencies allow, reducing USB reload thrash.

## Operator commands

```bash
office model status . --config examples/local_models_jit.json
office model start qwen . --config examples/local_models_jit.json
office model switch nemotron . --config examples/local_models_jit.json
office model stop nemotron . --config examples/local_models_jit.json
office model stop-all . --config examples/local_models_jit.json
```

A true cold-start lifecycle validation requires all configured endpoints to be empty after Office-owned servers are stopped. It then runs the sequence you specify and records loading times:

```bash
office model cold-start . \
  --config examples/local_models_jit.json \
  --sequence qwen,nemotron,qwen
```

Default report:

```text
.office/benchmarks/model-cold-start.json
```

Persistent lifecycle log:

```text
.office/runtime/models/lifecycle-events.jsonl
```

If an unowned process is already occupying a model endpoint, cold-start fails intentionally. Stop that process explicitly after confirming what it is; the Office will not use `pkill llama-server` or kill an unknown PID.

## Cold-start autonomous proof

The lifecycle report only proves safe model loading/switching. The final proof must still be performed on the target machine:

1. Stop all Office-owned model servers.
2. Confirm `8080` and `8081` are empty.
3. Run `office model cold-start ... --sequence qwen,nemotron,qwen`.
4. Start a fresh project with fixed acceptance tests.
5. Run the Office using this config.
6. Confirm the evidence shows Qwen doing implementation, Nemotron doing difficult review/reasoning, and deterministic acceptance gates deciding PASS.

Do not weaken tests or treat a model's textual claim as verification.
