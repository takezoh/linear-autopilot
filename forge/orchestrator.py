import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from .config import FORGE_ROOT, load_env, load_repos, resolve_repo
from .constants import (STATE_PLANNING, STATE_IMPLEMENTING,
                        STATE_PLAN_CHANGES_REQUESTED, STATE_CHANGES_REQUESTED,
                        STATE_IN_PROGRESS, STATE_IN_REVIEW, STATE_DONE)
from .git import branch_exists, create_branch, detect_default_branch, worktree_add, worktree_remove, pr_create
from .claude import generate_pr_body
from .linear import poll, fetch_sub_issues, update_issue_state


def count_locks(lock_dir: Path) -> int:
    return len(list(lock_dir.glob("*.lock")))


def clean_stale_locks(lock_dir: Path, timeout_min: int):
    now = time.time()
    for lock in lock_dir.glob("*.lock"):
        age_min = (now - lock.stat().st_mtime) / 60
        if age_min > timeout_min:
            lock.unlink(missing_ok=True)


def log(msg: str):
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


def create_parent_pr(parent_identifier: str, parent_title: str, repo_path: str,
                     parent_id: str, lock_dir: Path, env: dict,
                     sub_issues: list[dict] | None = None):
    pr_lock = lock_dir / f"pr-{parent_identifier}.lock"
    if pr_lock.exists():
        log(f"  Skip PR creation for {parent_identifier} (already created)")
        return

    pr_lock.write_text(parent_identifier)

    log(f"  Generating PR description for {parent_identifier}...")
    title, body = generate_pr_body(parent_id, parent_identifier, repo_path,
                                   sub_issues or [], env)

    default_branch = detect_default_branch(repo_path)
    ret = pr_create(repo_path, f"{parent_identifier}: {title}", body,
                    parent_identifier, default_branch)
    if ret.returncode == 0:
        log(f"  Created PR for {parent_identifier}")
    else:
        log(f"  Failed to create PR for {parent_identifier}: {ret.stderr}")
        pr_lock.unlink(missing_ok=True)
        return

    update_issue_state(parent_id, STATE_IN_REVIEW)

    parent_worktree = Path(env["FORGE_WORKTREE_DIR"]) / Path(repo_path).name / parent_identifier
    if parent_worktree.exists():
        worktree_remove(repo_path, str(parent_worktree))


def dispatch_issue(phase: str, issue: dict, lock_dir: Path, max_concurrent: int,
                   repos: dict[str, str], parent_id: str = "",
                   parent_identifier: str = "") -> subprocess.Popen | None:
    issue_id = issue["id"]
    identifier = issue["identifier"]
    title = issue["title"]
    labels = issue.get("labels", [])

    lock_file = lock_dir / f"{issue_id}.lock"
    if lock_file.exists():
        log(f"  Skip {identifier} (locked): {title}")
        return None

    if count_locks(lock_dir) >= max_concurrent:
        log(f"  Skip {identifier} (max concurrent): {title}")
        return None

    repo_path = resolve_repo(labels, repos)
    if not repo_path:
        log(f"  Skip {identifier} (no repo label): {title}")
        return None
    if not Path(repo_path).is_dir():
        log(f"  Skip {identifier} (repo not found: {repo_path}): {title}")
        return None

    log(f"  Start {identifier} ({phase}): {title}")
    lock_file.write_text(identifier)

    cmd = [sys.executable, "-m", "forge.executor", phase, issue_id, identifier, repo_path]
    if parent_id:
        cmd.append(parent_id)
    if parent_identifier:
        cmd.append(parent_identifier)

    return subprocess.Popen(cmd, cwd=str(FORGE_ROOT))


