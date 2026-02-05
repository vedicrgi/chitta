#!/usr/bin/env python3
"""archive-sessions.py

Session retention policy:
- Keep the most recent N days of plaintext session JSONL files ("hot").
- Archive older sessions into monthly tar.gz bundles and encrypt them.

Safety defaults:
- If you run with no flags, it behaves like --dry-run.
- --encrypt creates encrypted archives and keeps plaintext.
- --delete requires --encrypt and deletes plaintext only after encryption succeeds.

Encryption passphrase is derived from ~/.openclaw/workspace/vault.enc.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List

from crypto_util import derive_passphrase, encrypt_file

SESSIONS_DIR = Path("/Users/VedicRGI_Worker/.openclaw/agents/main/sessions")
ARCHIVE_DIR = Path("/Users/VedicRGI_Worker/.openclaw/archives/sessions")


def month_key_from_mtime(mtime_sec: float) -> str:
    lt = time.gmtime(mtime_sec)
    return f"{lt.tm_year:04d}-{lt.tm_mon:02d}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hot-days", type=int, default=90)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--encrypt", action="store_true")
    ap.add_argument("--delete", action="store_true")
    args = ap.parse_args()

    if not args.dry_run and not args.encrypt and not args.delete:
        args.dry_run = True

    if args.delete and not args.encrypt:
        raise SystemExit("Refusing: --delete requires --encrypt")

    if args.dry_run and (args.encrypt or args.delete):
        raise SystemExit("Refusing: --dry-run cannot be combined with --encrypt/--delete")

    if not SESSIONS_DIR.exists():
        print("No sessions dir; nothing to do")
        return 0

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    passphrase = derive_passphrase()

    cutoff_sec = time.time() - (max(1, int(args.hot_days)) * 86400)

    old_files: List[Path] = []
    for p in sorted(SESSIONS_DIR.glob("*.jsonl"), key=lambda x: x.name):
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        if st.st_mtime < cutoff_sec:
            old_files.append(p)

    if not old_files:
        print("No files eligible for archiving")
        return 0

    groups: Dict[str, List[Path]] = {}
    for p in old_files:
        key = month_key_from_mtime(p.stat().st_mtime)
        groups.setdefault(key, []).append(p)

    for month, files in sorted(groups.items()):
        enc_path = ARCHIVE_DIR / f"{month}.tar.gz.enc"

        if args.dry_run:
            print(f"[dry-run] would archive {len(files)} files -> {enc_path.name}")
            continue

        with tempfile.TemporaryDirectory() as td:
            tmp_tar = Path(td) / f"{month}.tar.gz"
            rels = [p.name for p in files]
            cmd = ["/usr/bin/tar", "-czf", str(tmp_tar), "-C", str(SESSIONS_DIR)] + rels
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise RuntimeError(f"tar failed: {res.stderr.strip()}")

            encrypt_file(str(tmp_tar), str(enc_path), passphrase=passphrase)

        if args.delete:
            for p in files:
                try:
                    p.unlink()
                except FileNotFoundError:
                    pass

    print(
        {
            "ok": True,
            "eligible_files": len(old_files),
            "months": sorted(groups.keys()),
            "dry_run": bool(args.dry_run),
            "encrypted": bool(args.encrypt),
            "deleted": bool(args.delete),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
