#!/usr/bin/env python3
"""chitta-router.py - Vedic Mind Router

Semantic router that classifies messages and routes:
- FAST path: Quick-chat with Chitta memory (~3s)
- DEEP path: Full OpenClaw agent (~30s)

Uses qwen2.5:0.5b for fast classification (~0.8s).

HTTP API (Vedic Gateway):
- POST /route  {"message": "..."}
  -> {"decision": "fast"|"deep", "response": "..."?, "confidence": 0..1, "should_fallthrough": bool}
- GET  /health -> {"status":"healthy", "router":"chitta"}

The /webhook endpoint remains for Signal-cli webhook integration.
"""

import json
import os
import subprocess
import urllib.request
import re
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configuration
ROUTER_PORT = 18800
OLLAMA_URL = "http://127.0.0.1:11434"
CLASSIFIER_MODEL = "qwen2.5:0.5b"
SIGNAL_CLI_URL = "http://127.0.0.1:8080"
SIGNAL_ACCOUNT = "+919952631996"
CHITTA_DIR = (
    os.path.expanduser("~/.openclaw/../chitta")
    if os.path.exists(os.path.expanduser("~/chitta"))
    else "/Users/VedicRGI_Worker/chitta"
)

# Classification prompt
CLASSIFY_PROMPT = """Classify this message as FAST or DEEP.
FAST: Simple factual question, lookup, "who is", "what is", greetings
DEEP: Action request, scheduling, file operations, code tasks, complex analysis

Message: {message}
Output only FAST or DEEP:"""

def _normalize_user_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _is_greeting(text: str) -> bool:
    t = _normalize_user_text(text)
    t = re.sub(r"[!?.]+$", "", t)
    return t in {
        "hi",
        "hi there",
        "hello",
        "hey",
        "hey there",
        "good morning",
        "good afternoon",
        "good evening",
    }


def _is_identity_question(text: str) -> bool:
    t = _normalize_user_text(text)
    if "who are you" in t:
        return True
    if "your name" in t or "what is your name" in t or "what's your name" in t:
        return True
    if "are you manas" in t or "is your name manas" in t:
        return True
    return False


def _is_english_preference(text: str) -> bool:
    t = _normalize_user_text(text)
    return (
        "only in english" in t
        or "reply only in english" in t
        or "reply in english" in t
        or "respond in english" in t
        or "speak english" in t
        or "use english" in t
    )



def classify_message(message):
    """Use qwen2.5:0.5b to classify message as FAST or DEEP."""
    prompt = CLASSIFY_PROMPT.format(message=message[:200])
    payload = {"model": CLASSIFIER_MODEL, "prompt": prompt, "stream": False}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())["response"].strip().upper()
            return "FAST" if "FAST" in result else "DEEP"
    except Exception as e:
        print(f"[Router] Classification error: {e}, defaulting to DEEP")
        return "DEEP"


