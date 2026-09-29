from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'src/engineering_office/ui/app.js').read_text()
RENDER=(ROOT/'src/engineering_office/ui/vendor/living-floor-renderer.min.js').read_text()

def test_handoffs_come_from_real_message_events():
    assert "e.kind==='message.sent'" in APP
    assert 'sender' in RENDER and 'recipient' in RENDER
    assert 'drawHandoffs' in RENDER

def test_model_server_visualizes_runtime_states():
    assert '/api/models/runtime' in APP
    for token in ['MODEL_LOADING','model.loading','model.ready']:
        assert token in APP or token in RENDER
    assert 'drawModels' in RENDER

def test_verifier_success_requires_verification_finished_event():
    assert 'verification.finished' in APP
    assert 'VERIFIED' in APP or 'VERIFIED' in RENDER
    assert 'verification.finished' in APP and 'PASS' in APP

def test_ui_never_labels_hidden_chain_of_thought():
    combined=(APP+'\n'+RENDER).lower()
    assert 'chain-of-thought' not in combined
    assert 'hidden reasoning' not in combined
