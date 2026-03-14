import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lib.claude import setup_settings

MOCK_FORGE_ROOT = Path("/fake/forge")


@pytest.fixture
def work_dir(tmp_path):
    return tmp_path / "work"


def _run_setup(work_dir, user_config=None, phase="", log_dir=None, extra_write_paths=None):
    if user_config is None:
        user_config = {}
    work_dir.mkdir(parents=True, exist_ok=True)
    with patch("lib.claude.load_config", return_value=user_config):
        setup_settings(work_dir, phase=phase, log_dir=log_dir,
                       extra_write_paths=extra_write_paths)
    settings_file = work_dir / ".claude" / "settings.local.json"
    assert settings_file.exists()
    return json.loads(settings_file.read_text())


class TestSetupSettings:
    def test_settings_file_created(self, work_dir):
        _run_setup(work_dir)
        assert (work_dir / ".claude" / "settings.local.json").exists()

    def test_log_dir_in_allow_write(self, work_dir):
        user_config = {"claude": {"sandbox": {"filesystem": {}}}}
        log_dir = Path("/tmp/logs")
        result = _run_setup(work_dir, user_config=user_config, log_dir=log_dir)
        assert "//tmp/logs" in result["sandbox"]["filesystem"]["allowWrite"]

    def test_extra_write_paths(self, work_dir):
        user_config = {"claude": {"sandbox": {"filesystem": {}}}}
        result = _run_setup(work_dir, user_config=user_config,
                            extra_write_paths=["/extra/path"])
        assert "//extra/path/" in result["sandbox"]["filesystem"]["allowWrite"]

    def test_user_allow_write_preserved(self, work_dir):
        user_config = {
            "claude": {
                "sandbox": {
                    "filesystem": {
                        "allowWrite": ["//tmp/custom"],
                    },
                },
            },
        }
        result = _run_setup(work_dir, user_config=user_config, log_dir=Path("/tmp/logs"))
        aw = result["sandbox"]["filesystem"]["allowWrite"]
        assert "//tmp/custom" in aw
        assert "//tmp/logs" in aw

    def test_user_sandbox_passed_through(self, work_dir):
        user_config = {
            "claude": {
                "sandbox": {
                    "enabled": True,
                    "autoAllowBashIfSandboxed": True,
                    "filesystem": {
                        "denyWrite": ["~/.ssh"],
                    },
                },
            },
        }
        result = _run_setup(work_dir, user_config=user_config)
        sb = result["sandbox"]
        assert sb["enabled"] is True
        assert sb["autoAllowBashIfSandboxed"] is True
        assert "~/.ssh" in sb["filesystem"]["denyWrite"]


class TestPermissions:
    def test_default_permissions_no_phase(self, work_dir):
        result = _run_setup(work_dir)
        perms = result["permissions"]
        assert perms["allow"] == ["mcp__linear-server__*"]
        assert perms["deny"] == []

    def test_planning_phase_deny(self, work_dir):
        result = _run_setup(work_dir, phase="planning")
        perms = result["permissions"]
        assert "mcp__linear-server__*" in perms["allow"]
        assert "mcp__linear-server__get_issue" in perms["deny"]
        assert "mcp__linear-server__list_issue_statuses" in perms["deny"]

    def test_implementing_phase_deny(self, work_dir):
        result = _run_setup(work_dir, phase="implementing")
        perms = result["permissions"]
        assert "mcp__linear-server__save_issue" in perms["deny"]

    def test_implementing_phase_with_allowed_tools(self, work_dir):
        user_config = {
            "allowed_tools": {
                "implementing": ["Edit", "Write", "Bash"],
            },
        }
        result = _run_setup(work_dir, user_config=user_config, phase="implementing")
        perms = result["permissions"]
        assert "Edit" in perms["allow"]
        assert "Write" in perms["allow"]
        assert "Bash" in perms["allow"]
        assert "mcp__linear-server__*" in perms["allow"]

    def test_review_phase_deny(self, work_dir):
        result = _run_setup(work_dir, phase="review")
        perms = result["permissions"]
        assert "mcp__linear-server__save_issue" in perms["deny"]
        assert "mcp__linear-server__get_issue" in perms["deny"]
        assert "mcp__linear-server__list_documents" in perms["deny"]

    def test_unknown_phase_no_deny(self, work_dir):
        result = _run_setup(work_dir, phase="unknown")
        perms = result["permissions"]
        assert perms["deny"] == []
