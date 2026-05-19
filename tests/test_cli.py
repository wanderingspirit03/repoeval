from typer.testing import CliRunner

from repoeval.cli import app


def test_init_creates_config(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".repoeval" / "tasks.yaml").read_text() == "tasks: []\n"
