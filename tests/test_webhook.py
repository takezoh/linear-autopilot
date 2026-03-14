import hashlib
import hmac as hmac_mod
import json
import os
import signal as sig_mod
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, ANY

import pytest

from forge.webhook import (
    _verify_signature, _extract_issue_from_context, _process_event,
    _handle_created, _handle_prompted, _handle_stop,
    _processes, _processes_lock, app, STATE_TO_PHASE,
)
from forge.constants import (
    STATE_PLANNING, STATE_IMPLEMENTING,
    STATE_PLAN_CHANGES_REQUESTED, STATE_CHANGES_REQUESTED,
    PHASE_PLANNING, PHASE_IMPLEMENTING, PHASE_PLAN_REVIEW, PHASE_REVIEW,
)

SID = "sess-1"
KEY = "test-key"
ISSUE_ID = "issue-abc"


def _make_payload(action="created", session_id=SID, prompt_context="", body=""):
    p = {
        "type": "AgentSessionEvent",
        "action": action,
        "agentSession": {"id": session_id, "promptContext": prompt_context},
    }
    if body:
        p["agentActivity"] = {"body": body}
    return p


@pytest.fixture(autouse=True)
def _clean_processes():
    yield
    with _processes_lock:
        _processes.clear()


# --- _verify_signature ---

class TestVerifySignature:
    def test_valid(self):
        body = b"hello"
        secret = "mysecret"
        sig = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_signature(body, sig, secret) is True

    def test_invalid(self):
        assert _verify_signature(b"hello", "badsig", "mysecret") is False

    def test_empty_body(self):
        body = b""
        secret = "s"
        sig = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert _verify_signature(body, sig, secret) is True


# --- _extract_issue_from_context ---

class TestExtractIssue:
    def test_both(self):
        ctx = "<identifier>DEV-1</identifier><id>id1</id>"
        assert _extract_issue_from_context(ctx) == ("DEV-1", "id1")

    def test_id_only(self):
        ctx = "<id>id1</id>"
        assert _extract_issue_from_context(ctx) == ("", "id1")

    def test_identifier_only(self):
        ctx = "<identifier>DEV-1</identifier>"
        assert _extract_issue_from_context(ctx) == ("DEV-1", "")

    def test_empty(self):
        assert _extract_issue_from_context("") == ("", "")


# --- _process_event routing ---

class TestProcessEvent:
    def test_non_agent_event_ignored(self):
        with patch("forge.webhook._handle_created") as hc:
            _process_event({"type": "Other", "action": "created"}, {})
            hc.assert_not_called()

    @pytest.mark.parametrize("action,handler", [
        ("created", "_handle_created"),
        ("prompted", "_handle_prompted"),
        ("stop", "_handle_stop"),
    ])
    def test_routes(self, action, handler):
        payload = _make_payload(action=action)
        with patch(f"forge.webhook.{handler}") as h:
            _process_event(payload, {"k": "v"})
            h.assert_called_once_with(payload, {"k": "v"})

    def test_unknown_action_no_error(self):
        _process_event(_make_payload(action="unknown"), {})

    @patch("forge.webhook.emit_error")
    @patch("forge.webhook._handle_created", side_effect=RuntimeError("boom"))
    def test_handler_exception_emits_error(self, _, mock_err):
        _process_event(_make_payload(action="created"), {"LINEAR_OAUTH_TOKEN": KEY})
        mock_err.assert_called_once()
        assert "boom" in mock_err.call_args[0][1]


# --- _handle_created ---

