#!/usr/bin/env python3
"""Create an integrity-checked SQLite backup and retain seven days of copies."""
import argparse
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def backup_database(source, directory):
    """Back up committed state before replacing the completed backup file.

    Args:
        source: Existing SQLite database path.
        directory: Private directory for completed backups.

    Returns:
        Path to the new backup.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)
    now = datetime.now(timezone.utc)
    destination = directory / f"paperpulse-{now.strftime('%Y%m%dT%H%M%S%fZ')}.sqlite"
    fd, name = tempfile.mkstemp(prefix=".paperpulse-", suffix=".part", dir=directory)
    os.close(fd)
    temporary = Path(name)
    try:
        original = sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)
        copy = sqlite3.connect(temporary)
        try:
            original.backup(copy)
            if copy.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise RuntimeError("SQLite backup integrity check failed")
            if copy.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError("SQLite backup foreign key check failed")
        finally:
            copy.close()
            original.close()
        temporary.replace(destination)
        cutoff = now.timestamp() - 7 * 24 * 60 * 60
        for old in directory.glob("paperpulse-*.sqlite"):
            if old.stat().st_mtime < cutoff:
                old.unlink()
        return destination
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/var/lib/paperpulse/db/paperpulse.sqlite")
    parser.add_argument("--directory", default="/var/lib/paperpulse/backups")
    args = parser.parse_args()
    print(backup_database(args.source, args.directory))
