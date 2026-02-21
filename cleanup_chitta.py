from neo4j import GraphDatabase

NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "vedicrgi2025")

BAD_STRINGS = ["NO_ANSWER_YET", "NO_SIGNAL_HERE", "NO_REPLY", "NO_IMAGE_FOUND", "NO RESPONSE YET"]

def cleanup_db():
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver.session() as session:
        for s in BAD_STRINGS:
            print(f"Cleaning up nodes containing: {s}")
            # Delete Context nodes and their relationships
            # Also delete connected Moment and Action if they are orphans (though Moments are usually 1:1 with Context here)
            query = """
            MATCH (c:Context)
            WHERE c.id STARTS WITH 'sess_' AND (toUpper(c.text) CONTAINS toUpper($s) OR toUpper(c.name) CONTAINS toUpper($s))
            OPTIONAL MATCH (c)-[:HAS_MOMENT]->(m:Moment)
            OPTIONAL MATCH (m)-[:LED_TO]->(a:Action)
            DETACH DELETE c, m, a
            """
            result = session.run(query, s=s)
            print(f"  Done.")

    driver.close()

if __name__ == "__main__":
    cleanup_db()
