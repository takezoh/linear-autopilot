from unittest.mock import patch, call

from forge.agent_api import (
    emit_activity, emit_thought, emit_action, emit_response, emit_error,
    emit_elicitation, update_session_plan, update_session_external_urls,
    AGENT_ACTIVITY_CREATE, AGENT_SESSION_UPDATE,
)

SID = "session-1"
KEY = "test-key"


@patch("forge.agent_api.graphql")
class TestEmitActivity:
    def test_minimal(self, mock_gql):
        emit_activity(SID, {"type": "thought", "body": "hi"}, KEY)
        args = mock_gql.call_args
        input_dict = args[0][2]["input"]
        assert input_dict["agentSessionId"] == SID
        assert input_dict["content"] == {"type": "thought", "body": "hi"}
        assert "signal" not in input_dict
        assert "signalMetadata" not in input_dict
        assert "ephemeral" not in input_dict

    def test_signal(self, mock_gql):
        emit_activity(SID, {"type": "thought", "body": "x"}, KEY, signal="stop")
        input_dict = mock_gql.call_args[0][2]["input"]
        assert input_dict["signal"] == "stop"

    def test_signal_metadata(self, mock_gql):
        meta = {"key": "val"}
        emit_activity(SID, {"type": "thought", "body": "x"}, KEY,
                       signal="auth", signal_metadata=meta)
        input_dict = mock_gql.call_args[0][2]["input"]
        assert input_dict["signalMetadata"] == meta

    def test_ephemeral_true(self, mock_gql):
        emit_activity(SID, {"type": "thought", "body": "x"}, KEY, ephemeral=True)
        input_dict = mock_gql.call_args[0][2]["input"]
        assert input_dict["ephemeral"] is True

    def test_ephemeral_false_default(self, mock_gql):
        emit_activity(SID, {"type": "thought", "body": "x"}, KEY)
        input_dict = mock_gql.call_args[0][2]["input"]
        assert "ephemeral" not in input_dict


@patch("forge.agent_api.graphql")
class TestEmitHelpers:
    def test_emit_thought(self, mock_gql):
        emit_thought(SID, "thinking", KEY)
        content = mock_gql.call_args[0][2]["input"]["content"]
        assert content == {"type": "thought", "body": "thinking"}

    def test_emit_action_no_result(self, mock_gql):
        emit_action(SID, "run", "ls", KEY)
        content = mock_gql.call_args[0][2]["input"]["content"]
        assert content == {"type": "action", "action": "run", "parameter": "ls"}
        assert "result" not in content

    def test_emit_action_with_result(self, mock_gql):
        emit_action(SID, "run", "ls", KEY, result="ok")
        content = mock_gql.call_args[0][2]["input"]["content"]
        assert content["result"] == "ok"

    def test_emit_response(self, mock_gql):
        emit_response(SID, "done", KEY)
        content = mock_gql.call_args[0][2]["input"]["content"]
        assert content == {"type": "response", "body": "done"}

    def test_emit_error(self, mock_gql):
        emit_error(SID, "fail", KEY)
        content = mock_gql.call_args[0][2]["input"]["content"]
        assert content == {"type": "error", "body": "fail"}

    def test_emit_elicitation_no_signal(self, mock_gql):
        emit_elicitation(SID, "question?", KEY)
        input_dict = mock_gql.call_args[0][2]["input"]
        assert input_dict["content"] == {"type": "elicitation", "body": "question?"}
        assert "signal" not in input_dict

    def test_emit_elicitation_with_signal(self, mock_gql):
        emit_elicitation(SID, "pick", KEY, signal="select",
                         signal_metadata={"options": ["a"]})
        input_dict = mock_gql.call_args[0][2]["input"]
        assert input_dict["signal"] == "select"
        assert input_dict["signalMetadata"] == {"options": ["a"]}


@patch("forge.agent_api.graphql")
class TestSessionUpdate:
    def test_update_plan(self, mock_gql):
        steps = [{"title": "step1"}]
        update_session_plan(SID, steps, KEY)
        mock_gql.assert_called_once_with(
            KEY, AGENT_SESSION_UPDATE,
            {"id": SID, "input": {"plan": steps}},
        )

    def test_update_external_urls(self, mock_gql):
        urls = [{"url": "https://example.com", "label": "PR"}]
        update_session_external_urls(SID, urls, KEY)
        mock_gql.assert_called_once_with(
            KEY, AGENT_SESSION_UPDATE,
            {"id": SID, "input": {"externalUrls": urls}},
        )
