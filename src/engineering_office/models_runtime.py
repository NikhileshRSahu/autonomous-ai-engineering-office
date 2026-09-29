from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol
from urllib.request import Request, urlopen
import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from .models import Complexity


@dataclass(slots=True)
class ModelResponse:
    content: str
    usage: dict[str, int] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class ModelProvider(Protocol):
    def complete(self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None) -> ModelResponse: ...


@dataclass(slots=True, repr=False)
class ModelProfile:
    name: str
    endpoint: str
    model: str
    api_key_env: str | None = None
    temperature: float = 0.1
    timeout: int = 180
    max_tokens: int | None = None

    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env) if self.api_key_env else None

    def __repr__(self) -> str:
        return f"ModelProfile(name={self.name!r}, endpoint={self.endpoint!r}, model={self.model!r}, api_key_env={self.api_key_env!r})"


class OpenAICompatibleProvider:
    def __init__(self, profile: ModelProfile):
        self.profile = profile

    def complete(self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None) -> ModelResponse:
        endpoint = self.profile.endpoint.rstrip("/") + "/chat/completions"
        payload: dict[str, Any] = {
            "model": self.profile.model,
            "messages": messages,
            "temperature": self.profile.temperature,
        }
        if self.profile.max_tokens is not None:
            payload["max_tokens"] = self.profile.max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        headers = {"Content-Type": "application/json"}
        key = self.profile.api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        req = Request(endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
        with urlopen(req, timeout=self.profile.timeout) as response:
            raw = json.loads(response.read().decode())
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("OpenAI-compatible response missing choices[0].message.content") from exc
        usage_raw = raw.get("usage") or {}
        prompt = int(usage_raw.get("prompt_tokens", 0) or 0)
        completion = int(usage_raw.get("completion_tokens", 0) or 0)
        usage = {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": int(usage_raw.get("total_tokens", prompt + completion) or 0)}
        return ModelResponse(str(content), usage=usage, raw=raw)


class ScriptedProvider:
    """Deterministic provider for tests/demos. Responses are consumed FIFO."""
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []
        self._lock = threading.Lock()

    def complete(self, messages: list[dict[str, str]], response_format: dict[str, Any] | None = None) -> ModelResponse:
        with self._lock:
            self.calls.append(messages)
            if not self.responses:
                raise RuntimeError("scripted provider has no responses left")
            content = self.responses.pop(0)
        return ModelResponse(content, usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0})


class ModelLifecycleError(RuntimeError):
    pass


class ModelEndpointConflict(ModelLifecycleError):
    pass


class ModelOwnershipError(ModelLifecycleError):
    pass


class ModelStartupTimeout(ModelLifecycleError):
    pass


@dataclass(slots=True)
class LocalModelSpec:
    name: str
    endpoint: str
    expected_model: str
    start_command: list[str]
    startup_timeout: float = 600.0
    poll_interval: float = 2.0
    shutdown_timeout: float = 15.0
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("local model name is required")
        if not self.expected_model.strip():
            raise ValueError("expected_model is required")
        if not self.start_command or not all(isinstance(x, str) and x for x in self.start_command):
            raise ValueError("start_command must be a non-empty argv list")
        endpoint = self.endpoint.rstrip("/")
        if not (endpoint.startswith("http://127.0.0.1") or endpoint.startswith("http://localhost") or endpoint.startswith("http://[::1]")):
            raise ValueError("local model endpoint must be loopback-only")


class LocalModelManager:
    """Serializes heavyweight local-model transitions and only stops owned processes."""

    def __init__(
        self,
        specs: dict[str, LocalModelSpec],
        runtime_dir: str | Path,
        *,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ):
        self.specs = dict(specs)
        self.runtime_dir = Path(runtime_dir).resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._event_sink = event_sink
        self._switch_lock = threading.RLock()
        self._processes: dict[str, subprocess.Popen] = {}
        self._current_model: str | None = None

    @property
    def current_model(self) -> str | None:
        return self._current_model

    def ensure(self, name: str) -> dict[str, Any]:
        with self._switch_lock:
            return self._ensure_locked(name)

    def _ensure_locked(self, name: str) -> dict[str, Any]:
        spec = self._spec(name)
        ids = self._list_model_ids(spec)
        if spec.expected_model in ids:
            self._current_model = name
            status = {"name": name, "status": "READY", "model_ids": ids, "endpoint": spec.endpoint}
            self._emit("model.ready", name, external=name not in self._processes, model_ids=ids)
            return status
        if ids:
            raise ModelEndpointConflict(
                f"endpoint {spec.endpoint} is occupied by unexpected model(s): {', '.join(ids)}; expected {spec.expected_model}"
            )

        stopped_current = None
        if self._current_model and self._current_model != name:
            stopped_current = self._current_model
            self.stop(stopped_current)

        # Memory safety: before loading a heavyweight target, make sure no other
        # model endpoint is occupied. Office-owned peers may be stopped; an
        # unowned process is never killed implicitly.
        for other_name, other_spec in self.specs.items():
            if other_name == name or other_name == stopped_current:
                continue
            other_ids = self._list_model_ids(other_spec)
            other_owned = other_name in self._processes or self._pid_path(other_name).exists()
            if other_ids and not other_owned:
                raise ModelEndpointConflict(
                    f"cannot start {name}: unowned model endpoint {other_spec.endpoint} is active "
                    f"with {', '.join(other_ids)}; stop it explicitly or adopt it before switching"
                )
            if other_owned:
                self.stop(other_name)

        self._emit("model.starting", name, endpoint=spec.endpoint, timeout=spec.startup_timeout)
        process = self._spawn(spec)
        self._processes[name] = process
        self._write_pid_record(spec, process)
        deadline = time.monotonic() + spec.startup_timeout
        while time.monotonic() < deadline:
            ids = self._list_model_ids(spec)
            if spec.expected_model in ids:
                self._current_model = name
                self._emit("model.ready", name, external=False, pid=process.pid, model_ids=ids)
                return {"name": name, "status": "READY", "model_ids": ids, "endpoint": spec.endpoint, "pid": process.pid}
            if ids:
                # Our process is owned, but the endpoint belongs to something else. Stop only our process.
                self._terminate_owned_process(name, process, spec.shutdown_timeout)
                raise ModelEndpointConflict(
                    f"endpoint {spec.endpoint} became occupied by unexpected model(s): {', '.join(ids)}; expected {spec.expected_model}"
                )
            if process.poll() is not None:
                self._processes.pop(name, None)
                self._pid_path(name).unlink(missing_ok=True)
                raise ModelLifecycleError(f"local model {name} exited before becoming ready (code {process.returncode})")
            time.sleep(spec.poll_interval)

        self._terminate_owned_process(name, process, spec.shutdown_timeout)
        raise ModelStartupTimeout(f"local model {name} did not become ready within {spec.startup_timeout:.0f}s")

    def stop(self, name: str) -> dict[str, Any]:
        with self._switch_lock:
            spec = self._spec(name)
            process = self._processes.get(name)
            if process is not None:
                self._terminate_owned_process(name, process, spec.shutdown_timeout)
                return {"name": name, "status": "STOPPED"}

            path = self._pid_path(name)
            if not path.exists():
                if self._current_model == name:
                    self._current_model = None
                return {"name": name, "status": "STOPPED", "external": bool(self._list_model_ids(spec))}

            try:
                meta = json.loads(path.read_text())
                pid = int(meta["pid"])
                expected = str(meta["command_fingerprint"])
                expected_start = meta.get("process_start_ticks")
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ModelOwnershipError(f"invalid PID ownership record for {name}") from exc
            actual = self._pid_command_fingerprint(pid)
            if actual != expected:
                raise ModelOwnershipError(
                    f"refusing to stop PID {pid} for {name}: process command does not match Office ownership record"
                )
            if expected_start is not None:
                actual_start = self._pid_start_ticks(pid)
                if actual_start != int(expected_start):
                    raise ModelOwnershipError(
                        f"refusing to stop PID {pid} for {name}: process start identity does not match Office ownership record"
                    )
            self._kill_pid(pid, force=False)
            path.unlink(missing_ok=True)
            if self._current_model == name:
                self._current_model = None
            self._emit("model.stopped", name, pid=pid, recovered_pid_record=True)
            return {"name": name, "status": "STOPPED", "pid": pid}

    def status(self, name: str) -> dict[str, Any]:
        spec = self._spec(name)
        ids = self._list_model_ids(spec)
        if spec.expected_model in ids:
            state = "READY"
        elif ids:
            state = "CONFLICT"
        elif name in self._processes and self._processes[name].poll() is None:
            state = "LOADING"
        else:
            state = "STOPPED"
        return {"name": name, "status": state, "model_ids": ids, "endpoint": spec.endpoint, "owned": name in self._processes or self._pid_path(name).exists()}

    def stop_all_owned(self) -> list[dict[str, Any]]:
        results = []
        for name in self.specs:
            if name in self._processes or self._pid_path(name).exists():
                results.append(self.stop(name))
        return results

    def cold_start_validate(self, sequence: list[str], output_path: str | Path | None = None) -> dict[str, Any]:
        if not sequence:
            raise ValueError("cold-start sequence must include at least one model")
        for name in sequence:
            self._spec(name)
        with self._switch_lock:
            self.stop_all_owned()
            occupied = {}
            for name, spec in self.specs.items():
                ids = self._list_model_ids(spec)
                if ids:
                    occupied[name] = ids
            if occupied:
                detail = "; ".join(f"{name}: {','.join(ids)}" for name, ids in occupied.items())
                raise ModelEndpointConflict(f"cold-start validation requires empty model endpoints after stopping Office-owned servers; found {detail}")

            started_at = self._timestamp()
            transitions = []
            for name in sequence:
                t0 = time.monotonic()
                status = self._ensure_locked(name)
                elapsed = time.monotonic() - t0
                transitions.append({
                    "model": name,
                    "status": status.get("status"),
                    "model_ids": status.get("model_ids", []),
                    "elapsed_seconds": round(elapsed, 3),
                    "completed_at": self._timestamp(),
                })
            report = {
                "cold_start": True,
                "started_at": started_at,
                "completed_at": self._timestamp(),
                "sequence": list(sequence),
                "transitions": transitions,
                "final_model": self._current_model,
                "event_log": str(self.runtime_dir / "lifecycle-events.jsonl"),
            }
            if output_path is not None:
                path = Path(output_path).expanduser()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
            return report

    def _spec(self, name: str) -> LocalModelSpec:
        try:
            return self.specs[name]
        except KeyError as exc:
            raise KeyError(f"unknown local model: {name}") from exc

    def _models_url(self, spec: LocalModelSpec) -> str:
        return spec.endpoint.rstrip("/") + "/models"

    def _list_model_ids(self, spec: LocalModelSpec) -> list[str]:
        request = Request(self._models_url(spec), method="GET")
        try:
            with urlopen(request, timeout=2.0) as response:
                raw = json.loads(response.read().decode())
        except Exception:
            return []
        data = raw.get("data") if isinstance(raw, dict) else None
        if not isinstance(data, list):
            return []
        ids = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                ids.append(item["id"])
        return ids

    def _spawn(self, spec: LocalModelSpec):
        env = os.environ.copy()
        env.update(spec.env)
        log_path = self.runtime_dir / f"{spec.name}.log"
        log_handle = log_path.open("ab", buffering=0)
        try:
            process = subprocess.Popen(
                list(spec.start_command),
                cwd=spec.cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception:
            log_handle.close()
            raise
        # Keep the handle alive with the process object; close when stopped.
        setattr(process, "_office_log_handle", log_handle)
        return process

    def _terminate_owned_process(self, name: str, process, timeout: float) -> None:
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=max(1.0, min(timeout, 5.0)))
        finally:
            handle = getattr(process, "_office_log_handle", None)
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass
            self._processes.pop(name, None)
            self._pid_path(name).unlink(missing_ok=True)
            if self._current_model == name:
                self._current_model = None
            self._emit("model.stopped", name, pid=getattr(process, "pid", None))

    def _pid_path(self, name: str) -> Path:
        return self.runtime_dir / f"{name}.pid.json"

    @staticmethod
    def _command_fingerprint(argv: list[str]) -> str:
        return hashlib.sha256(json.dumps(list(argv), separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def _pid_metadata(self, spec: LocalModelSpec, pid: int) -> dict[str, Any]:
        return {
            "pid": int(pid),
            "model": spec.name,
            "endpoint": spec.endpoint,
            "expected_model": spec.expected_model,
            "command_fingerprint": self._command_fingerprint(spec.start_command),
            "process_start_ticks": self._pid_start_ticks(pid),
            "created_at": self._timestamp(),
        }

    def _write_pid_record(self, spec: LocalModelSpec, process) -> None:
        path = self._pid_path(spec.name)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._pid_metadata(spec, process.pid), indent=2, sort_keys=True))
        tmp.replace(path)

    def _pid_command_fingerprint(self, pid: int) -> str | None:
        try:
            raw = Path(f"/proc/{int(pid)}/cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            return None
        argv = [chunk.decode(errors="replace") for chunk in raw.split(b"\0") if chunk]
        return self._command_fingerprint(argv) if argv else None

    def _pid_start_ticks(self, pid: int) -> int | None:
        try:
            raw = Path(f"/proc/{int(pid)}/stat").read_text()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            return None
        # /proc/<pid>/stat field 2 is parenthesized and may contain spaces; split after the final ')'.
        try:
            rest = raw[raw.rfind(")") + 2 :].split()
            return int(rest[19])  # field 22 overall => index 19 after fields 1-2 are removed
        except (ValueError, IndexError):
            return None

    def _kill_pid(self, pid: int, force: bool = False) -> None:
        os.kill(int(pid), signal.SIGKILL if force else signal.SIGTERM)

    @staticmethod
    def _timestamp() -> str:
        return _dt.datetime.now(_dt.timezone.utc).isoformat()

    def _emit(self, event: str, model: str, **payload: Any) -> None:
        data = {"event": event, "model": model, "timestamp": self._timestamp(), **payload}
        log_path = self.runtime_dir / "lifecycle-events.jsonl"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True, default=str) + "\n")
        if self._event_sink is not None:
            self._event_sink(data)


