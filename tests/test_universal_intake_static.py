from pathlib import Path

UI = Path('src/engineering_office/ui')


def test_onboarding_exposes_universal_intake_modes():
    html = (UI / 'index.html').read_text()
    for token in ['Folder', 'Files / Archive', 'Paste', 'Git', 'New project', 'intake-drop-zone', 'intake-files', 'intake-folder', 'intake-objective']:
        assert token in html


def test_browser_ui_has_upload_dragdrop_and_archive_mode_support():
    js = (UI / 'app.js').read_text()
    for token in ['/api/intake/path', '/api/intake/paste', '/api/intake/git', '/api/intake/new', '/api/intake/sessions', 'dragover', 'drop', 'webkitRelativePath', "mode:'archive'"]:
        assert token in js


def test_new_floor_reuses_universal_intake_component():
    html = (UI / 'index.html').read_text()
    js = (UI / 'app.js').read_text()
    assert 'new-floor-form' not in html
    assert 'openUniversalIntake' in js
    assert 'New Floor' in js


def test_network_failure_has_actionable_message_not_failed_to_fetch():
    js = (UI / 'app.js').read_text()
    assert 'Office backend unreachable' in js
    assert 'BACKEND_UNREACHABLE' in js
    assert "Failed to fetch" not in js


def test_paste_supports_multiple_named_files_and_preserves_state_on_error():
    html = (UI / 'index.html').read_text()
    js = (UI / 'app.js').read_text()
    assert 'paste-items' in html
    assert 'add-paste-file' in html
    assert 'paste-path' in js
    assert 'paste-content' in js
    assert 'resetIntakeForm' in js
    assert 'catch(err)' in js


def test_intake_progress_states_are_user_facing():
    js = (UI / 'app.js').read_text()
    for text in ['Uploading', 'Validating', 'Extracting', 'Detecting project root', 'Opening floor', 'Staffing team']:
        assert text in js
