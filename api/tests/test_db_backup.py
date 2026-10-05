import importlib.util
import os
import sqlite3
from pathlib import Path

import pytest

script = Path(__file__).resolve().parents[2] / "scripts" / "backup-paperpulse-db.py"
spec = importlib.util.spec_from_file_location("db_backup", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_backup_captures_wal_state_and_prunes_expired_copies(tmp_path):
    source = tmp_path / "source.sqlite"
    directory = tmp_path / "backups"
    directory.mkdir()
    expired = directory / "paperpulse-expired.sqlite"
    expired.touch()
    os.utime(expired, (1, 1))
    with sqlite3.connect(source) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE samples (value TEXT)")
        conn.execute("INSERT INTO samples VALUES ('committed')")
        conn.commit()
        output = module.backup_database(source, directory)
        with sqlite3.connect(output) as restored:
            assert restored.execute("SELECT value FROM samples").fetchall() == [("committed",)]
    assert output.stat().st_mode & 0o777 == 0o600
    assert not expired.exists()
    assert not list(directory.glob("*.part"))
    with pytest.raises(sqlite3.OperationalError):
        module.backup_database(tmp_path / "missing.sqlite", directory)
    assert not (tmp_path / "missing.sqlite").exists()
    assert output.exists()
    assert not list(directory.glob("*.part"))
