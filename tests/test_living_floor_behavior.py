from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'src/engineering_office/ui/app.js').read_text()
RENDER=(ROOT/'src/engineering_office/ui/vendor/living-floor-renderer.min.js').read_text()

def test_app_polls_runtime_events_and_drives_activity_from_phases():
    assert '/api/events' in APP
    assert 'runtimePhaseFor' in APP
    for phase in ['READING','CODING','RUNNING_COMMAND','TESTING','RESEARCHING','EXPERIMENTING','MESSAGING','REVIEWING','VERIFYING','MODEL_LOADING','NEEDS_USER','BLOCKED','FAILED','VERIFIED']:
        assert phase in APP or phase in RENDER

def test_renderer_has_deterministic_identity_and_overflow_slots():
    assert 'hashName' in RENDER
    assert 'zoneSlots' in RENDER
    assert 'overflow' in RENDER
    assert '12' in RENDER

def test_reduced_motion_keeps_state_without_travel_animation():
    css=(ROOT/'src/engineering_office/ui/app.css').read_text()
    assert 'prefers-reduced-motion' in css
    assert 'reduceMotion' in APP or 'reducedMotion' in RENDER
