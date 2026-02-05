#!/usr/bin/env python3
"""run-bench.py

Terminal-only A/B harness to measure whether Chitta improves:
- Speed (latency)
- Actionably helpful correctness (manual rating, optional)

It runs each prompt through:
- FAST baseline: quick-chat.py --json
- DEEP baseline: openclaw agent --json

Outputs:
- Writes an encrypted vault item into ~/.openclaw/vault/items as <id>.json.enc
  Passphrase is derived (locally) from ~/.openclaw/workspace/vault.enc.

Notes:
- We intentionally store raw benchmark outputs only encrypted in the vault.
- This script does not write benchmark data into Neo4j.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

CHITTA_DIR = Path("/Users/VedicRGI_Worker/chitta")
VAULT_ITEMS_DIR = Path("/Users/VedicRGI_Worker/.openclaw/vault/items")

sys.path.insert(0, str(CHITTA_DIR))

from crypto_util import derive_passphrase, encrypt_file  # noqa: E402


def _now_ms() -> int:
    return int(time.time() * 1000)


def _run_json(cmd: List[str], timeout_sec: int) -> Tuple[Dict[str, Any], int, str]:
    started = _now_ms()
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    took_ms = _now_ms() - started
    out = (res.stdout or "").strip()
    if res.returncode != 0:
        err = (res.stderr or "").strip()
        raise RuntimeError(f"command failed ({res.returncode}): {' '.join(cmd)}\n{err}")
    try:
        return json.loads(out), took_ms, out
    except Exception as e:
        raise RuntimeError(f"failed to parse JSON from: {' '.join(cmd)}\nerror={e}\nstdout={out[:2000]}")


def run_fast(prompt: str, timeout_sec: int) -> Dict[str, Any]:
    payload, took_ms, _raw = _run_json(
        ["python3", str(CHITTA_DIR / "quick-chat.py"), "--json", prompt],
        timeout_sec=timeout_sec,
    )
    return {
        "latency_ms": took_ms,
        "result": payload,
    }


def run_deep(prompt: str, timeout_sec: int, session_id: str) -> Dict[str, Any]:
    payload, took_ms, _raw = _run_json(
        [
            "openclaw",
            "agent",
            "--session-id",
            session_id,
            "--message",
            prompt,
            "--json",
            "--timeout",
            str(int(timeout_sec)),
        ],
        timeout_sec=max(timeout_sec + 30, 60),
    )
    return {
        "latency_ms": took_ms,
        "result": payload,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompts", default=str(CHITTA_DIR / "bench" / "prompts.json"))
    ap.add_argument("--timeout-fast", type=int, default=60)
    ap.add_argument("--timeout-deep", type=int, default=240)
    ap.add_argument("--id", default=f"bench_{_now_ms()}")
    args = ap.parse_args()

    prompts_path = Path(args.prompts)
    prompts_obj = json.loads(prompts_path.read_text(encoding="utf-8"))
    prompts = prompts_obj.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        raise SystemExit("No prompts found")

    run_id = str(args.id)
    ts = _now_ms()

    results: Dict[str, Any] = {
        "id": run_id,
        "ts_ms": ts,
        "prompts_file": str(prompts_path),
        "items": [],
    }

    for i, item in enumerate(prompts):
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or f"p{i}")
        kind = str(item.get("kind") or "")
        prompt_raw = str(item.get("prompt") or "").strip()
        if not prompt_raw:
            continue
        prompt = prompt_raw.replace("TIMESTAMP", str(_now_ms()))

        fast = run_fast(prompt, timeout_sec=int(args.timeout_fast))
        deep_session = f"bench:{run_id}:{pid}:{_now_ms()}"
        deep = run_deep(prompt, timeout_sec=int(args.timeout_deep), session_id=deep_session)

        results["items"].append(
            {
                "id": pid,
                "kind": kind,
                "prompt": prompt,
                "fast": fast,
                "deep": deep,
                "rating": None,
                "notes": "",
            }
        )

    # Encrypt and store into vault
    VAULT_ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    passphrase = derive_passphrase()
    out_id = run_id
    cipher_path = VAULT_ITEMS_DIR / f"{out_id}.json.enc"

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        tmp.write(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
        tmp_path = tmp.name

    try:
        encrypt_file(tmp_path, str(cipher_path), passphrase=passphrase)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    print(json.dumps({"ok": True, "vault_item": str(cipher_path), "items": len(results["items"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
