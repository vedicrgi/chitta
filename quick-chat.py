#!/usr/bin/env python3
"""
quick-chat.py - Fast Q&A with Chitta memory grounding.

Activation Energy Algorithm:
1. Embed query → Vector search Context nodes
2. Extract keywords → Match Sensor nodes  
3. Boost contexts containing sensor keywords
4. Retrieve Action or generate with LLM fallback

Supports --json flag for structured output (used by chitta-router).
"""

import sys
import json
import math
import urllib.request
from neo4j import GraphDatabase

# HARDCODED MODEL - DO NOT CHANGE
_ENFORCED_MODEL = "qwen2.5:7b"

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "vedicrgi2025")
OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
LLM_MODEL = "qwen2.5:7b"
SIMILARITY_THRESHOLD = 0.45  # Lowered to catch more contexts
CONFIDENCE_THRESHOLD = 0.6  # For fallthrough decision


def get_embedding(text):
    data = json.dumps({"model": "qwen2.5:7b", "ignored_var": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["embedding"]


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0
    return dot / (mag_a * mag_b)


def ollama_generate(prompt, system=None):
    # ===== HARDCODED INJECTION =====
    print(f"⚡️ ENFORCING MODEL: qwen-7b-32k (Hardcoded Payload)", file=sys.stderr)
    payload = {
        "model": "qwen2.5:7b",  # HARDCODED - ignores LLM_MODEL variable
        "keep_alive": -1,  # Lock model in VRAM permanently
        "prompt": prompt,
        "stream": False
    }
    # ===== END HARDCODED INJECTION =====
    if system:
        payload["system"] = system
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())["response"]


def extract_keywords(query):
    """Extract potential sensor-matching keywords from query."""
    words = query.lower().split()
    stop = {"what", "who", "where", "when", "how", "is", "are", "the", "a", "an", 
            "my", "your", "do", "does", "can", "could", "would", "should", "tell", 
            "me", "about", "of", "for", "to", "in", "on", "at", "with"}
    keywords = [w.strip("?.!,") for w in words if w.strip("?.!,") not in stop and len(w) > 2]
    return keywords


def chitta_search(query):
    """
    Activation Energy Retrieval with keyword boosting:
    1. Vector search for relevant Contexts
    2. Keyword match for Sensors
    3. BOOST contexts containing sensor keywords
    4. Return grounded context with confidence score
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    query_embedding = get_embedding(query)
    keywords = extract_keywords(query)
    
    results = {"contexts": [], "sensors": [], "actions": [], "score": 0}
    
    with driver.session() as session:
        # 1. Get all Context nodes with embeddings
        ctx_records = session.run(
            "MATCH (c:Context) RETURN c.id as id, c.name as name, c.text as text, c.embedding as embedding"
        ).data()
        
        # 2. Match Sensors by keywords first (to boost contexts)
        sensor_values = []
        if keywords:
            sensor_query = "MATCH (s:Sensor) WHERE " + " OR ".join(
                [f"toLower(s.value) CONTAINS '{kw}'" for kw in keywords]
            ) + " RETURN s.id as id, s.type as type, s.value as value"
            sensors = session.run(sensor_query).data()
            results["sensors"] = sensors
            sensor_values = [s["value"].lower() for s in sensors]
        
        # Calculate similarities with keyword boost
        scored_contexts = []
        for ctx in ctx_records:
            if ctx["embedding"]:
                sim = cosine_similarity(query_embedding, ctx["embedding"])
                
                # BOOST: If context contains a sensor keyword, boost similarity
                text_lower = ctx["text"].lower() if ctx["text"] else ""
                keyword_boost = 0
                for kw in keywords:
                    if kw in text_lower:
                        keyword_boost = 0.2  # Significant boost for keyword match
                        break
                for sv in sensor_values:
                    if sv in text_lower:
                        keyword_boost = max(keyword_boost, 0.25)  # Even more boost for sensor match
                        break
                
                boosted_sim = sim + keyword_boost
                
                if boosted_sim > SIMILARITY_THRESHOLD:
                    scored_contexts.append({
                        "id": ctx["id"],
                        "name": ctx["name"],
                        "text": ctx["text"],
                        "similarity": boosted_sim,
                        "base_sim": sim,
                        "boost": keyword_boost
                    })
        
        # Sort by boosted similarity
        scored_contexts.sort(key=lambda x: x["similarity"], reverse=True)
        results["contexts"] = scored_contexts[:5]  # Return top 5 instead of 3
        
        # 3. Find Actions connected to top Context's Moment
        if results["contexts"]:
            top_ctx_id = results["contexts"][0]["id"]
            actions = session.run(
                "MATCH (c:Context {id: $cid})-[:HAS_MOMENT]->(m:Moment)-[:LED_TO]->(a:Action) "
                "RETURN a.trigger as trigger, a.response as response",
                cid=top_ctx_id
            ).data()
            results["actions"] = actions
        
        # Calculate activation score (confidence)
        ctx_score = results["contexts"][0]["similarity"] if results["contexts"] else 0
        sensor_boost = 0.1 * len(results["sensors"])
        results["score"] = min(ctx_score + sensor_boost, 1.0)
    
    driver.close()
    return results


def chitta_quick_chat(query, return_json=False):
    """
    Main entry point for quick Q&A.
    
    Args:
        query: User question
        return_json: If True, return structured dict instead of string
    
    Returns:
        If return_json: {"response": str, "confidence": float, "should_fallthrough": bool}
        Else: Human-readable response string
    """
    # Search memory
    memory = chitta_search(query)
    confidence = memory["score"]
    should_fallthrough = confidence < CONFIDENCE_THRESHOLD
    
    # Build context from memory
    context_parts = []
    if memory["contexts"]:
        context_parts.append("Memory contexts (search results):")
        for ctx in memory["contexts"]:
            # Include more text for better extraction
            context_parts.append(f"### {ctx['name']}\n{ctx['text'][:800]}")
    
    if memory["sensors"]:
        sensor_str = ", ".join([s["value"] for s in memory["sensors"]])
        context_parts.append(f"\nEntities mentioned in query: {sensor_str}")
    
    if memory["actions"]:
        action_str = "; ".join([a["response"] for a in memory["actions"]])
        context_parts.append(f"\nStanding directives: {action_str}")
    
    grounded_context = "\n".join(context_parts)
    
    # System prompt - more explicit about extraction
    system = """You are Manas. Extract and answer from the memory contexts below.

CRITICAL RULES:
1. SEARCH the contexts for the answer - it IS there if contexts were found
2. Look for patterns like "**Name:** Role" or "Name: Description"
3. Give a SHORT, DIRECT answer: "X is Y." or "X does Y."
4. ONLY say "Data Missing" if there are NO contexts provided
5. Do NOT add explanations or caveats"""
    
    # Build prompt
    if grounded_context:
        prompt = f"""{grounded_context}

QUESTION: {query}

Extract the answer from the contexts above. One sentence max."""
    else:
        prompt = f"Query: {query}\n\nNo memory found. Say 'Data Missing'."
    
    # Generate response
    response = ollama_generate(prompt, system)
    
    if return_json:
        return {
            "response": response,
            "confidence": confidence,
            "should_fallthrough": should_fallthrough,
            "contexts_found": len(memory["contexts"]),
            "sensors_found": len(memory["sensors"])
        }
    else:
        debug = f"\n\n[Score: {confidence:.2f} | Contexts: {len(memory['contexts'])} | Sensors: {len(memory['sensors'])}]"
        return response + debug


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 quick-chat.py [--json] 'your question'")
        sys.exit(1)
    
    # Parse args
    args = sys.argv[1:]
    json_output = False
    if "--json" in args:
        json_output = True
        args.remove("--json")
    
    if not args:
        print("Usage: python3 quick-chat.py [--json] 'your question'")
        sys.exit(1)
    
    query = " ".join(args)
    result = chitta_quick_chat(query, return_json=json_output)
    
    if json_output:
        print(json.dumps(result))
    else:
        print(result)
