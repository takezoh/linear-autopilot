import json
import os
import signal
from pathlib import Path


def enqueue(queue_dir: str | Path, issue_id: str, session_id: str = "", phase: str = ""):
    queue_dir = Path(queue_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)
    payload = {"issue_id": issue_id, "session_id": session_id, "phase": phase}
    (queue_dir / f"{issue_id}.json").write_text(json.dumps(payload))


def dequeue_all(queue_dir: str | Path) -> list[dict]:
    queue_dir = Path(queue_dir)
    if not queue_dir.exists():
        return []
    items = []
    for f in queue_dir.glob("*.json"):
        try:
            items.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
        f.unlink(missing_ok=True)
    return items


def wake(pid_file: str | Path):
    pid_file = Path(pid_file)
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGUSR1)
    except (ValueError, ProcessLookupError, OSError):
        pass
