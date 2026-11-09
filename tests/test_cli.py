"""Tests for CLI commands (`doctor`, `db init`, `db status`, `db backup`, `db restore`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from storytelling.cli import main


def test_cli_doctor(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["doctor"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["llm_provider"] == "file"
    assert out["allow_paid_apis"] is False
    assert out["max_concurrent_gpu_jobs"] == 1
    assert out["ffmpeg_available"] is True


def test_cli_db_lifecycle(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_file = tmp_path / "cli_test.db"
    backup_file = tmp_path / "cli_backup.db"
    restored_file = tmp_path / "cli_restored.db"

    assert main(["db", "init", "--db-path", str(db_file)]) == 0
    init_out = json.loads(capsys.readouterr().out)
    assert init_out["required_tables_present"] is True
    assert "001_initial.sql" in init_out["applied_now"]

    assert main(["db", "status", "--db-path", str(db_file)]) == 0
    status_out = json.loads(capsys.readouterr().out)
    assert status_out["exists"] is True
    assert status_out["applied_migrations"] == ["001_initial.sql"]

    assert (
        main(
            [
                "db",
                "backup",
                "--db-path",
                str(db_file),
                "--output",
                str(backup_file),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert backup_file.exists()

    assert (
        main(
            [
                "db",
                "restore",
                "--db-path",
                str(restored_file),
                "--input",
                str(backup_file),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert restored_file.exists()
