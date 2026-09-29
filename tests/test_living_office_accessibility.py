from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'src/engineering_office/ui/index.html').read_text()
CSS=(ROOT/'src/engineering_office/ui/app.css').read_text()
APP=(ROOT/'src/engineering_office/ui/app.js').read_text()

def test_canvas_has_keyboard_semantic_roster_and_text_summary():
    assert 'agent-roster' in HTML
    assert 'floor-accessible-summary' in HTML
    assert 'aria-live="polite"' in HTML
    assert 'data-roster-agent' in APP

def test_reduced_motion_preserves_information():
    assert 'prefers-reduced-motion:reduce' in CSS.replace(' ','')
    assert 'reducedMotion' in APP

def test_state_is_expressed_as_text_not_color_only():
    assert 'agent-status' in HTML or 'agent-status' in APP
    assert 'floor-activity-summary' in HTML
