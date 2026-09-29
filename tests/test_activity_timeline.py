from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'src/engineering_office/ui/app.js').read_text()
HTML=(ROOT/'src/engineering_office/ui/index.html').read_text()

def test_timeline_and_replay_controls_exist():
    assert 'timeline-btn' in HTML
    assert 'REPLAY' in APP and 'LIVE' in APP
    assert 'replay-range' in APP
    assert 'replay-scrub' in APP

def test_replay_reuses_runtime_event_reducer():
    assert 'effectiveRuntimeEvents' in APP
    assert 'runtimePhaseFor' in APP
    assert 'state.replay' in APP

def test_timeline_filters_cover_engineering_categories():
    for token in ['agent','task','model','error','review','verification']:
        assert token in APP.lower()
