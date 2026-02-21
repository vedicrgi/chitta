from neo4j import GraphDatabase
import sys

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "vedicrgi2025")

def dump_db():
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
        with driver.session() as session:
            print("--- CONTEXT NODES ---")
            records = session.run("MATCH (c:Context) RETURN c.id as id, c.name as name, c.text as text").data()
            for r in records:
                print(f"ID: {r.get('id')} | Name: {r.get('name')}")
                text = r.get('text', '')
                if text:
                    print(f"Text: {text[:500]}")
                print("-" * 20)
                
            print("\n--- SENSOR NODES ---")
            records = session.run("MATCH (s:Sensor) RETURN s.id as id, s.type as type, s.value as value").data()
            for r in records:
                print(f"ID: {r.get('id')} | Type: {r.get('type')} | Value: {r.get('value')}")
                
            print("\n--- ACTION NODES ---")
            records = session.run("MATCH (a:Action) RETURN a.id as id, a.trigger as trigger, a.response as response").data()
            for r in records:
                print(f"ID: {r.get('id')} | Trigger: {r.get('trigger')} | Response: {r.get('response')}")

        driver.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    dump_db()
