"""Persist a small, local research context, without chat history or credentials."""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3


ROLES = ('x', 'y', 'controls', 'mediators', 'moderators', 'instruments')
REPORTS = ('fixed_effects_report', 'did_report', 'statistics_report', 'mediation_report', 'event_study_report', 'combined_regression')


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def checked_dataset_path(root, value):
    if not isinstance(value, str) or not value:
        return None
    root = Path(root).resolve()
    path = Path(value).resolve()
    if not path.is_relative_to(root):
        return None
    if not any(path.is_relative_to((root / name).resolve()) for name in ('runs', 'datasets')):
        return None
    return path if path.is_file() and path.suffix.lower() in ('.dta', '.csv', '.xlsx') else None


def capture(root, workspace):
    """Capture only verified model records and dataset roles, never credentials."""
    dataset = workspace.get('dataset') or {}
    path = checked_dataset_path(root, workspace.get('path')) if workspace.get('loaded') else None
    safe_to_reload = bool(path and not dataset.get('memory_only'))
    state = {
        'version': 1,
        'dataset': {'path': str(path) if safe_to_reload else None,
                    'filename': dataset.get('filename'),
                    'sha256': file_digest(path) if safe_to_reload else None,
                    'revision': workspace.get('dataset_revision'),
                    'memory_only': bool(workspace.get('loaded') and not safe_to_reload)},
        'research_variables': {role: [v for v in (workspace.get('research_variables') or {}).get(role, [])
                                      if isinstance(v, str)][:100] for role in ROLES},
        'confirmed_model': workspace.get('confirmed_model'),
        'models': [],
        'artifacts': [a for a in workspace.get('artifacts', [])
                      if isinstance(a, dict) and isinstance(a.get('name'), str)
                      and isinstance(a.get('url'), str) and a['url'].startswith('/api/artifacts/')][:10000],
    }
    for event in workspace.get('events', []):
        if event.get('error') or not any(isinstance(event.get(key), dict) for key in REPORTS):
            continue
        state['models'].append({key: event[key] for key in
            ('tool', 'label', 'error', 'dataset_revision', 'readable_code', 'readable_url', *REPORTS) if key in event})
    return state


def _connect(db):
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db, timeout=5)
    connection.execute('CREATE TABLE IF NOT EXISTS research_state (id INTEGER PRIMARY KEY CHECK(id = 1), payload TEXT NOT NULL)')
    return connection


def save(db, state):
    payload = json.dumps(state, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    with closing(_connect(db)) as conn, conn:
        conn.execute('INSERT INTO research_state(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (payload,))


def load(db):
    if not Path(db).is_file():
        return None
    with closing(_connect(db)) as conn:
        row = conn.execute('SELECT payload FROM research_state WHERE id=1').fetchone()
    if not row:
        return None
    state = json.loads(row[0])
    if not isinstance(state, dict) or state.get('version') != 1:
        raise ValueError('不支持的研究上下文版本。')
    return state


def clear(db):
    if Path(db).is_file():
        with closing(_connect(db)) as conn, conn:
            conn.execute('DELETE FROM research_state WHERE id=1')
