"""GraphRAG engine: retrieval, context assembly and answer generation with citations.

This implementation favors testability: the GraphRAG accepts a neo4j_client and an llm_callable
(llm_callable(prompt: str) -> str). It performs a simple keyword-based retrieval followed by
optional multi-hop neighbor expansion, assembles evidence snippets and citation metadata, then
calls the LLM to generate a citation-first answer. If no evidence is found, it returns a
standardized refusal (QueryResult.empty_refusal()).
"""

from typing import Callable, Dict, List, Optional, Set
import logging
import re

from .models import QueryResult, Citation
from . import prompts

logger = logging.getLogger(__name__)


class GraphRAG:
    """Simple GraphRAG engine.

    Parameters:
    - neo4j_client: client with run_query/find_nodes methods
    - llm_callable: callable(prompt: str) -> str. If not provided, an error is raised when generating answers.
    """

    def __init__(self, neo4j_client, llm_callable: Optional[Callable[[str], str]] = None):
        self.neo4j = neo4j_client
        self.llm = llm_callable

    def _tokenize(self, text: str) -> List[str]:
        return [t for t in re.findall(r"[A-Za-z0-9]+", text.lower()) if len(t) > 2]

    def _retrieve_candidates(self, question: str, top_k: int = 5, max_hops: int = 1) -> List[Dict]:
        """Retrieve candidate nodes and connected context from the graph.

        Strategy:
        1) simple token-match on name properties to find seed nodes
        2) for each seed node, optionally expand neighbors up to max_hops
        3) return a deduplicated list of node property dicts
        """
        tokens = self._tokenize(question)
        if not tokens:
            return []
        # build a cypher that searches for nodes whose name contains any token (case-insensitive)
        # use parameterized tokens list
        tok_params = {f"t{i}": t for i, t in enumerate(tokens)}
        where_clauses = [f"toLower(n.name) CONTAINS ${p}" for p in tok_params.keys()]
        where = " OR ".join(where_clauses)
        cypher = f"MATCH (n) WHERE {where} RETURN DISTINCT n {{ .* }} as node LIMIT {int(top_k)}"
        try:
            rows = self.neo4j.run_query(cypher, params=tok_params)
        except Exception:
            logger.exception("Keyword search query failed; falling back to find_nodes per token")
            rows = []
        nodes = [r["node"] for r in rows] if rows else []

        # expand neighbors if requested
        expanded: List[Dict] = []
        seen_ids: Set[str] = set([n.get("id") for n in nodes if n.get("id")])
        for n in nodes:
            nid = n.get("id")
            if not nid:
                continue
            # find connected nodes up to max_hops
            if max_hops and int(max_hops) >= 1:
                cy = (
                    "MATCH (s {id: $id})-[*1..$hops]-(m) RETURN DISTINCT m { .* } as node LIMIT $lim"
                )
                params = {"id": nid, "hops": int(max_hops), "lim": int(top_k)}
                try:
                    res = self.neo4j.run_query(cy, params=params)
                    for r in res:
                        node = r.get("node")
                        if node and node.get("id") not in seen_ids:
                            expanded.append(node)
                            seen_ids.add(node.get("id"))
                except Exception:
                    logger.exception("Neighbor expansion query failed for node id=%s", nid)
        all_nodes = nodes + expanded
        return all_nodes

    def _assemble_evidence(self, nodes: List[Dict]) -> (List[Dict], List[Dict]):
        """From node property dicts assemble evidence snippets and citation metadata.

        Returns: (evidence_snippets, citations_metadata)
        evidence_snippets: list of {source_id, text}
        citations_metadata: list of {source_id, doc_id, page, excerpt}
        """
        evidence = []
        citations = []
        seen_sids = set()
        for n in nodes:
            props = n or {}
            # determine source id
            sid = props.get("source_id") or props.get("doc_id") or props.get("id")
            if not sid:
                continue
            if sid in seen_sids:
                continue
            seen_sids.add(sid)
            text = props.get("raw_text") or props.get("excerpt") or props.get("name") or ""
            evidence.append({"source_id": sid, "text": text})
            citations.append({"source_id": sid, "doc_id": props.get("doc_id"), "page": props.get("page"), "excerpt": props.get("excerpt") or text})
        return evidence, citations

    def _extract_citation_ids_from_answer(self, answer: str) -> List[str]:
        ids = re.findall(r"\[CITATION:([^\]]+)\]", answer)
        return ids

    def answer_query(self, question: str, top_k: int = 5, max_hops: int = 1) -> QueryResult:
        """Answer a user question using graph retrieval + LLM.

        If no supporting evidence is found, returns QueryResult.empty_refusal().
        """
        nodes = self._retrieve_candidates(question, top_k=top_k, max_hops=max_hops)
        evidence_snippets, citations_meta = self._assemble_evidence(nodes)
        if not evidence_snippets:
            logger.debug("No evidence found for question: %s", question)
            return QueryResult.empty_refusal()

        if not self.llm:
            raise ValueError("No llm_callable provided to GraphRAG. Provide a callable that accepts a prompt and returns text.")

        prompt = prompts.build_answer_prompt(question=question, evidence_snippets=evidence_snippets, citations=citations_meta)
        logger.debug("Sending answer prompt to LLM (evidence count=%s)", len(evidence_snippets))
        raw = self.llm(prompt)
        if raw is None:
            return QueryResult.empty_refusal()
        answer_text = raw.strip()

        # extract citation ids from the answer text
        cited_ids = self._extract_citation_ids_from_answer(answer_text)
        citations_objs: List[Citation] = []
        provenance = []
        sid_to_cit = {c["source_id"]: c for c in citations_meta}
        for sid in cited_ids:
            meta = sid_to_cit.get(sid) or {}
            citations_objs.append(Citation(source_id=sid, doc_id=meta.get("doc_id"), page=meta.get("page"), excerpt=meta.get("excerpt")))
            provenance.append({"source_id": sid, "snippet": next((e["text"] for e in evidence_snippets if e["source_id"] == sid), None)})

        return QueryResult(answer=answer_text, citations=citations_objs, confidence=None, provenance=provenance)


# convenience factory
def from_callable(neo4j_client, llm_callable: Callable[[str], str]) -> GraphRAG:
    return GraphRAG(neo4j_client=neo4j_client, llm_callable=llm_callable)