def main():
    env = load_env()
    log_dir = Path(env["FORGE_LOG_DIR"])
    lock_dir = Path(env["FORGE_LOCK_DIR"])
    max_concurrent = int(env["FORGE_MAX_CONCURRENT"])
    lock_timeout = int(env["FORGE_LOCK_TIMEOUT_MIN"])

    log_dir.mkdir(parents=True, exist_ok=True)
    lock_dir.mkdir(parents=True, exist_ok=True)

    repos = load_repos()

    clean_stale_locks(lock_dir, lock_timeout)

    log("=== forge started ===")

    log("Polling Planning issues...")
    planning_issues = poll(STATE_PLANNING)

    log("Polling Implementing issues...")
    implementing_issues = poll(STATE_IMPLEMENTING)

    log("Polling Plan Changes Requested issues...")
    plan_review_issues = poll(STATE_PLAN_CHANGES_REQUESTED)

    log("Polling Changes Requested issues...")
    review_issues = poll(STATE_CHANGES_REQUESTED)

    processes: list[subprocess.Popen] = []

    if planning_issues:
        log(f"{len(planning_issues)} planning issue(s) found")
        for issue in planning_issues:
            p = dispatch_issue("planning", issue, lock_dir, max_concurrent, repos)
            if p:
                processes.append(p)

    if implementing_issues:
        log(f"{len(implementing_issues)} implementing parent issue(s) found")
        for parent in implementing_issues:
            parent_id = parent["id"]
            parent_identifier = parent["identifier"]
            parent_labels = parent.get("labels", [])

            repo_path = resolve_repo(parent_labels, repos)
            if not repo_path:
                log(f"  Skip {parent_identifier} (no repo label): {parent['title']}")
                continue
            if not Path(repo_path).is_dir():
                log(f"  Skip {parent_identifier} (repo not found: {repo_path}): {parent['title']}")
                continue

            log(f"  Fetching sub-issues for {parent_identifier}...")
            result = fetch_sub_issues(parent_id)
            sub_issues = result["sub_issues"]

            if result.get("cycle"):
                log(f"  Skip {parent_identifier} (dependency cycle: {' -> '.join(result['cycle'])})")
                continue

            if not branch_exists(repo_path, parent_identifier):
                default_branch = detect_default_branch(repo_path)
                br_ret = create_branch(repo_path, parent_identifier, default_branch)
                if br_ret.returncode != 0:
                    log(f"  Failed to create parent branch {parent_identifier} from {default_branch}: {br_ret.stderr.strip()}")
                    continue
                log(f"  Created parent branch: {parent_identifier} (from {default_branch})")

            parent_worktree = Path(env["FORGE_WORKTREE_DIR"]) / Path(repo_path).name / parent_identifier
            if not parent_worktree.exists():
                parent_worktree.parent.mkdir(parents=True, exist_ok=True)
                worktree_add(repo_path, str(parent_worktree), parent_identifier)
                log(f"  Created parent worktree: {parent_worktree}")

            ready = [s for s in sub_issues if s.get("ready")]
            done = [s for s in sub_issues if s.get("state") in (STATE_DONE, STATE_IN_REVIEW)]
            log(f"  {parent_identifier}: {len(sub_issues)} sub-issues, {len(ready)} ready, {len(done)} done")

            for sub in ready:
                sub_issue = {
                    "id": sub["id"],
                    "identifier": sub["identifier"],
                    "title": sub["title"],
                    "labels": parent_labels,
                }
                p = dispatch_issue("implementing", sub_issue, lock_dir, max_concurrent, repos,
                                   parent_id=parent_id, parent_identifier=parent_identifier)
                if p:
                    update_issue_state(sub["id"], STATE_IN_PROGRESS)
                    processes.append(p)

            all_done = all(s.get("state") == STATE_DONE for s in sub_issues) and len(sub_issues) > 0
            if all_done:
                create_parent_pr(parent_identifier, parent["title"], repo_path,
                                 parent_id, lock_dir, env, sub_issues=sub_issues)

    if plan_review_issues:
        log(f"{len(plan_review_issues)} plan review issue(s) found")
        for issue in plan_review_issues:
            p = dispatch_issue("plan_review", issue, lock_dir, max_concurrent, repos)
            if p:
                processes.append(p)

    if review_issues:
        log(f"{len(review_issues)} review feedback issue(s) found")
        for issue in review_issues:
            p = dispatch_issue("review", issue, lock_dir, max_concurrent, repos)
            if p:
                processes.append(p)

    for p in processes:
        p.wait()

    log("=== forge finished ===")
    return len(processes) > 0
