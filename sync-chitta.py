#!/usr/bin/env python3
"""sync-chitta.py - Ingest MEMORY.md/IDENTITY.md into Neo4j Chitta graph."""

import os
import re
import hashlib
import json
import urllib.request
from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "vedicrgi2025")
OLLAMA_URL = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text"
WORKSPACE = os.path.expanduser("~/.openclaw/workspace")
FILES = ["IDENTITY.md", "MEMORY.md"]


def get_embedding(text):
    data = json.dumps({"model": EMBED_MODEL, "prompt": text}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["embedding"]


def chunk_markdown(content, filename):
    chunks = []
    current_section = None
    current_content = []
    lines = content.split("\n")
    for line in lines:
        if line.startswith("## "):
            if current_section and current_content:
                text = "\n".join(current_content).strip()
                if text:
                    chunk_id = hashlib.md5(f"{filename}:{current_section}".encode()).hexdigest()[:12]
                    chunks.append({
                        "source": filename,
                        "section": current_section,
                        "text": text,
                        "id": chunk_id
                    })
            current_section = line[3:].strip()
            current_content = []
        else:
            current_content.append(line)
    if current_section and current_content:
        text = "\n".join(current_content).strip()
        if text:
            chunk_id = hashlib.md5(f"{filename}:{current_section}".encode()).hexdigest()[:12]
            chunks.append({
                "source": filename,
                "section": current_section,
                "text": text,
                "id": chunk_id
            })
    return chunks


def extract_sensors(text):
    sensors = []
    pattern = r"\*\*([A-Z][a-z]+):\*\*"
    for match in re.finditer(pattern, text):
        name = match.group(1)
        skip = ["Name", "Role", "Location", "Status", "Goal", "System"]
        if name not in skip:
            sensors.append({"type": "person", "value": name})
    loc = re.search(r"\*\*Location:\*\*\s*([^(]+)", text)
    if loc:
        sensors.append({"type": "location", "value": loc.group(1).strip()})
    seen = set()
    unique = []
    for s in sensors:
        k = s["type"] + ":" + s["value"]
        if k not in seen:
            seen.add(k)
            unique.append(s)
    return unique


def extract_actions(text):
    actions = []
    patterns = [r"YOU MUST ([^.]+)\.", r"Always ([^.]+)\.", r"Never ([^.]+)\."]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            actions.append({"trigger": "directive", "response": match.group(1).strip()})
    return actions[:5]


def chitta_sync_to_neo4j():
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    print("Syncing Chitta (Memory Graph)...")

    all_chunks = []
    for filename in FILES:
        filepath = os.path.join(WORKSPACE, filename)
        if os.path.exists(filepath):
            with open(filepath) as f:
                content = f.read()
            chunks = chunk_markdown(content, filename)
            all_chunks.extend(chunks)
            print(f"  {filename}: {len(chunks)} chunks")

    with driver.session() as session:
        # Incremental sync: do NOT wipe the DB.

        for chunk in all_chunks:
            section_name = chunk["section"][:40]
            print(f"  Processing: {section_name}...")
            emb = get_embedding(chunk["text"][:2000])

            session.run(
                "MERGE (c:Context {id: $id}) "
                "SET c.name = $name, c.source = $src, c.text = $txt, c.embedding = $emb, c.updated_at = datetime()",
                id=chunk["id"], name=chunk["section"], src=chunk["source"], txt=chunk["text"], emb=emb
            )

            mid = "m_" + chunk["id"]
            session.run(
                "MERGE (m:Moment {id: $id}) "
                "ON CREATE SET m.timestamp = datetime(), m.source = $src "
                "SET m.source = $src",
                id=mid, src=chunk["source"]
            )
            session.run(
                "MATCH (c:Context {id: $cid}), (m:Moment {id: $mid}) MERGE (c)-[:HAS_MOMENT]->(m)",
                cid=chunk["id"], mid=mid
            )

            for s in extract_sensors(chunk["text"]):
                sid = hashlib.md5((s["type"] + ":" + s["value"]).encode()).hexdigest()[:12]
                session.run(
                    "MERGE (s:Sensor {id: $id}) SET s.type = $t, s.value = $v",
                    id=sid, t=s["type"], v=s["value"]
                )
                session.run(
                    "MATCH (s:Sensor {id: $sid}), (m:Moment {id: $mid}) MERGE (s)-[:OBSERVED_IN]->(m)",
                    sid=sid, mid=mid
                )

            for i, a in enumerate(extract_actions(chunk["text"])):
                aid = "a_" + chunk["id"] + "_" + str(i)
                session.run(
                    "MERGE (a:Action {id: $id}) SET a.trigger = $t, a.response = $r",
                    id=aid, t=a["trigger"], r=a["response"]
                )
                session.run(
                    "MATCH (m:Moment {id: $mid}), (a:Action {id: $aid}) MERGE (m)-[:LED_TO]->(a)",
                    mid=mid, aid=aid
                )

    with driver.session() as session:
        result = session.run(
            "MATCH (c:Context) WITH count(c) as ctx "
            "MATCH (m:Moment) WITH ctx, count(m) as mom "
            "MATCH (s:Sensor) WITH ctx, mom, count(s) as sen "
            "MATCH (a:Action) RETURN ctx, mom, sen, count(a) as act"
        ).single()
        ctx = result["ctx"]
        mom = result["mom"]
        sen = result["sen"]
        act = result["act"]
        print(f"\nComplete! Contexts:{ctx} Moments:{mom} Sensors:{sen} Actions:{act}")
    driver.close()


if __name__ == "__main__":
    chitta_sync_to_neo4j()