class ResidencyState(str, Enum):
    COLD = "COLD"
    LOADING_USB = "LOADING_USB"
    CPU_RESIDENT = "CPU_RESIDENT"
    SLEEPING = "SLEEPING"
    WAKING = "WAKING"
    GPU_READY = "GPU_READY"
    BUSY = "BUSY"
    ERROR = "ERROR"


class ModelResidencyManager:
    """Benchmark-aware residency wrapper that preserves LocalModelManager safety.

    Optional sleep/wake hooks are injected by runtime benchmark adapters. Without
    a proven hook the manager falls back to the existing owned-process stop/start
    lifecycle rather than assuming CPU residency is available.
    """

    def __init__(
        self,
        local_manager: LocalModelManager | Any,
        *,
        sleep_hooks: dict[str, Callable[[], Any]] | None = None,
        wake_hooks: dict[str, Callable[[], Any]] | None = None,
        memory_guard: Callable[[str], bool] | None = None,
    ):
        self.local = local_manager
        self.specs = getattr(local_manager, "specs", {})
        self.sleep_hooks = dict(sleep_hooks or {})
        self.wake_hooks = dict(wake_hooks or {})
        self.memory_guard = memory_guard or (lambda _name: True)
        self._lock = threading.RLock()
        self._states: dict[str, ResidencyState] = {name: ResidencyState.COLD for name in self.specs}
        self._current_model: str | None = getattr(local_manager, "current_model", None)

    @property
    def current_model(self) -> str | None:
        return self._current_model or getattr(self.local, "current_model", None)

    def status(self, name: str) -> dict[str, Any]:
        base = dict(self.local.status(name))
        if base.get("status") == "READY":
            state = ResidencyState.GPU_READY
            self._states[name] = state
            self._current_model = name
        else:
            state = self._states.get(name, ResidencyState.COLD)
        base["residency"] = state.value
        return base

    def ensure(self, name: str) -> dict[str, Any]:
        with self._lock:
            base = self.local.status(name)
            if base.get("status") == "READY":
                self._states[name] = ResidencyState.GPU_READY
                self._current_model = name
                return {**base, "residency": ResidencyState.GPU_READY.value, "path": "already-ready"}

            current = self.current_model
            if current and current != name:
                try:
                    current_status = self.local.status(current)
                except Exception:
                    current_status = {"status": "STOPPED"}
                if current_status.get("status") == "READY" or self._states.get(current) in {ResidencyState.GPU_READY, ResidencyState.CPU_RESIDENT}:
                    self.sleep(current)

            state = self._states.get(name, ResidencyState.COLD)
            if state in {ResidencyState.CPU_RESIDENT, ResidencyState.SLEEPING} and name in self.wake_hooks:
                self._states[name] = ResidencyState.WAKING
                self._emit("model.waking", name, residency=ResidencyState.WAKING.value)
                started = time.monotonic()
                result = self.wake_hooks[name]() or {}
                self._states[name] = ResidencyState.GPU_READY
                self._current_model = name
                self._emit("model.ready", name, residency=ResidencyState.GPU_READY.value, wake_seconds=round(time.monotonic()-started, 3))
                return {"name": name, "status": "READY", **(result if isinstance(result, dict) else {}), "residency": ResidencyState.GPU_READY.value, "path": "wake"}

            if not self.memory_guard(name):
                self._states[name] = ResidencyState.ERROR
                self._emit("model.error", name, reason="memory guard rejected cold load")
                raise ModelLifecycleError(f"memory guard rejected cold load for {name}")

            self._states[name] = ResidencyState.LOADING_USB
            self._emit("model.loading", name, residency=ResidencyState.LOADING_USB.value)
            started = time.monotonic()
            result = self.local.ensure(name)
            self._states[name] = ResidencyState.GPU_READY
            self._current_model = name
            self._emit("model.ready", name, residency=ResidencyState.GPU_READY.value, cold_load_seconds=round(time.monotonic()-started, 3))
            return {**result, "residency": ResidencyState.GPU_READY.value, "path": result.get("path", "cold") if isinstance(result, dict) else "cold"}

    def sleep(self, name: str) -> dict[str, Any]:
        with self._lock:
            if name in self.sleep_hooks:
                self._states[name] = ResidencyState.SLEEPING
                self._emit("model.sleeping", name, residency=ResidencyState.SLEEPING.value)
                started = time.monotonic()
                self.sleep_hooks[name]()
                self._states[name] = ResidencyState.CPU_RESIDENT
                if self._current_model == name:
                    self._current_model = None
                self._emit("model.slept", name, residency=ResidencyState.CPU_RESIDENT.value, sleep_seconds=round(time.monotonic()-started, 3))
                return {"name": name, "status": "SLEEPING", "residency": ResidencyState.CPU_RESIDENT.value}
            result = self.local.stop(name)
            self._states[name] = ResidencyState.COLD
            if self._current_model == name:
                self._current_model = None
            return {**result, "residency": ResidencyState.COLD.value}

    def wake(self, name: str) -> dict[str, Any]:
        return self.ensure(name)

    def stop(self, name: str) -> dict[str, Any]:
        with self._lock:
            result = self.local.stop(name)
            self._states[name] = ResidencyState.COLD
            if self._current_model == name:
                self._current_model = None
            return {**result, "residency": ResidencyState.COLD.value}

    def stop_all_owned(self) -> list[dict[str, Any]]:
        results = self.local.stop_all_owned()
        for name in self.specs:
            self._states[name] = ResidencyState.COLD
        self._current_model = None
        return results

    def _emit(self, event: str, model: str, **payload: Any) -> None:
        emit = getattr(self.local, "_emit", None)
        if emit is not None:
            emit(event, model, **payload)


