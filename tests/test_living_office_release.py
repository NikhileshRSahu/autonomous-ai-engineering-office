from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_local_renderer_is_packaged_and_no_cdn_runtime_reference():
    py=(ROOT/'pyproject.toml').read_text()
    assert 'ui/vendor/*' in py
    ui='\n'.join(p.read_text(errors='ignore') for p in (ROOT/'src/engineering_office/ui').rglob('*') if p.is_file())
    assert 'cdn.jsdelivr.net' not in ui and 'unpkg.com' not in ui
    assert (ROOT/'src/engineering_office/ui/vendor/living-floor-renderer.min.js').is_file()

def test_observability_docs_and_production_screenshot_exist():
    assert (ROOT/'docs/RUNTIME_OBSERVABILITY.md').is_file()
    assert (ROOT/'docs/assets/living-office-control-room.png').is_file()
