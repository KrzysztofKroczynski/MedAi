# Shared Neo4j driver singleton.
# Reads NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD from environment variables.
# Exposes a get_driver() function that returns a connected neo4j.GraphDatabase.driver instance.
# Should handle connection retries on startup (Neo4j may still be initializing).
