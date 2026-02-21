#!/usr/bin/env python3
"""ingest-sessions.py

Ingest OpenClaw session JSONL into:
- Encrypted vault items (raw text)
- Redacted Neo4j Context nodes (for Chitta quick-chat retrieval)

Ingest rules (initial):
- Only message.role in {user, assistant}
- Only content blocks where block.type == "text"
- Skip toolResult and non-text blocks

Idempotency:
- Cursor file stores per-session-file byte offsets.
- Stable IDs derived from (session_file, byte_offset, role, block_index).

Security:
- Raw text is stored only in encrypted vault items.
- Neo4j receives only heuristic-redacted text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple

from neo4j import GraphDatabase

from crypto_util import derive_passphrase, encrypt_file

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "vedicrgi2025")
OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"

SESSIONS_DIR = Path("/Users/VedicRGI_Worker/.openclaw/agents/main/sessions")
STATE_DIR = Path("/Users/VedicRGI_Worker/.openclaw/chitta")
STATE_PATH = STATE_DIR / "ingest-state.json"
VAULT_ITEMS_DIR = Path("/Users/VedicRGI_Worker/.openclaw/vault/items")

RE_EMAIL = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
RE_URL = re.compile(r"https?://\S+", re.IGNORECASE)
RE_PHONE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
RE_LONG_NUM = re.compile(r"\b\d{5,}\b")


def sha256_12_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def get_embedding(text: str) -> List[float]:
    data = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["embedding"]


def redact_text(text: str, max_len: int = 700) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = RE_EMAIL.sub("[EMAIL]", t)
    t = RE_URL.sub("[URL]", t)
    t = RE_PHONE.sub("[PHONE]", t)
    t = RE_LONG_NUM.sub("[NUMBER]", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > max_len:
        t = t[: max_len - 3].rstrip() + "..."
    return t


def is_noise(text: str) -> bool:
    """Check if the text is a placeholder, error, or noise message."""
    t = text.strip().upper()
    noise_patterns = [
        r"^NO_ANSWER_YET$",
        r"^NO_SIGNAL_HERE",
        r"^NO_REPLY$",
        r"^NO_IMAGE_FOUND",
        r"^NO RESPONSE YET",
        r"^MEDIA:/USERS/",
        r"^PRE-COMPACTION MEMORY FLUSH",
        r"^\[QUEUED MESSAGES WHILE AGENT WAS BUSY\]",
    ]
    for p in noise_patterns:
        if re.search(p, t):
            return True
    
    # Also skip very short messages that don't add value
    if len(text.strip()) < 3:
        return True
        
    return False


def load_state() -> Dict[str, Any]:
    try:
        obj = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"version": 1, "files": {}}


def save_state(state: Dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(f".tmp.{os.getpid()}.{int(time.time())}")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def iter_session_files() -> List[Path]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted(SESSIONS_DIR.glob("*.jsonl"), key=lambda p: p.name)


def extract_text_blocks(message: Dict[str, Any]) -> List[Tuple[int, str]]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    out: List[Tuple[int, str]] = []
    for i, block in enumerate(content):
        if not isinstance(block, dict):
            continue
        if block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            out.append((i, text))
    return out


def chitta_upsert_context(
    driver: GraphDatabase.driver,
    *,
    ctx_id: str,
    name: str,
    source: str,
    redacted_text: str,
    moment_id: str,
) -> None:
    emb = get_embedding(redacted_text[:2000])
    with driver.session() as session:
        session.run(
            "MERGE (c:Context {id: $id}) "
            "SET c.name = $name, c.source = $src, c.text = $txt, c.embedding = $emb, c.updated_at = datetime()",
            id=ctx_id,
            name=name,
            src=source,
            txt=redacted_text,
            emb=emb,
        )
        session.run(
            "MERGE (m:Moment {id: $id}) "
            "ON CREATE SET m.timestamp = datetime(), m.source = $src "
            "SET m.source = $src",
            id=moment_id,
            src=source,
        )
        session.run(
            "MATCH (c:Context {id: $cid}), (m:Moment {id: $mid}) MERGE (c)-[:HAS_MOMENT]->(m)",
            cid=ctx_id,
            mid=moment_id,
        )


def ingest_one_text_block(
    *,
    driver: GraphDatabase.driver,
    passphrase: str,
    session_file: str,
    byte_offset: int,
    role: str,
    block_index: int,
    raw_text: str,
    dry_run: bool,
) -> bool:
    raw_text = raw_text.strip()
    if not raw_text:
        return False
        
    if is_noise(raw_text):
        return False

    stable = f"{session_file}:{byte_offset}:{role}:{block_index}"
    item_id = sha256_12_hex(stable)

    redacted = redact_text(raw_text)
    if not redacted:
        return False

    if dry_run:
        return True

    vault_plain = {
        "id": item_id,
        "created_at": int(time.time() * 1000),
        "source": {
            "session_file": session_file,
            "byte_offset": byte_offset,
            "role": role,
            "block_index": block_index,
        },
        "raw_text": raw_text,
    }

    VAULT_ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    vault_cipher_path = VAULT_ITEMS_DIR / f"{item_id}.json.enc"

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        tmp.write(json.dumps(vault_plain, ensure_ascii=False) + "\n")
        tmp_path = tmp.name

    try:
        encrypt_file(tmp_path, str(vault_cipher_path), passphrase=passphrase)
    except Exception as e:
        print(f"Warning: Failed to encrypt to vault: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    ctx_id = f"sess_{item_id}"
    moment_id = f"m_sess_{item_id}"
    ctx_name = f"session:{session_file}:{role}"
    ctx_source = f"session:{session_file}"

    chitta_upsert_context(
        driver,
        ctx_id=ctx_id,
        name=ctx_name,
        source=ctx_source,
        redacted_text=redacted,
        moment_id=moment_id,
    )

    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    state = load_state()
    files_state = state.setdefault("files", {})

    passphrase = derive_passphrase()
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

    ingested = 0
    try:
        for p in iter_session_files():
            key = str(p)
            prev_off = int(files_state.get(key, 0) or 0)
            size = p.stat().st_size
            if prev_off > size:
                prev_off = 0

            with p.open("rb") as fp:
                fp.seek(prev_off)
                while ingested < args.limit:
                    pos = fp.tell()
                    line = fp.readline()
                    if not line:
                        break
                    new_off = fp.tell()

                    try:
                        obj = json.loads(line.decode("utf-8"))
                    except Exception:
                        files_state[key] = new_off
                        continue

                    if not isinstance(obj, dict) or obj.get("type") != "message":
                        files_state[key] = new_off
                        continue

                    msg = obj.get("message")
                    if not isinstance(msg, dict):
                        files_state[key] = new_off
                        continue

                    role = msg.get("role")
                    if role not in ("user", "assistant"):
                        files_state[key] = new_off
                        continue

                    blocks = extract_text_blocks(msg)
                    if not blocks:
                        files_state[key] = new_off
                        continue

                    for block_index, text in blocks:
                        if ingested >= args.limit:
                            break
                        if ingest_one_text_block(
                            driver=driver,
                            passphrase=passphrase,
                            session_file=p.name,
                            byte_offset=pos,
                            role=role,
                            block_index=block_index,
                            raw_text=text,
                            dry_run=bool(args.dry_run),
                        ):
                            ingested += 1

                    files_state[key] = new_off

            state["updated_at_ms"] = int(time.time() * 1000)
            save_state(state)

        state["updated_at_ms"] = int(time.time() * 1000)
        save_state(state)

    finally:
        driver.close()

    print(json.dumps({"ok": True, "dry_run": bool(args.dry_run), "ingested": ingested}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
