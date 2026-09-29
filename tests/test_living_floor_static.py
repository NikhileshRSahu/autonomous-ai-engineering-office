from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
UI=ROOT/'src/engineering_office/ui'

def test_living_floor_uses_local_renderer_not_cdn():
    html=(UI/'index.html').read_text()
    assert '/static/living-floor-renderer.min.js' in html
    assert 'cdn.jsdelivr' not in html and 'unpkg.com' not in html
    assert 'living-floor-canvas' in html
    assert (UI/'vendor/living-floor-renderer.min.js').is_file()

def test_renderer_contains_semantic_engineering_zones_and_characters():
    js=(UI/'vendor/living-floor-renderer.min.js').read_text()
    for token in ['Director','Engineering','Research','Review','Robot Lab','Verification','Model Server','Break']:
        assert token in js
    for token in ['skin','hair','shirt','walk','typing','talk','testing','blocked','verified']:
        assert token in js

def test_canvas_floor_keeps_accessible_roster_fallback():
    html=(UI/'index.html').read_text()
    assert 'agent-roster' in html
    assert 'floor-accessible-summary' in html
