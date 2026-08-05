"""The commands a reader of the README will actually type."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from jsonschema import Draft202012Validator

from cassette.cli.main import main

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "trace.schema.json"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema: Any = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


@pytest.fixture
def cli() -> CliRunner:
    return CliRunner()


def test_help_lists_the_commands(cli: CliRunner) -> None:
    result = cli.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "export" in result.output


def test_version_is_reported(cli: CliRunner) -> None:
    result = cli.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "cassette" in result.output


def test_run_reports_the_seed_and_the_cluster(cli: CliRunner) -> None:
    result = cli.invoke(main, ["run", "--seed", "8421"])
    assert result.exit_code == 0
    assert "8421" in result.output
    assert "5 replicas" in result.output


def test_run_is_reproducible(cli: CliRunner) -> None:
    first = cli.invoke(main, ["run", "--seed", "8421", "--json"])
    second = cli.invoke(main, ["run", "--seed", "8421", "--json"])
    assert first.output == second.output


def test_run_json_validates_against_the_schema(
    cli: CliRunner, validator: Draft202012Validator
) -> None:
    result = cli.invoke(main, ["run", "--seed", "8421", "--json"])
    validator.validate(json.loads(result.output))


def test_a_seed_is_required(cli: CliRunner) -> None:
    assert cli.invoke(main, ["run"]).exit_code != 0


def test_the_preset_changes_the_faults(cli: CliRunner) -> None:
    quiet = cli.invoke(main, ["run", "--seed", "1", "--preset", "quiet"])
    harsh = cli.invoke(main, ["run", "--seed", "1", "--preset", "harsh"])
    assert "drop" not in quiet.output
    assert "drop 0.1" in harsh.output


def test_individual_faults_override_the_preset(cli: CliRunner) -> None:
    result = cli.invoke(main, ["run", "--seed", "1", "--preset", "quiet", "--drop-rate", "0.25"])
    assert "drop 0.25" in result.output


def test_a_weak_quorum_is_flagged(cli: CliRunner) -> None:
    result = cli.invoke(
        main, ["run", "--seed", "1", "--nodes", "5", "--read-quorum", "2", "--write-quorum", "2"]
    )
    assert "R+W" in result.output


def test_export_writes_a_trace(cli: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "traces" / "8421.json"
    result = cli.invoke(main, ["export", "--seed", "8421", "-o", str(target)])
    assert result.exit_code == 0
    assert target.is_file()
    assert "wrote" in result.output


def test_an_exported_trace_validates(
    cli: CliRunner, tmp_path: Path, validator: Draft202012Validator
) -> None:
    target = tmp_path / "8421.json"
    cli.invoke(main, ["export", "--seed", "8421", "-o", str(target)])
    validator.validate(json.loads(target.read_text(encoding="utf-8")))


def test_an_exported_trace_matches_the_json_output(cli: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "8421.json"
    cli.invoke(main, ["export", "--seed", "8421", "-o", str(target)])
    streamed = cli.invoke(main, ["run", "--seed", "8421", "--json"]).output
    assert json.loads(target.read_text(encoding="utf-8")) == json.loads(streamed)
