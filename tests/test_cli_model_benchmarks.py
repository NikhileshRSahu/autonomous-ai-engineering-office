from engineering_office.cli import build_parser


def test_benchmark_parser_accepts_residency_speculative_and_nemotron_runtime():
    parser=build_parser()
    a=parser.parse_args(["benchmark","residency","."])
    b=parser.parse_args(["benchmark","speculative","qwen","."])
    c=parser.parse_args(["benchmark","nemotron-runtime","."])
    assert a.benchmark_kind == "residency"
    assert b.benchmark_kind == "speculative" and b.benchmark_target == "qwen"
    assert c.benchmark_kind == "nemotron-runtime"