class ModelRouter:
    def __init__(
        self,
        providers: dict[Complexity, ModelProvider],
        *,
        lifecycle_manager: LocalModelManager | Any | None = None,
        model_bindings: dict[Complexity, str] | None = None,
    ):
        self.providers = dict(providers)
        self.lifecycle_manager = lifecycle_manager
        self.model_bindings = dict(model_bindings or {})

    def route(self, complexity: Complexity) -> ModelProvider:
        if complexity not in self.providers:
            raise KeyError(f"no model provider configured for complexity {complexity.value}")
        provider = self.providers[complexity]
        model_name = self.model_bindings.get(complexity)
        if self.lifecycle_manager is not None and model_name and not getattr(provider, "defer_lifecycle", False):
            self.lifecycle_manager.ensure(model_name)
        return provider

    def model_key(self, complexity: Complexity) -> str | None:
        return self.model_bindings.get(complexity)

    def order_tasks_for_residency(self, tasks: list[Any]) -> list[Any]:
        tasks = list(tasks)
        if not tasks or self.lifecycle_manager is None or not self.model_bindings:
            return tasks
        grouped: dict[str | None, list[Any]] = {}
        order: list[str | None] = []
        for task in tasks:
            key = self.model_key(task.complexity)
            if key not in grouped:
                grouped[key] = []
                order.append(key)
            grouped[key].append(task)
        current = getattr(self.lifecycle_manager, "current_model", None)
        keys = list(order)
        if current in grouped:
            keys.remove(current)
            keys.insert(0, current)
        elif keys:
            first_index = {key: idx for idx, key in enumerate(order)}
            keys.sort(key=lambda key: (-len(grouped[key]), first_index[key]))
        result: list[Any] = []
        for key in keys:
            result.extend(grouped[key])
        return result

    def same_model_batch(self, tasks: list[Any], limit: int) -> list[Any]:
        ordered = self.order_tasks_for_residency(tasks)
        if not ordered or limit <= 0:
            return []
        if self.lifecycle_manager is None or not self.model_bindings:
            return ordered[:limit]
        first_key = self.model_key(ordered[0].complexity)
        batch = [task for task in ordered if self.model_key(task.complexity) == first_key]
        return batch[:limit]
