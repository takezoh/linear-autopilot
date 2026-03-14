import os
from unittest.mock import patch

from forge.config import get_api_key


class TestGetApiKey:
    def test_env_dict_oauth_over_api_key(self):
        env = {"LINEAR_OAUTH_TOKEN": "oauth", "LINEAR_API_KEY": "apikey"}
        assert get_api_key(env) == "oauth"

    def test_env_dict_api_key_only(self):
        env = {"LINEAR_API_KEY": "apikey"}
        assert get_api_key(env) == "apikey"

    @patch.dict(os.environ, {"LINEAR_OAUTH_TOKEN": "env-oauth"}, clear=True)
    def test_empty_env_falls_back_to_os_oauth(self):
        assert get_api_key({}) == "env-oauth"

    @patch.dict(os.environ, {"LINEAR_API_KEY": "env-key"}, clear=True)
    def test_empty_env_falls_back_to_os_api_key(self):
        assert get_api_key({}) == "env-key"

    @patch.dict(os.environ, {"LINEAR_OAUTH_TOKEN": "env-oauth", "LINEAR_API_KEY": "env-key"}, clear=True)
    def test_os_environ_oauth_priority(self):
        assert get_api_key({}) == "env-oauth"

    @patch.dict(os.environ, {"LINEAR_OAUTH_TOKEN": "env-oauth"}, clear=True)
    def test_none_env_reads_os(self):
        assert get_api_key(None) == "env-oauth"

    @patch.dict(os.environ, {}, clear=True)
    def test_nothing_returns_empty(self):
        assert get_api_key({}) == ""

    def test_oauth_empty_string_falls_back(self):
        env = {"LINEAR_OAUTH_TOKEN": "", "LINEAR_API_KEY": "apikey"}
        assert get_api_key(env) == "apikey"
