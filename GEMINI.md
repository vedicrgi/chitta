# GEMINI.md - VedicRGI Mission Control

## Project Overview: VedicRGI
**Vedic Reliable General Intelligence (RGI)** is a dual-layered AI system designed as a digital extension of Vinodh. It optimizes for **reliability** (*Satya*) over fluency, using a "Mind/Body" architecture grounded in **Vedic Cognitive Architecture** (*Antahkarana*).

### The Philosophy
- **Reliability over Generation:** The system prefers restraint (*Neti, Neti* — "Not this, not this") over hallucination.
- **The Verifier Model:** Separates Execution (Body) from Verification (Mind). Intelligence is defined not just by generation, but by the ability to restrain it until verified.
- **Domain Sovereignty:** The Universal Body (OpenClaw) remains infrastructure, while the Sovereign Mind (Chitta) encodes specific laws, memories, and values.

---

## 1. The Antahkarana (Inner Instrument)

| Component | Vedic Role | Implementation | Cybernetic Function |
|-----------|------------|----------------|---------------------|
| **Manas** | Sensory Router | `chitta-router.py` | Input filter; classifies FAST vs DEEP. |
| **Chitta** | Memory Graph | Neo4j (Tripartite) | Constraint & Verifier; grounds answers in truth. |
| **Buddhi** | Intellect/Logic | Router Decision Logic | Discrimination; evaluates confidence and fallthrough. |
| **Ahamkara** | Identity/Ego | Persona (Manas) | Vinodh's extension; maintains tone and boundaries. |
| **Jnana Indriyas** | Input Organs | Signal/WhatsApp/WebChat | Ingestion of external stimuli (messages). |
| **Karma Indriyas** | Action Organs | OpenClaw Agent & Tools | Execution of tasks; manifests only after verification. |

---

## 2. Technical Mandates & Flow of Prana

### The Path of a Message
1. **Ingestion (Jnana Indriyas):** Message received by the OpenClaw gateway.
2. **Filtering (Manas):** `chitta-router.py` receives the message and queries Chitta.
3. **Grounding (Chitta):** Vector search on **Context** nodes + keyword boost via **Sensor** nodes.
4. **Discrimination (Buddhi):** Confidence evaluation:
    - **Sattva (FAST):** High confidence memory match -> immediate reply (~3s).
    - **Rajas (DEEP):** Low confidence or tool-intent -> fallthrough to Agent (~30s).
5. **Execution (Karma Indriyas):** Agent runs tools or generator; response delivered to user.

### Runtime Requirements
- **Node.js:** MUST be **v22.12.0 or later** (LTS) for security and stability.
- **Python:** Used for the Chitta router and GraphRAG logic.
- **Neo4j:** The authoritative storehouse of impressions (*Chitta*).

### Naming Conventions (Mandatory)
- **`chitta_` prefix:** For symbols belonging to deep storage, memory retrieval, or graph operations.
- **`manas_` prefix:** For symbols belonging to routing, sensory processing, or classification.
- **No Generic Terms:** Avoid renaming Chitta, Manas, Buddhi, etc., to generic equivalents (e.g., "MemoryStore").

### Observability: The Trace
Every "breath" (interaction) is logged as a trace artifact:
- **Location:** `/Users/VedicRGI_Worker/logs/chitta-route.jsonl`
- **Utility:** Source of truth for debugging FAST vs DEEP decisions and outcome confidence.

---

## 3. Directory Structure
- `/Users/VedicRGI_Worker/chitta`: The Mind (Python/Neo4j).
- `/Users/VedicRGI_Worker/openclaw-src`: The Body (Node.js/TypeScript).
- `/Users/VedicRGI_Worker/scripts`: Mission Control & Lifecycle (wake_up, monitor).
- `/Users/VedicRGI_Worker/logs`: Unified logs (chitta, sharira, route trace).

## 4. Security & User Roles
Respect the role-based gating in `signal_gateway.py`:
- **ADMIN:** (Vinodh) Full bypass of tool confirmations.
- **MITRA/GRIHASTA/RISHI:** Strict boundaries; no terminal access; no financial/location leaks.
- **Neti, Neti:** If data is missing or unauthorized, the system MUST admit ignorance ("Data Missing").
- **Secret Detection:** `detect-secrets` is used in CI; never commit raw credentials.
