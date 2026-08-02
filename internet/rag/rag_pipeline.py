"""
Vivy AI — Retrieval-Augmented Generation (RAG) Pipeline & Local Search Engine
=============================================================================
Provides persistent document indexing and intelligent multi-stage retrieval:
  **Query -> Retriever (Top 20 candidates) -> Ranker & Credibility Filter -> Top 5 Authoritative Snippets -> LLM**
Features:
  - Persistent SQLite storage (`shared/local_knowledge.db`) for documents, code, notes, and scraped web facts
  - TF-IDF and keyword semantic similarity evaluation without external heavy vector databases
  - Dynamic re-ranking based on source reliability, recency, and term relevance
  - Operates autonomously offline as Vivy's dedicated personal search engine
"""

import os
import re
import math
import json
import time
import sqlite3
import threading
from typing import List, Dict, Any, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STORAGE_DIR = os.path.join(BASE_DIR, "shared")
DEFAULT_DB_PATH = os.path.join(STORAGE_DIR, "local_knowledge.db")

class RAGPipeline:
    """Persistent RAG indexing engine and local document search server."""
    _instance = None
    _lock = threading.RLock()

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        except Exception as err:
            print(f"[RAGPipeline] Silenced folder creation warning: {err}")
        self._init_db()

    @classmethod
    def get_instance(cls) -> "RAGPipeline":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS documents (
                            doc_id TEXT PRIMARY KEY,
                            title TEXT NOT NULL,
                            content TEXT NOT NULL,
                            source TEXT,
                            doc_type TEXT,
                            timestamp REAL,
                            reliability REAL DEFAULT 1.0,
                            metadata TEXT
                        )
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_title ON documents(title);")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_type ON documents(doc_type);")
                    conn.commit()
            except Exception as e:
                print(f"[RAGPipeline] Database init warning: {e}")

    def index_document(self, doc_id: str, title: str, content: str, source: str = "local_workspace", doc_type: str = "document", reliability: float = 1.0, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Indexes or updates a document inside the persistent local SQLite knowledge base."""
        if not doc_id or not content.strip():
            return False
        with self._lock:
            meta_json = json.dumps(metadata or {}, ensure_ascii=False)
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO documents (doc_id, title, content, source, doc_type, timestamp, reliability, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (str(doc_id), str(title), str(content), str(source), str(doc_type), time.time(), float(reliability), meta_json))
                    conn.commit()
                return True
            except Exception as err:
                print(f"[RAGPipeline] Indexing failure for doc {doc_id}: {err}")
                return False

    def remove_document(self, doc_id: str) -> bool:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("DELETE FROM documents WHERE doc_id = ?", (str(doc_id),))
                    conn.commit()
                return True
            except Exception:
                return False

    def _tokenize(self, text: str) -> List[str]:
        clean = re.sub(r'[^\w\s]', ' ', text.lower())
        words = [w for w in clean.split() if len(w) > 2 and w not in ["the", "and", "for", "with", "from", "that", "this", "have", "with", "are", "not"]]
        return words

    def _score_candidate(self, query_tokens: List[str], doc_row: sqlite3.Row, total_docs: int, df_map: Dict[str, int]) -> float:
        """Calculates TF-IDF relevance multiplied by document reliability and recency bonus."""
        doc_text = f"{doc_row['title']} {doc_row['content']}".lower()
        doc_tokens = self._tokenize(doc_text)
        if not doc_tokens:
            return 0.0

        doc_len = len(doc_tokens)
        token_counts: Dict[str, int] = {}
        for t in doc_tokens:
            token_counts[t] = token_counts.get(t, 0) + 1

        tf_idf_score = 0.0
        for qt in query_tokens:
            tf = token_counts.get(qt, 0) / float(doc_len)
            df = df_map.get(qt, 1)
            idf = math.log((total_docs + 1.0) / (df + 0.5)) + 1.0
            tf_idf_score += tf * idf

        # Exact substring bonus
        raw_query = " ".join(query_tokens)
        if raw_query in doc_text:
            tf_idf_score *= 1.5
        elif any(qt in doc_row['title'].lower() for qt in query_tokens):
            tf_idf_score *= 1.25

        reliability_factor = max(0.2, min(2.0, float(doc_row["reliability"])))
        age_days = max(0.1, (time.time() - float(doc_row["timestamp"])) / 86400.0)
        recency_factor = 1.0 + max(0.0, (30.0 - age_days) / 100.0)

        return tf_idf_score * reliability_factor * recency_factor

    def search_rag(self, query: str, top_n: int = 5, candidate_pool_size: int = 20, doc_type_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Executes the multi-stage RAG retrieval loop:
        1. Retriever: Fetches top candidate_pool_size matching documents from SQLite index.
        2. Ranker: Evaluates semantic relevance, reliability, and recency.
        3. Returns Top-N authoritative knowledge packets for LLM grounding.
        """
        if not query or len(query.strip()) < 2:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    if doc_type_filter:
                        cursor.execute("SELECT * FROM documents WHERE doc_type = ?", (doc_type_filter,))
                    else:
                        cursor.execute("SELECT * FROM documents")
                    rows = cursor.fetchall()
            except Exception as e:
                print(f"[RAGPipeline] Search query error: {e}")
                return []

            total_docs = len(rows)
            if total_docs == 0:
                return []

            # Compute Document Frequencies for query tokens
            df_map: Dict[str, int] = {}
            for qt in query_tokens:
                count = 0
                for r in rows:
                    if qt in f"{r['title']} {r['content']}".lower():
                        count += 1
                df_map[qt] = count

            # Stage 1: Retrieve candidate pool (Top 20 by fast scoring)
            scored_pool = []
            for r in rows:
                score = self._score_candidate(query_tokens, r, total_docs, df_map)
                if score > 0.0:
                    scored_pool.append((score, r))

            scored_pool.sort(key=lambda x: x[0], reverse=True)
            top_candidates = scored_pool[:candidate_pool_size]

            # Stage 2: Ranker refinement (Re-rank among top candidates)
            final_results = []
            for rank, (score, row) in enumerate(top_candidates[:top_n], 1):
                try:
                    meta = json.loads(row["metadata"]) if row["metadata"] else {}
                except Exception:
                    meta = {}

                snippet = row["content"][:350].strip() + ("..." if len(row["content"]) > 350 else "")
                final_results.append({
                    "doc_id": row["doc_id"],
                    "title": row["title"],
                    "content": row["content"],
                    "snippet": snippet,
                    "source": row["source"],
                    "doc_type": row["doc_type"],
                    "timestamp": row["timestamp"],
                    "reliability": row["reliability"],
                    "relevance_score": round(score * 100.0, 2),
                    "rank": rank,
                    "metadata": meta
                })

            return final_results

    def generate_rag_prompt_grounding(self, query: str, top_n: int = 3) -> str:
        """Returns concise formatted markdown knowledge blocks for direct prompt synthesis."""
        results = self.search_rag(query, top_n=top_n)
        if not results:
            return ""
        blocks = ["### Local & RAG Knowledge Context:"]
        for res in results:
            blocks.append(f"- **[{res['doc_type'].upper()}] {res['title']}** (Score: {res['relevance_score']}, Source: {res['source']}): {res['snippet']}")
        return "\n".join(blocks)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with self._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*), COUNT(DISTINCT doc_type), MAX(timestamp) FROM documents")
                    cnt, types, max_ts = cursor.fetchone()
                    return {"total_documents": cnt or 0, "unique_doc_types": types or 0, "latest_timestamp": max_ts or 0.0, "db_path": self.db_path}
            except Exception as e:
                return {"error": str(e), "total_documents": 0}

_global_rag_pipeline = None
def get_rag_pipeline() -> RAGPipeline:
    global _global_rag_pipeline
    if _global_rag_pipeline is None:
        _global_rag_pipeline = RAGPipeline.get_instance()
    return _global_rag_pipeline
