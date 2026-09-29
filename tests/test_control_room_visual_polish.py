from pathlib import Path

UI = Path('src/engineering_office/ui')


def test_floor_uses_role_aware_pixel_engineer_sprites_and_activity_zones():
    js = (UI / 'app.js').read_text()
    css = (UI / 'app.css').read_text()
    for token in ['agent-sprite', 'sprite-hair', 'sprite-face', 'sprite-torso', 'sprite-arm', 'sprite-legs', 'sprite-tool']:
        assert token in js or token in css
    for token in ['zone-research', 'zone-meeting', 'zone-lab', 'zone-review', 'zone-break']:
        assert token in css
    assert 'destinationFor' in js
    assert 'activityFor' in js


def test_floor_visualizes_agent_handoffs_and_attention_bubbles():
    js = (UI / 'app.js').read_text()
    css = (UI / 'app.css').read_text()
    assert 'renderHandoffs' in js
    assert 'handoff-line' in js
    assert 'handoff-pulse' in css
    assert 'needs-attention' in js
    assert 'speech-tail' in css


def test_visual_states_drive_distinct_motion_and_equipment():
    js = (UI / 'app.js').read_text()
    css = (UI / 'app.css').read_text()
    for state in ['researching', 'coding', 'experimenting', 'reviewing', 'verifying', 'blocked', 'idle']:
        assert state in js
    for animation in ['walk-bob', 'typing-hands', 'review-nod', 'verify-pulse', 'blocked-shake']:
        assert animation in css


def test_roster_and_inspector_gain_live_visual_identity_without_external_assets():
    html = (UI / 'index.html').read_text()
    js = (UI / 'app.js').read_text()
    css = (UI / 'app.css').read_text()
    assert 'floor-activity-summary' in html
    assert 'roster-sprite' in js
    assert 'inspector-portrait' in js
    assert 'agent-model-pill' in js
    assert 'https://' not in html
    assert 'https://' not in css
    assert 'https://' not in js