def quick_chat(query):
    """Call quick-chat.py and return structured result."""
    try:
        result = subprocess.run(
            ["python3", f"{CHITTA_DIR}/quick-chat.py", "--json", query],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=CHITTA_DIR,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        print(f"[Router] Quick-chat error: {result.stderr}")
        return None
    except Exception as e:
        print(f"[Router] Quick-chat exception: {e}")
        return None


def openclaw_agent(message, sender):
    """Forward to OpenClaw agent via CLI."""
    try:
        result = subprocess.run(
            ["openclaw", "agent", "--to", sender, "--message", message, "--channel", "signal"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"
    except Exception as e:
        return f"OpenClaw error: {e}"


def send_signal_message(recipient, message):
    """Send message via signal-cli REST API."""
    payload = {"message": message, "number": SIGNAL_ACCOUNT, "recipients": [recipient]}
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SIGNAL_CLI_URL}/v2/send", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30):
            return True
    except Exception as e:
        print(f"[Router] Signal send error: {e}")
        # Fallback to CLI
        try:
            subprocess.run(
                [
                    "openclaw",
                    "message",
                    "send",
                    "--channel",
                    "signal",
                    "--target",
                    recipient,
                    "--message",
                    message,
                ],
                timeout=30,
            )
            return True
        except Exception:
            return False


def route_message(sender, message):
    """Main routing logic (webhook mode: can fall through into OpenClaw)."""
    print(f"[Router] Received from {sender}: {message[:50]}...")

    if _is_greeting(message):
        return "Hi — I’m Manas. How can I help?"

    if _is_identity_question(message):
        return "Yes — my name is Manas."

    if _is_english_preference(message):
        return "Understood — I’ll reply in English."

    # Check for explicit /q command (always FAST)
    if message.startswith("/q "):
        query = message[3:].strip()
        print("[Router] /q command detected, using FAST path")
        result = quick_chat(query)
        if result:
            return result.get("response", "")
        return "Quick-chat error. Please try again."

    # Semantic classification
    route = classify_message(message)
    print(f"[Router] Classified as: {route}")

    if route == "FAST":
        result = quick_chat(message)
        if result:
            if result.get("should_fallthrough", False):
                print(
                    f"[Router] Low confidence ({result.get('confidence', 0):.2f}), falling through to DEEP"
                )
                return openclaw_agent(message, sender)
            print(f"[Router] FAST path success (confidence: {result.get('confidence', 0):.2f})")
            return result.get("response", "")

        print("[Router] Quick-chat failed, falling through to DEEP")
        return openclaw_agent(message, sender)

    print("[Router] Using DEEP path (OpenClaw agent)")
    return openclaw_agent(message, sender)


def route_message_struct(message):
    """Routing logic for OpenClaw middleware: never calls OpenClaw; returns a decision."""
    trimmed = (message or "").strip()
    # Deterministic FAST rules to prevent identity/language drift on short messages.
    if _is_greeting(trimmed):
        return {
            "decision": "fast",
            "response": "Hi — I’m Manas. How can I help?",
            "confidence": 1.0,
            "should_fallthrough": False,
            "route": "FAST",
        }

    if _is_identity_question(trimmed):
        return {
            "decision": "fast",
            "response": "Yes — my name is Manas.",
            "confidence": 1.0,
            "should_fallthrough": False,
            "route": "FAST",
        }

    if _is_english_preference(trimmed):
        return {
            "decision": "fast",
            "response": "Understood — I’ll reply in English.",
            "confidence": 1.0,
            "should_fallthrough": False,
            "route": "FAST",
        }

    if not trimmed:
        return {"decision": "deep", "confidence": 0.0, "should_fallthrough": True}

    if trimmed.startswith("/q "):
        query = trimmed[3:].strip()
        result = quick_chat(query)
        if result and result.get("response"):
            return {
                "decision": "fast",
                "response": result.get("response", ""),
                "confidence": float(result.get("confidence", 0.0) or 0.0),
                "should_fallthrough": bool(result.get("should_fallthrough", False)),
                "route": "FAST",
            }
        return {"decision": "deep", "confidence": 0.0, "should_fallthrough": True, "route": "FAST"}

    route = classify_message(trimmed)

    if route != "FAST":
        return {"decision": "deep", "confidence": 0.0, "should_fallthrough": True, "route": "DEEP"}

    result = quick_chat(trimmed)
    if not result:
        return {"decision": "deep", "confidence": 0.0, "should_fallthrough": True, "route": "FAST"}

    confidence = float(result.get("confidence", 0.0) or 0.0)
    should_fallthrough = bool(result.get("should_fallthrough", False))
    response = (result.get("response") or "").strip()

    if response and not should_fallthrough:
        return {
            "decision": "fast",
            "response": response,
            "confidence": confidence,
            "should_fallthrough": False,
            "route": "FAST",
        }

    return {
        "decision": "deep",
        "confidence": confidence,
        "should_fallthrough": True,
        "route": "FAST",
    }


class WebhookHandler(BaseHTTPRequestHandler):
    """Handle incoming /webhook posts and /route middleware calls."""

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if self.path.startswith("/route"):
            try:
                data = json.loads(body) if body else {}
            except Exception:
                self._send_json(400, {"error": "invalid json"})
                return

            message = data.get("message")
            if not isinstance(message, str):
                self._send_json(400, {"error": "missing message"})
                return

            try:
                result = route_message_struct(message)
                self._send_json(200, result)
            except Exception as e:
                self._send_json(200, {"decision": "deep", "error": str(e), "should_fallthrough": True})
            return

        # Default: treat as signal-cli webhook.
        try:
            data = json.loads(body)
            print(f"[Router] Webhook received: {json.dumps(data)[:200]}")

            envelope = data.get("envelope", data)
            source = envelope.get("source", envelope.get("sourceNumber", ""))

            data_message = envelope.get("dataMessage", {})
            message = data_message.get("message", "")

            if not message or not source:
                self._send_json(200, {"status": "ignored"})
                return

            response = route_message(source, message)

            if response:
                send_signal_message(source, response)

            self._send_json(200, {"status": "ok"})

        except Exception as e:
            print(f"[Router] Webhook error: {e}")
            self._send_json(500, {"error": str(e)})

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "healthy", "router": "chitta"})
            return

        self._send_json(404, {"error": "not found"})

    def log_message(self, format, *args):
        print(f"[Router] {args[0]}")


def main():
    print(
        f"""
╔═══════════════════════════════════════════════════════════╗
║           Chitta Router - Vedic Mind Gateway              ║
║                                                           ║
║  FAST path: Quick-chat with memory graph (~3s)            ║
║  DEEP path: Full OpenClaw agent (~30s)                    ║
║                                                           ║
║  Listening on port {ROUTER_PORT}                               ║
║  Classifier: {CLASSIFIER_MODEL}                           ║
╚═══════════════════════════════════════════════════════════╝
"""
    )

    server = HTTPServer(("127.0.0.1", ROUTER_PORT), WebhookHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Router] Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
