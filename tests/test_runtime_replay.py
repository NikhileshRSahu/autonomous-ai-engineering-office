from __future__ import annotations
from pathlib import Path
from engineering_office.runtime_events import emit_runtime_event
from engineering_office.ui_service import DashboardService


def _service(root: Path):
    (root/'README.md').write_text('demo')
    svc=DashboardService(root, floor_registry_path=root/'floors.json')
    svc.start('inspect')
    return svc


def test_replay_is_bounded_by_timestamp_and_read_only(tmp_path: Path):
    svc=_service(tmp_path); pid=svc.engine._load_project().project_id
    emit_runtime_event(svc.engine.runtime_events, project_id=pid, agent_id='A', kind='file.read', summary='one', timestamp='2026-09-28T10:00:00+00:00')
    emit_runtime_event(svc.engine.runtime_events, project_id=pid, agent_id='A', kind='file.written', summary='two', timestamp='2026-09-28T10:01:00+00:00')
    emit_runtime_event(svc.engine.runtime_events, project_id=pid, agent_id='A', kind='test.started', summary='three', timestamp='2026-09-28T10:02:00+00:00')
    before=svc.snapshot()['status']
    replay=svc.replay_events('2026-09-28T10:00:30+00:00','2026-09-28T10:01:30+00:00')
    after=svc.snapshot()['status']
    assert [e['summary'] for e in replay['events']] == ['two']
    assert before == after


def test_replay_skips_malformed_rows_with_diagnostics(tmp_path: Path):
    svc=_service(tmp_path)
    with svc.engine.runtime_events.path.open('a') as f: f.write('{bad\n')
    replay=svc.replay_events(None,None)
    assert replay['diagnostics']
    assert all('id' in e for e in replay['events'])
