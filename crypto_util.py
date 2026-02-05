#!/usr/bin/env python3
"""crypto_util.py

Helper utilities for encrypting/decrypting files for Chitta maintenance scripts.

Goals:
- No extra Python deps (use system /usr/bin/openssl).
- Never print key material.
- Derive a passphrase deterministically from ~/.openclaw/workspace/vault.enc bytes.

Crypto (LibreSSL compatible):
- AES-256-CBC + PBKDF2 + SHA-256.

Command template:
  /usr/bin/openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -salt -pass env:CHITTA_PASSPHRASE

Note:
- CBC is not an AEAD mode (no authentication). For a future upgrade, prefer age
  or libsodium AEAD.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Optional

DEFAULT_ITER = 200_000
CIPHER = "-aes-256-cbc"


def derive_passphrase(
    vault_enc_path: str = "/Users/VedicRGI_Worker/.openclaw/workspace/vault.enc",
) -> str:
    raw = Path(vault_enc_path).read_bytes()
    return hashlib.sha256(raw).hexdigest()


def _run(cmd: list[str], env: Optional[dict[str, str]] = None) -> None:
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        stderr = (res.stderr or "").strip()
        msg = f"command failed ({res.returncode}): {' '.join(cmd)}"
        if stderr:
            msg += f"\n{stderr}"
        raise RuntimeError(msg)


def encrypt_file(
    plaintext_path: str,
    ciphertext_path: str,
    *,
    passphrase: str,
    iter_count: int = DEFAULT_ITER,
) -> None:
    Path(ciphertext_path).parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CHITTA_PASSPHRASE"] = passphrase
    _run(
        [
            "/usr/bin/openssl",
            "enc",
            CIPHER,
            "-pbkdf2",
            "-iter",
            str(int(iter_count)),
            "-md",
            "sha256",
            "-salt",
            "-pass",
            "env:CHITTA_PASSPHRASE",
            "-in",
            plaintext_path,
            "-out",
            ciphertext_path,
        ],
        env=env,
    )


def decrypt_file(
    ciphertext_path: str,
    plaintext_path: str,
    *,
    passphrase: str,
    iter_count: int = DEFAULT_ITER,
) -> None:
    Path(plaintext_path).parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CHITTA_PASSPHRASE"] = passphrase
    _run(
        [
            "/usr/bin/openssl",
            "enc",
            "-d",
            CIPHER,
            "-pbkdf2",
            "-iter",
            str(int(iter_count)),
            "-md",
            "sha256",
            "-salt",
            "-pass",
            "env:CHITTA_PASSPHRASE",
            "-in",
            ciphertext_path,
            "-out",
            plaintext_path,
        ],
        env=env,
    )
