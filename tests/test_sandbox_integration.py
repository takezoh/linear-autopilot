import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from forge.claude import run


@pytest.fixture
def work_dir():
    d = Path("/tmp/claude-1000") / f"test-{uuid.uuid4().hex[:8]}" / "work"
    d.mkdir(parents=True)
    # subprocess.run(["git", "init"], cwd=d, capture_output=True, check=True)
    # subprocess.run(
    #     ["git", "config", "user.email", "test@test.com"],
    #     cwd=d, capture_output=True, check=True,
    # )
    # subprocess.run(
    #     ["git", "config", "user.name", "Test"],
    #     cwd=d, capture_output=True, check=True,
    # )
    yield d
    shutil.rmtree(d.parent, ignore_errors=True)


def _run_claude(prompt, work_dir, extra_write_paths=None,
                disallowed_tools=None):
    print(f"work_dir: {work_dir}")
    ret = run(
        prompt, work_dir,
        model="haiku",
        max_turns="5",
        budget="0.15",
        capture_output=True,
        allow_write=extra_write_paths,
        disallowed_tools=disallowed_tools,
    )

    claude_settings_path = work_dir / ".claude" / "settings.local.json"
    with open(claude_settings_path) as f:
        settings = json.load(f)
        print(f"claude settings: {json.dumps(settings, indent=2)}")
    result = json.loads(ret.stdout)
    print(f"result: {json.dumps(result, indent=2)}")
    return ret, result


@pytest.mark.integration
class TestSandboxRead:
    def test_read_allowed(self, work_dir):
        target = work_dir / "readable.txt"
        target.write_text("hello sandbox")
        ret, result = _run_claude(
            f"Read the file at {target} and tell me its contents. Be brief.",
            work_dir,
        )
        assert ret.returncode == 0
        assert result["is_error"] is False
        assert result["subtype"] == "success"
        assert "hello sandbox" in result["result"]

    def test_read_denied(self, work_dir, tmp_path):
        secret_dir = tmp_path / ".ssh"
        secret_dir.mkdir()
        secret_file = secret_dir / "id_rsa"
        secret_file.write_text("SECRET_KEY_DATA")
        ret, result = _run_claude(
            f"Read the file at {secret_file}. Be brief.",
            work_dir,
        )
        assert "SECRET_KEY_DATA" not in result.get("result", "")


@pytest.mark.integration
class TestSandboxWrite:
    def test_write_allowed(self, work_dir):
        target = work_dir / "output.txt"
        ret, result = _run_claude(
            f"Only use the Bash tool. Run this bash command: echo -n 'write_success' > {target}",
            work_dir,
            extra_write_paths=[str(work_dir)],
            disallowed_tools=["Write", "Edit",
                              "mcp__filesystem__write_file",
                              "mcp__filesystem__edit_file"],
        )
        assert ret.returncode == 0
        assert result["is_error"] is False
        assert target.exists()
        assert "write_success" in target.read_text()

    def test_write_denied(self, work_dir, tmp_path):
        denied_dir = tmp_path / "denied_output"
        denied_dir.mkdir()
        target = denied_dir / "output.txt"
        ret, result = _run_claude(
            f"Only use the Bash tool. Run this bash command: echo -n 'write_fail' > {target}",
            work_dir,
            disallowed_tools=["Write", "Edit",
                              "mcp__filesystem__write_file",
                              "mcp__filesystem__edit_file"],
        )
        assert not target.exists() or "write_fail" not in target.read_text()
