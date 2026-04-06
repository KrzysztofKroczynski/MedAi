"""rag.models

Typed lightweight models used across the rag package:
- Citation
- NodeModel
- RelationshipModel
- ExtractionResult
- QueryResult

Includes simple serialization helpers for Neo4j and LLM IO.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import hashlib
import uuid


def _stable_uuid(*parts: str) -> str:
    """Generate a stable uuid-like id from provided parts.
    This is useful for idempotent ingestion (document_id + chunk_id + text_hash).
    """
    h = hashlib.sha256("|".join([p or "" for p in parts]).encode("utf-8")).hexdigest()
    # return shortened but stable id
    return h[:32]


@dataclass
class Citation:
    source_id: str
    doc_id: Optional[str] = None
    page: Optional[int] = None
    excerpt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "doc_id": self.doc_id,
            "page": self.page,
            "excerpt": self.excerpt,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Citation":
        return Citation(
            source_id=d.get("source_id"),
            doc_id=d.get("doc_id"),
            page=d.get("page"),
            excerpt=d.get("excerpt"),
        )


@dataclass
class NodeModel:
    id: str
    labels: List[str]
    properties: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def make_id(*parts: str) -> str:
        return _stable_uuid(*parts)

    def to_neo4j_map(self) -> Dict[str, Any]:
        """Return a dict suitable for use as Neo4j node parameters.
        Leaves label handling to the caller (driver cypher).
        """
        params = {"id": self.id}
        params.update(self.properties)
        return params

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "labels": self.labels, "properties": self.properties}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "NodeModel":
        return NodeModel(id=d["id"], labels=d.get("labels", []), properties=d.get("properties", {}))


@dataclass
class RelationshipModel:
    id: str
    start_id: str
    end_id: str
    rel_type: str
    properties: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def make_id(*parts: str) -> str:
        return _stable_uuid(*parts, uuid.uuid4().hex)

    def to_neo4j_map(self) -> Dict[str, Any]:
        params = {"id": self.id, "start_id": self.start_id, "end_id": self.end_id}
        params.update(self.properties)
        return params

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "start_id": self.start_id,
            "end_id": self.end_id,
            "rel_type": self.rel_type,
            "properties": self.properties,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RelationshipModel":
        return RelationshipModel(
            id=d["id"],
            start_id=d["start_id"],
            end_id=d["end_id"],
            rel_type=d.get("rel_type") or d.get("type"),
            properties=d.get("properties", {}),
        )


@dataclass
class ExtractionResult:
    nodes: List[NodeModel] = field(default_factory=list)
    relationships: List[RelationshipModel] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "relationships": [r.to_dict() for r in self.relationships],
            "citations": [c.to_dict() for c in self.citations],
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ExtractionResult":
        return ExtractionResult(
            nodes=[NodeModel.from_dict(n) for n in d.get("nodes", [])],
            relationships=[RelationshipModel.from_dict(r) for r in d.get("relationships", [])],
            citations=[Citation.from_dict(c) for c in d.get("citations", [])],
            metadata=d.get("metadata", {}),
        )


@dataclass
class QueryResult:
    answer: str
    citations: List[Citation] = field(default_factory=list)
    confidence: Optional[float] = None
    provenance: Optional[List[Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "citations": [c.to_dict() for c in self.citations],
            "confidence": self.confidence,
            "provenance": self.provenance,
        }

    @staticmethod
    def empty_refusal() -> "QueryResult":
        return QueryResult(
            answer=(
                "I cannot find sufficient evidence in the indexed documents to answer this question. "
                "Please consult a healthcare professional."
            ),
            citations=[],
            confidence=0.0,
            provenance=None,
        )

