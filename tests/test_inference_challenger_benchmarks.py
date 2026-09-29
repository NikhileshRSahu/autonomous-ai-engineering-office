from pathlib import Path


def result(latencies, correct=True, stable=True):
    return {"latencies_seconds":latencies,"correct":correct,"stable":stable,"ram_ok":True}


def test_qwen_speculative_requires_fifteen_percent_gain(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, QwenSpeculativeBenchmark
    b=QwenSpeculativeBenchmark(RuntimeBenchmarkRegistry(tmp_path))
    rejected=b.evaluate("fp1", baseline=result([10,10,10]), candidates={"ngram":result([9,9,9])})
    promoted=b.evaluate("fp2", baseline=result([10,10,10]), candidates={"ngram":result([8,8,8]),"draft":result([7,7,7])})
    assert rejected.selected_strategy == "baseline"
    assert promoted.selected_strategy == "draft"


def test_qwen_correctness_rejection_beats_speed(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, QwenSpeculativeBenchmark
    out=QwenSpeculativeBenchmark(RuntimeBenchmarkRegistry(tmp_path)).evaluate("fp", baseline=result([10,10]), candidates={"draft":result([2,2],correct=False)})
    assert out.selected_strategy == "baseline"


def test_nemotron_tensorrt_unsupported_is_skip_not_failure(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, NemotronRuntimeBenchmark
    out=NemotronRuntimeBenchmark(RuntimeBenchmarkRegistry(tmp_path)).evaluate("fp", llama=result([9,9]), challenger_capability={"supported":False,"reason":"gpu/runtime unsupported"}, challenger=None)
    assert out.status == "SKIPPED_UNSUPPORTED"
    assert out.selected_strategy == "llama.cpp"


def test_nemotron_nvfp4_challenger_must_be_faster_and_correct(tmp_path: Path):
    from engineering_office.runtime_benchmarks import RuntimeBenchmarkRegistry, NemotronRuntimeBenchmark
    b=NemotronRuntimeBenchmark(RuntimeBenchmarkRegistry(tmp_path))
    good=b.evaluate("fp1", llama=result([10,10]), challenger_capability={"supported":True}, challenger=result([6,6]))
    bad=b.evaluate("fp2", llama=result([10,10]), challenger_capability={"supported":True}, challenger=result([5,5],correct=False))
    assert good.selected_strategy == "tensorrt-nvfp4"
    assert bad.selected_strategy == "llama.cpp"
