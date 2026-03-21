from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PhaseConfig(BaseModel):
    model: str = ""
    budget: Decimal = Decimal("3.00")
    max_turns: int = 30
    timeout: int = 1800
    idle_timeout: int = 180


class WebhookConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 3000


def _parse_env_file(path: Path) -> dict[str, str]:
    result = {}
    if not path.exists():
        return result
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        result[key.strip()] = value
    return result


def _load_settings_json(path: Path) -> dict:
    if not path.exists():
        return {}
    import json
    return json.loads(path.read_text())


def _load_repos_conf(path: Path) -> dict[str, Path]:
    repos = {}
    if not path.exists():
        return repos
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        label, repo_path = line.split("=", 1)
        repos[label.strip()] = Path(repo_path.strip())
    return repos


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LOKI_",
        extra="ignore",
    )

    linear_team: str = ""
    linear_oauth_token: SecretStr = SecretStr("")
    linear_webhook_secret: SecretStr = SecretStr("")

    default_model: str = "sonnet"
    max_concurrent: int = 3
    max_retries: int = 2
    poll_interval: int = 300

    log_dir: Path = Path("logs")
    worktree_dir: Path = Path("worktrees")
    db_path: Path = Path("loki2.db")

    config_dir: Path = Path("config")
    repos: dict[str, Path] = {}
    phases: dict[str, PhaseConfig] = {}
    webhook: WebhookConfig | None = None

    def model_post_init(self, __context):
        # Load v1 settings.json for fallback values
        v1_settings = _load_settings_json(self.config_dir / "settings.json")
        if not self.linear_team and v1_settings.get("team"):
            self.linear_team = v1_settings["team"]

        # Load v1 secrets.env for fallback token
        secrets_path = self.config_dir / "secrets.env"
        if secrets_path.exists():
            secrets = _parse_env_file(secrets_path)
            if not self.linear_oauth_token.get_secret_value() and secrets.get("LINEAR_OAUTH_TOKEN"):
                self.linear_oauth_token = SecretStr(secrets["LINEAR_OAUTH_TOKEN"])
            if not self.linear_webhook_secret.get_secret_value() and secrets.get("LINEAR_WEBHOOK_SECRET"):
                self.linear_webhook_secret = SecretStr(secrets["LINEAR_WEBHOOK_SECRET"])

        if not self.linear_team:
            raise ValueError("linear_team is required (set LOKI_LINEAR_TEAM or config/settings.json 'team')")
        if not self.linear_oauth_token.get_secret_value():
            raise ValueError("linear_oauth_token is required (set LOKI_LINEAR_OAUTH_TOKEN or config/secrets.env)")

        if not self.repos:
            self.repos = _load_repos_conf(self.config_dir / "repos.conf")

    def phase_config(self, phase: str) -> PhaseConfig:
        return self.phases.get(phase, PhaseConfig())

    def model_for_phase(self, phase: str) -> str:
        pc = self.phase_config(phase)
        return pc.model or self.default_model