class TestHandleCreated:
    def _env(self, tmp_path):
        return {
            "LINEAR_OAUTH_TOKEN": KEY,
            "FORGE_LOCK_DIR": str(tmp_path / "locks"),
        }

    def _ctx(self, identifier="DEV-1", issue_id=ISSUE_ID):
        parts = []
        if identifier:
            parts.append(f"<identifier>{identifier}</identifier>")
        if issue_id:
            parts.append(f"<id>{issue_id}</id>")
        return "".join(parts)

    def _patches(self, **overrides):
        defaults = {
            "forge.webhook.fetch_issue_detail": {"identifier": "DEV-1", "labels": []},
            "forge.webhook.fetch_issue_state": STATE_PLANNING,
            "forge.webhook.load_repos": {},
            "forge.webhook.resolve_repo": None,
            "forge.webhook.emit_thought": None,
        }
        defaults.update(overrides)
        import contextlib
        patches = []
        for target, rv in defaults.items():
            patches.append(patch(target, return_value=rv))
        return contextlib.ExitStack(), patches

    def _run(self, tmp_path, prompt_context=None, extra_patches=None, **overrides):
        if prompt_context is None:
            prompt_context = self._ctx()
        env = self._env(tmp_path)
        payload = _make_payload(prompt_context=prompt_context)
        stack, patches = self._patches(**overrides)
        if extra_patches:
            patches.extend(extra_patches)
        mocks = {}
        with stack:
            for p in patches:
                m = stack.enter_context(p)
                mocks[p.attribute] = m
            _handle_created(payload, env)
        return mocks, env

    def test_no_issue_id(self, tmp_path):
        mocks, _ = self._run(tmp_path, prompt_context="<identifier>DEV-1</identifier>")
        mock_thought = mocks["emit_thought"]
        mock_thought.assert_called_once()
        assert "issue ID" in mock_thought.call_args[0][1]

    def test_resolve_repo_none(self, tmp_path):
        mocks, _ = self._run(tmp_path)
        calls = [c[0][1] for c in mocks["emit_thought"].call_args_list]
        assert any("no repo" in c.lower() for c in calls)

    def test_repo_path_not_exists(self, tmp_path):
        mocks, _ = self._run(tmp_path, **{"forge.webhook.resolve_repo": "/nonexistent/path"})
        calls = [c[0][1] for c in mocks["emit_thought"].call_args_list]
        assert any("not found" in c.lower() for c in calls)

    def test_lock_exists(self, tmp_path):
        env = self._env(tmp_path)
        lock_dir = Path(env["FORGE_LOCK_DIR"])
        lock_dir.mkdir(parents=True, exist_ok=True)
        (lock_dir / f"{ISSUE_ID}.lock").write_text("x")
        mocks, _ = self._run(tmp_path, **{"forge.webhook.resolve_repo": str(tmp_path)})
        calls = [c[0][1] for c in mocks["emit_thought"].call_args_list]
        assert any("already being processed" in c for c in calls)

    def test_normal_path(self, tmp_path):
        mock_proc = MagicMock()
        mock_proc.wait.return_value = 0
        mock_popen = MagicMock(return_value=mock_proc)
        mocks, env = self._run(
            tmp_path,
            extra_patches=[patch("forge.webhook.subprocess.Popen", mock_popen)],
            **{
                "forge.webhook.resolve_repo": str(tmp_path),
                "forge.webhook.fetch_issue_state": STATE_IMPLEMENTING,
            },
        )
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "forge.executor" in " ".join(cmd)
        assert PHASE_IMPLEMENTING in cmd
        popen_env = mock_popen.call_args[1]["env"]
        assert popen_env["FORGE_SESSION_ID"] == SID
        lock_file = Path(env["FORGE_LOCK_DIR"]) / f"{ISSUE_ID}.lock"
        assert lock_file.exists()

    def test_popen_exception(self, tmp_path):
        mock_err = MagicMock()
        mocks, env = self._run(
            tmp_path,
            extra_patches=[
                patch("forge.webhook.subprocess.Popen", side_effect=OSError("fail")),
                patch("forge.webhook.emit_error", mock_err),
            ],
            **{"forge.webhook.resolve_repo": str(tmp_path)},
        )
        mock_err.assert_called_once()
        lock_file = Path(env["FORGE_LOCK_DIR"]) / f"{ISSUE_ID}.lock"
        assert not lock_file.exists()


class TestStateToPhase:
    @pytest.mark.parametrize("state,phase", [
        (STATE_PLANNING, PHASE_PLANNING),
        (STATE_IMPLEMENTING, PHASE_IMPLEMENTING),
        (STATE_PLAN_CHANGES_REQUESTED, PHASE_PLAN_REVIEW),
        (STATE_CHANGES_REQUESTED, PHASE_REVIEW),
    ])
    def test_mapping(self, state, phase):
        assert STATE_TO_PHASE[state] == phase

    def test_unknown_state_default(self):
        assert STATE_TO_PHASE.get("Unknown") is None


# --- _handle_prompted ---

class TestHandlePrompted:
    @patch("forge.webhook.emit_thought")
    def test_emits_thought_with_body(self, mock_thought):
        payload = _make_payload(action="prompted", body="user msg")
        _handle_prompted(payload, {"LINEAR_OAUTH_TOKEN": KEY})
        mock_thought.assert_called_once()
        assert "user msg" in mock_thought.call_args[0][1]


# --- _handle_stop ---

class TestHandleStop:
    @patch("forge.webhook.emit_response")
    def test_running_process(self, mock_resp):
        proc = MagicMock()
        proc.poll.return_value = None
        with _processes_lock:
            _processes[SID] = proc
        _handle_stop(_make_payload(action="stop"), {"LINEAR_OAUTH_TOKEN": KEY})
        proc.send_signal.assert_called_once_with(sig_mod.SIGTERM)
        mock_resp.assert_called_once()

    @patch("forge.webhook.emit_response")
    def test_no_process(self, mock_resp):
        _handle_stop(_make_payload(action="stop"), {"LINEAR_OAUTH_TOKEN": KEY})
        mock_resp.assert_called_once()

    @patch("forge.webhook.emit_response")
    def test_already_exited(self, mock_resp):
        proc = MagicMock()
        proc.poll.return_value = 0
        with _processes_lock:
            _processes[SID] = proc
        _handle_stop(_make_payload(action="stop"), {"LINEAR_OAUTH_TOKEN": KEY})
        proc.send_signal.assert_not_called()
        mock_resp.assert_called_once()


# --- Flask endpoint ---

class TestWebhookEndpoint:
    @pytest.fixture
    def client(self):
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c

    @patch("forge.webhook._process_event")
    def test_valid_post(self, _, client):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LINEAR_WEBHOOK_SECRET", None)
            resp = client.post("/webhook", json={"type": "test"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_invalid_signature_401(self, client):
        secret = "webhook-secret"
        with patch.dict(os.environ, {"LINEAR_WEBHOOK_SECRET": secret}):
            resp = client.post("/webhook", data=b'{"a":1}',
                               headers={"Linear-Signature": "bad"},
                               content_type="application/json")
        assert resp.status_code == 401

    @patch("forge.webhook._process_event")
    def test_valid_signature_200(self, _, client):
        secret = "webhook-secret"
        body = b'{"type":"AgentSessionEvent"}'
        sig = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        with patch.dict(os.environ, {"LINEAR_WEBHOOK_SECRET": secret}):
            resp = client.post("/webhook", data=body,
                               headers={"Linear-Signature": sig},
                               content_type="application/json")
        assert resp.status_code == 200

    @patch("forge.webhook._process_event")
    def test_no_secret_skips_verification(self, _, client):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LINEAR_WEBHOOK_SECRET", None)
            resp = client.post("/webhook", json={"type": "test"})
        assert resp.status_code == 200
