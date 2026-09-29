from pathlib import Path

UI = Path("src/engineering_office/ui")


def test_index_has_four_region_desktop_control_room():
    html = (UI / "index.html").read_text()
    for token in ["office-chrome", "office-stage", "agent-inspector", "agent-roster", "floor-switcher"]:
        assert token in html


def test_control_room_has_real_agent_inspector_tabs_and_queue():
    js = (UI / "app.js").read_text()
    for label in ["TERMINAL", "FILES", "MESSAGES", "TASK", "EVIDENCE", "TRACES", "QUEUE"]:
        assert label in js
    assert "/api/agents/" in js
    assert "/steer" in js
    assert "/control/pause" in js
    assert "/control/halt" in js


def test_control_room_supports_multiple_floors_and_add_agent():
    js = (UI / "app.js").read_text()
    assert "/api/floors" in js
    assert "/api/add-agent" in js
    assert "New Floor" in js
    assert "Add Agent" in js


def test_office_floor_visualizes_feedback_states_without_external_assets():
    css = (UI / "app.css").read_text()
    js = (UI / "app.js").read_text()
    for cls in ["state-investigating", "state-experimenting", "state-review", "state-verifying", "state-verified", "state-blocked"]:
        assert cls in css
    assert "https://" not in (UI / "index.html").read_text()
    assert "https://" not in css
    assert "https://" not in js
