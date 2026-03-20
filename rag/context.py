# Context assembler: formats raw Neo4j result rows into a structured string for the LLM.
# Takes the list of result rows from retriever.py and converts them into a readable context block.
# Groups facts by entity (e.g., all properties and relations of a Drug together).
# Collects and deduplicates source citations: list of {source_file, page_number} across all rows.
# Returns: { "context": "<formatted text>", "citations": [{"file": ..., "page": ...}, ...] }
# If result rows are empty, returns context="" and citations=[].
