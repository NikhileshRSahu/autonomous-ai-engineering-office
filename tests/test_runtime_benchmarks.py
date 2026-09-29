from pathlib import Path


def adapter(*, supported=True, latency=10.0, correct=True, ram_ok=True):
    class A:
        def capability(self): return {"supported":supported,"reason":None if supported else "missing runtime"}
        def run(self): return {"latency_seconds":latency,"correct":correct,"ram_ok":ram_ok,"stable":True}
    return A()


def test_registry_persists_selection_by_fingerprint(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry
    reg=RuntimeBenchmarkRegistry(tmp_path)
    fp=reg.fingerprint({"gpu":"5060"},{"runtime":"llama"},{"model":"qwen"},{"ctx":16384})
    reg.record("residency", {"fingerprint":fp,"selected":True,"strategy":"warm"})
    assert reg.selected("residency", fp)["strategy"] == "warm"
    assert reg.selected("residency", "other") is None


def test_vllm_unsupported_is_skipped(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, VllmSleepBenchmark
    reg=RuntimeBenchmarkRegistry(tmp_path)
    out=VllmSleepBenchmark(reg).evaluate("fp", baseline=adapter(latency=10), candidate=adapter(supported=False))
    assert out.status == "SKIPPED_UNSUPPORTED"
    assert out.selected is False


def test_vllm_slower_or_incorrect_is_rejected(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, VllmSleepBenchmark
    reg=RuntimeBenchmarkRegistry(tmp_path)
    slower=VllmSleepBenchmark(reg).evaluate("fp1", baseline=adapter(latency=10), candidate=adapter(latency=12))
    wrong=VllmSleepBenchmark(reg).evaluate("fp2", baseline=adapter(latency=10), candidate=adapter(latency=5, correct=False))
    assert not slower.selected and slower.reason == "candidate_not_faster"
    assert not wrong.selected and wrong.reason == "correctness_gate_failed"


def test_vllm_success_selects_sleep_wake(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, VllmSleepBenchmark
    reg=RuntimeBenchmarkRegistry(tmp_path)
    out=VllmSleepBenchmark(reg).evaluate("fp", baseline=adapter(latency=10), candidate=adapter(latency=4))
    assert out.status == "SUPPORTED_AND_BENCHMARKED"
    assert out.selected is True
    assert reg.selected("vllm_sleep", "fp")["selected"] is True


def test_ram_guard_rejects_candidate(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, VllmSleepBenchmark
    out=VllmSleepBenchmark(RuntimeBenchmarkRegistry(tmp_path)).evaluate("fp", baseline=adapter(latency=10), candidate=adapter(latency=4, ram_ok=False))
    assert not out.selected and out.reason == "memory_guard_failed"


def test_llama_warm_load_falls_back_when_candidate_not_better(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, LlamaWarmLoadBenchmark
    out=LlamaWarmLoadBenchmark(RuntimeBenchmarkRegistry(tmp_path)).evaluate("fp", cold=adapter(latency=8), warm=adapter(latency=9))
    assert out.selected_strategy == "cold"
