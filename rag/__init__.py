"""Public API for rag package."""

from .entity_extractor import EntityExtractor, from_callable as extractor_from_callable
from .graph_rag import GraphRAG, from_callable as grag_from_callable
from .ingest import ingest_chunks, ingest_from_list
from .neo4j_client import Neo4jClient, Neo4jClientContext
from . import models, schema, prompts, utils

__all__ = [
    "EntityExtractor",
    "extractor_from_callable",
    "GraphRAG",
    "grag_from_callable",
    "ingest_chunks",
    "ingest_from_list",
    "Neo4jClient",
    "Neo4jClientContext",
    "models",
    "schema",
    "prompts",
    "utils",
]

__version__ = "0.1.0"
