import json
import os
import subprocess
from pathlib import Path

from .config import FORGE_ROOT
from .constants import (PHASE_PLANNING, PHASE_IMPLEMENTING,
                        PHASE_PLAN_REVIEW, PHASE_REVIEW)
from .git import detect_default_branch, diff_stat
from .linear import fetch_issue_detail, fetch_sub_issues

SANDBOX_SETTINGS = {
    "sandbox": {
        "enabled": True,
        "autoAllowBashIfSandboxed": True,
        "allowUnsandboxedCommands": False,
        "filesystem": {
            "denyRead": ["~/.ssh", "~/.aws", "~/.gnupg"],
            "denyWrite": ["~/.ssh", "~/.aws", "~/.gnupg", "~/.bashrc", "~/.zshrc"],
        },
        "network": {
            "allowManagedDomainsOnly": True,
            "allowedDomains": [
                "api.linear.app",
                "github.com",
                "*.github.com",
                "*.githubusercontent.com",
                "api.anthropic.com",
            ],
        },
    },
    "permissions": {
        "deny": [
            "Bash(rm -rf /)",
            "Bash(git push * --force *)",
            "Bash(git push * -f *)",
        ],
    },
}

DISALLOWED_TOOLS_MAP = {
    PHASE_PLANNING: [
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_issue_statuses",
    ],
    PHASE_IMPLEMENTING: [
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_documents",
        "mcp__linear-server__list_comments",
        "mcp__linear-server__save_issue",
    ],
    PHASE_PLAN_REVIEW: [
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_issue_statuses",
    ],
    PHASE_REVIEW: [
        "mcp__linear-server__save_issue",
        "mcp__linear-server__get_issue",
        "mcp__linear-server__list_documents",
    ],
}


def setup_sandbox(work_dir: Path, log_dir: Path, extra_write_paths: list[str] | None = None):
    settings = json.loads(json.dumps(SANDBOX_SETTINGS))
    allow_write = [str(log_dir)]
    if extra_write_paths:
        allow_write.extend(extra_write_paths)
    settings["sandbox"]["filesystem"]["allowWrite"] = allow_write

    claude_dir = work_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    settings_file = claude_dir / "settings.local.json"
    settings_file.write_text(json.dumps(settings, indent=2))


def run(prompt: str, work_dir: Path, log_dir: Path, log_file: Path,
        env: dict, phase: str, extra_write_paths: list[str] | None = None):
    setup_sandbox(work_dir, log_dir, extra_write_paths=extra_write_paths)

    model_key = f"FORGE_MODEL_{phase.upper()}"
    model = env.get(model_key, env["FORGE_MODEL"])
    budget_key = f"FORGE_BUDGET_{phase.upper()}"
    turns_key = f"FORGE_MAX_TURNS_{phase.upper()}"
    budget = env.get(budget_key, "1.00")
    max_turns = env.get(turns_key, "")

    run_env = {**os.environ}
    run_env.pop("CLAUDECODE", None)

    cmd = [
        "claude", "--print",
        "--no-session-persistence",
        "--max-budget-usd", budget,
        "--model", model,
        "--dangerously-skip-permissions",
        "-p", prompt,
    ]
    disallowed = DISALLOWED_TOOLS_MAP.get(phase, [])
    if disallowed:
        cmd.extend(["--disallowedTools", ",".join(disallowed)])
    if max_turns:
        cmd.extend(["--max-turns", max_turns])

    with open(log_file, "w") as log:
        ret = subprocess.run(
            cmd,
            stdout=log, stderr=subprocess.STDOUT,
            cwd=work_dir, env=run_env,
        )

    return ret


def generate_pr_body(parent_id: str, parent_identifier: str, repo_path: str,
                     sub_issues: list[dict], env: dict) -> tuple[str, str]:
    prompt_file = FORGE_ROOT / "prompts" / "pr.md"
    prompt = prompt_file.read_text()

    parent_detail = fetch_issue_detail(parent_id)
    prompt = prompt.replace("{{PARENT_ISSUE_DETAIL}}", json.dumps(parent_detail, indent=2, ensure_ascii=False))

    parent_data = fetch_sub_issues(parent_id)
    prompt = prompt.replace("{{PLAN_DOCUMENTS}}", json.dumps(parent_data.get("documents", []), indent=2, ensure_ascii=False))

    sub_summary = []
    for s in sub_issues:
        sub_summary.append(f"- {s['identifier']}: {s['title']} ({s.get('state', '')})")
    prompt = prompt.replace("{{SUB_ISSUES}}", "\n".join(sub_summary))

    default_branch = detect_default_branch(repo_path)
    prompt = prompt.replace("{{DIFF_STAT}}", diff_stat(repo_path, default_branch, parent_identifier))

    model = env.get("FORGE_MODEL_PR", env["FORGE_MODEL"])
    ret = subprocess.run(
        ["claude", "--print", "--no-session-persistence", "--model", model,
         "--max-turns", "1", "-p", prompt],
        capture_output=True, text=True, cwd=repo_path,
    )
    if ret.returncode != 0:
        return parent_detail.get("title", parent_identifier), f"Parent issue: {parent_identifier}\n\nAll sub-issues completed."

    output = ret.stdout.strip()
    title = parent_detail.get("title", parent_identifier)
    body = output

    if "TITLE:" in output and "---" in output:
        parts = output.split("---", 1)
        for line in parts[0].splitlines():
            if line.startswith("TITLE:"):
                title = line.removeprefix("TITLE:").strip()
                break
        body = parts[1].strip()
        if body.startswith("```"):
            body = body.split("\n", 1)[1] if "\n" in body else body
        if body.endswith("```"):
            body = body.rsplit("\n", 1)[0] if "\n" in body else body

    return title, body
