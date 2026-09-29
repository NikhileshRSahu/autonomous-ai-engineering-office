from pathlib import Path

UI = Path('src/engineering_office/ui')
HTML = (UI / 'index.html').read_text()
APP = (UI / 'app.js').read_text()
CSS = (UI / 'app.css').read_text()
VENDOR = (UI / 'vendor/living-floor-renderer.min.js').read_text()


def test_default_view_has_simple_run_overview_and_real_timers():
    for token in [
        'run-overview', 'run-mode-label', 'run-objective', 'run-stage-strip',
        'run-total-time', 'run-stage-time', 'run-eta', 'needs-you-card',
        'whats-happening', 'open-report-btn', 'open-report-folder-btn',
        'view-evidence-btn', 'replay-run-btn',
    ]:
        assert token in HTML
    assert '/api/run' in APP
    assert '/api/run/timing' in APP
    assert '/api/needs-user' in APP
    assert '/api/run/report' in APP
    assert 'formatDuration' in APP
    assert 'renderRunOverview' in APP


def test_default_agent_tab_is_friendly_activity_and_advanced_views_remain():
    assert "tab:'ACTIVITY'" in APP
    for tab in ['ACTIVITY','TERMINAL','FILES','MESSAGES','TASK','EVIDENCE','TRACES','MODEL']:
        assert tab in APP
    assert 'friendlyEvent' in APP
    assert 'What they are doing' in APP or "WHAT THEY'RE DOING" in APP
    assert 'Open terminal' in APP or 'TERMINAL' in APP


def test_stage_progress_uses_real_stage_states_not_fake_percentages():
    assert 'renderStageStrip' in APP
    assert '.stages' in APP
    assert 'stage.state' in APP or 's.state' in APP
    assert 'run-progress-percent' not in HTML
    assert 'model-load-percent' not in HTML
    assert 'Math.random' not in APP


def test_needs_you_and_model_wait_copy_explains_when_no_action_is_needed():
    assert 'Nothing needs you right now' in APP
    assert 'No action needed' in APP
    assert 'Loading' in APP
    assert 'model-loading' in APP or 'MODEL_LOADING' in APP
    assert 'waiting for the stronger' in APP.lower() or 'stronger review model' in APP.lower()


def test_report_actions_and_eta_learning_state_are_user_friendly():
    assert 'Learning from this run' in APP
    assert 'Open report' in HTML or 'Open report' in APP
    assert 'Open output folder' in HTML or 'Open report folder' in HTML or 'Open report folder' in APP
    assert 'View evidence' in HTML or 'View evidence' in APP
    assert 'Replay run' in HTML or 'Replay run' in APP


def test_character_renderer_has_explicit_larger_character_scale_hook():
    assert 'characterScale' in VENDOR
    assert 'hitRadius' in VENDOR
    assert '.friendly-control-room' in CSS
    assert '.run-overview' in CSS
    assert '.needs-you-card' in CSS
    assert '.run-timer' in CSS


def test_control_room_can_start_selected_run_mode():
    assert 'run-mode-select' in HTML
    for value in ['fast-audit','check-report','fix','complete','custom']:
        assert value in HTML
    assert 'selectedRunMode' in APP
    assert "body:json({mode" in APP or "mode:selectedRunMode" in APP
