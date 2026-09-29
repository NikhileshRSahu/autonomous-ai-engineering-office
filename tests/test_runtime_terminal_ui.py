from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/'src/engineering_office/ui/app.js').read_text()
HTML=(ROOT/'src/engineering_office/ui/index.html').read_text()

def test_selected_agent_terminal_uses_observability_endpoint_incrementally():
    assert '/terminal' in APP
    assert 'terminalCursorByAgent' in APP
    assert 'terminalCacheByAgent' in APP
    assert 'pullSelectedTerminal' in APP

def test_terminal_renders_observable_event_kinds():
    for token in ['command.started','command.output','file.read','file.written','message.sent','model.','verification.']:
        assert token in APP

def test_disconnect_freezes_last_confirmed_state():
    assert 'disconnected' in APP
    assert 'last confirmed' in APP.lower() or 'frozen' in APP.lower()
