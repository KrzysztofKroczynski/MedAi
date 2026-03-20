# Writes extracted entities and relations into Neo4j.
# Uses MERGE (not CREATE) to avoid duplicates across multiple PDF runs.
# For each entity: MERGE node by (type, name), set/update properties.
# For each relation: MERGE the relationship between the two nodes.
# Attaches source metadata (source_file, page_number) to each node and relationship.
# Should apply Neo4j schema constraints on startup (unique Drug.name, etc.).
