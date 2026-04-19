"""Drive → GitHub 片方向同期。

KNOWLEDGE_DRIVE_MOUNT の内容を KNOWLEDGE_GITHUB_REPO_PATH 配下にコピーし、
差分があれば git add/commit/push する。常駐スクリプトとして定期実行する。

衝突回避: GitHub側の knowledge/ ミラーは readonly 運用。直接編集はしない。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect_files(root: Path) -> dict[str, str]:
    """root配下の全ファイルの相対パス → SHA256 マップ。"""
    result: dict[str, str] = {}
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        result[rel] = _file_hash(p)
    return result


def _sync_once(drive_path: Path, repo_knowledge_path: Path) -> tuple[int, int, int]:
    """Drive → repo_knowledge_path に rsync相当コピー。追加/更新/削除 の件数を返す。"""
    drive_files = _collect_files(drive_path) if drive_path.exists() else {}
    repo_files = _collect_files(repo_knowledge_path) if repo_knowledge_path.exists() else {}

    added = updated = removed = 0
    repo_knowledge_path.mkdir(parents=True, exist_ok=True)

    for rel, src_hash in drive_files.items():
        dst = repo_knowledge_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel not in repo_files:
            shutil.copy2(drive_path / rel, dst)
            added += 1
        elif repo_files[rel] != src_hash:
            shutil.copy2(drive_path / rel, dst)
            updated += 1

    for rel in repo_files:
        if rel not in drive_files:
            (repo_knowledge_path / rel).unlink()
            removed += 1

    return added, updated, removed


def _git_commit_push(repo_root: Path, knowledge_subdir: str) -> bool:
    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    run("git", "add", knowledge_subdir)
    status = run("git", "status", "--porcelain", knowledge_subdir)
    if not status.stdout.strip():
        return False  # 変更なし

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit = run(
        "git", "commit",
        "-m", f"chore(knowledge): auto-sync from Drive {ts}",
    )
    if commit.returncode != 0:
        raise RuntimeError(f"git commit failed: {commit.stderr}")

    push = run("git", "push")
    if push.returncode != 0:
        raise RuntimeError(f"git push failed: {push.stderr}")
    return True


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    drive_mount = os.environ.get("KNOWLEDGE_DRIVE_MOUNT")
    repo_knowledge = os.environ.get("KNOWLEDGE_GITHUB_REPO_PATH")
    interval = int(os.environ.get("KNOWLEDGE_SYNC_INTERVAL_SEC", "600"))

    if not drive_mount or not repo_knowledge:
        raise SystemExit(
            "KNOWLEDGE_DRIVE_MOUNT と KNOWLEDGE_GITHUB_REPO_PATH を .env に設定してください"
        )

    drive_path = Path(drive_mount)
    repo_knowledge_path = Path(repo_knowledge)
    repo_root = repo_knowledge_path.parent
    knowledge_subdir = repo_knowledge_path.name

    print(f"[sync] drive={drive_path} repo={repo_knowledge_path} interval={interval}s")

    while True:
        try:
            added, updated, removed = _sync_once(drive_path, repo_knowledge_path)
            changed = added + updated + removed
            if changed:
                pushed = _git_commit_push(repo_root, knowledge_subdir)
                print(
                    f"[sync] +{added} ~{updated} -{removed} "
                    f"{'pushed' if pushed else 'no_git_change'}"
                )
            else:
                print("[sync] no diff")
        except Exception as e:
            print(f"[sync] ERROR: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
