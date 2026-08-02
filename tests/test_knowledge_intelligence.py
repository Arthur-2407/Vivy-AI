"""
Vivy AI — Autonomous Knowledge Acquisition & RAG Intelligence Verification Suite
=================================================================================
Tests newly deployed knowledge engine architectures:
  1. Persistent SQLite RAG Indexing & Top-20 to Top-5 Re-ranking
  2. Multimodal Document & File Extraction (PDF, Word XML, Transcripts, OCR)
"""

import os
import sys
import time
import shutil
import unittest
import tempfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from internet.rag.rag_pipeline import RAGPipeline, get_rag_pipeline
from internet.rag.document_extractor import DocumentExtractor, get_document_extractor
from internet.providers.source_router import SourceRouter, get_source_router
from internet.internet_manager import InternetManager
from internet.search_provider import SearchResult
from internet.verification.quality_evaluator import QualityEvaluator, get_quality_evaluator
from internet.verification.domain_experts import DomainExpertsEngine, get_domain_experts_engine
from internet.consolidation.knowledge_consolidator import KnowledgeConsolidator, get_knowledge_consolidator
from internet.consolidation.continuous_learning_engine import ContinuousLearningEngine, get_continuous_learning_engine
from knowledge_router import get_knowledge_router

class TestKnowledgeIntelligence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_rag.db")
        self.rag = RAGPipeline(db_path=self.db_path)
        self.extractor = DocumentExtractor()
        self.extractor.rag = self.rag  # Connect extractor to test RAG db
        self.router = get_source_router()
        self.manager = InternetManager.get_instance()
        self.evaluator = get_quality_evaluator()
        self.experts = get_domain_experts_engine()
        self.consolidator = get_knowledge_consolidator()
        self.learner = get_continuous_learning_engine()
        self.k_router = get_knowledge_router()

    def tearDown(self):
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_01_rag_indexing_and_ranking(self):
        self.rag.index_document("doc_1", "Python Guide", "Python is an interpreted programming language used for artificial intelligence.", reliability=1.0)
        self.rag.index_document("doc_2", "Cooking Pasta", "Boil pasta in salted water for ten minutes until al dente.", reliability=0.8)
        self.rag.index_document("doc_3", "Deep Learning Transformers", "Transformer neural networks power modern AI language models using attention layers.", reliability=1.2)
        results = self.rag.search_rag("Tell me about python programming and artificial intelligence", top_n=2)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["doc_id"], "doc_1", f"Expected doc_1 as highest rank, got {results[0]['doc_id']}")
        grounding = self.rag.generate_rag_prompt_grounding("transformer networks in AI")
        self.assertIn("Transformer", grounding)

    def test_02_document_extractor_lifecycle(self):
        note_path = os.path.join(self.temp_dir.name, "research_notes.md")
        with open(note_path, "w", encoding="utf-8") as nf:
            nf.write("# AGI Research Notes\nExploring memory consolidation and cross-source verification algorithms.")
        ext_res = self.extractor.extract_and_index_file(note_path, source_label="test_notes")
        self.assertTrue(ext_res["success"], f"File extraction failed: {ext_res}")
        self.assertEqual(ext_res["doc_type"], "markdown_note")
        rag_res = self.rag.search_rag("memory consolidation algorithms")
        self.assertGreaterEqual(len(rag_res), 1)
        self.assertIn("cross-source verification", rag_res[0]["content"])

    def test_03_youtube_transcript_and_ocr_extraction(self):
        yt_res = self.extractor.extract_youtube_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ", title_hint="Neural Architectures")
        self.assertTrue(yt_res["success"])
        self.assertIn("yt_", yt_res["doc_id"])
        ocr_res = self.extractor.index_perceived_multimodal_fact("whiteboard_screenshot", "Architecture diagram showing source router branching to Wikipedia and local KB.", reliability=0.95)
        self.assertTrue(ocr_res)
        search_res = self.rag.search_rag("source router branching Wikipedia")
        self.assertGreaterEqual(len(search_res), 1)
        self.assertEqual(search_res[0]["doc_type"], "multimodal_ocr")

    def test_04_source_router_dispatch(self):
        routes_sci = self.router.route_query("Find me recent arXiv papers on attention mechanisms")
        self.assertIn("academic_literature", routes_sci)
        routes_doc = self.router.route_query("How to implement PyTorch neural networks")
        self.assertIn("official_docs", routes_doc)
        routes_err = self.router.route_query("Why did I get segmentation fault in Qt? How to fix bug")
        self.assertIn("forum_discussion", routes_err)

    def test_05_multi_source_providers(self):
        status = self.manager.get_status()
        registered = status["registered_providers"]
        for required_provider in ["duckduckgo", "web_crawler", "official_docs", "github_package", "academic_literature", "rss_monitor", "forum_discussion", "wikipedia"]:
            self.assertIn(required_provider, registered, f"Missing registration for {required_provider}")
        res_arxiv = self.manager.providers["academic_literature"].search("quantum error correction")
        self.assertGreaterEqual(len(res_arxiv), 1)
        res_docs = self.manager.providers["official_docs"].search("Python decorators usage")
        self.assertGreaterEqual(len(res_docs), 1)
        res_gh = self.manager.providers["github_package"].search("pip install torch")
        self.assertGreaterEqual(len(res_gh), 1)

    def test_06_quality_evaluator_scoring(self):
        raw = [
            SearchResult("Official Fact", "Verified Python API specification from python.org documentation.", "https://docs.python.org", "official_docs", confidence=0.95),
            SearchResult("Unverified Spam", "Maybe try rebooting everything or running sudo rm -rf.", "http://random.forum", "unknown", confidence=0.4)
        ]
        evals = self.evaluator.evaluate_and_rank(raw)
        self.assertEqual(len(evals), 1, "Low-confidence item should be filtered out by threshold")
        self.assertEqual(evals[0]["title"], "Official Fact")
        self.assertGreaterEqual(evals[0]["evidence_count"], 2)
        formatted = self.evaluator.format_verified_context(evals)
        self.assertIn("Verified High-Confidence", formatted)

    def test_07_domain_experts_verification(self):
        consult = self.experts.consult_expert("programming", "PyTorch autograd usage")
        self.assertEqual(consult["domain_expert"], "PROGRAMMING")
        self.assertGreaterEqual(len(consult["sources_consulted"]), 2)
        self.assertIn("VERIFIED", consult["agreement_status"].upper())

    def test_08_knowledge_consolidator_and_personal_graph(self):
        success = self.consolidator.consolidate_verified_fact("Transformer", "uses", "Self Attention", confidence=0.92)
        self.assertTrue(success)
        upd = self.consolidator.update_user_profile("hardware", "memory", "64GB RAM")
        self.assertEqual(upd["status"], "stored")
        summary = self.consolidator.generate_user_profile_context()
        self.assertIn("64GB RAM", summary)

    def test_09_continuous_learning_and_router_integration(self):
        # Test autonomous background learning cycle
        reports = self.learner.run_learning_cycle(max_topics=1)
        self.assertGreaterEqual(len(reports), 1)
        self.assertEqual(reports[0]["status"], "studied_and_verified")

        # Test topic expansion tree
        exp = self.learner.expand_topic_tree("python")
        self.assertGreaterEqual(exp["branches_explored"], 3)

        # Test knowledge_router integration
        dummy_cb = lambda q: f"- **DDG**: Result for {q}"
        routed = self.k_router.route_knowledge_query("python decorators in AI", dummy_cb)
        self.assertIn("DDG", routed)
        self.assertIn("EXPERT", routed.upper())

    def test_10_3d_avatar_expert_and_study_briefing(self):
        # Test 3D_AVATAR_AND_ENGINE domain expert consultation
        avatar_consult = self.experts.consult_expert("3D Avatar", "How to fix Unity UniWindowController shader rigging in Blender")
        self.assertEqual(avatar_consult["domain_expert"], "3D_AVATAR_AND_ENGINE")

        # Perform one silent study cycle to populate the study log
        self.learner.run_learning_cycle(max_topics=1)
        briefing = self.learner.get_recent_learning_summary(hours=24)
        self.assertIn("Autonomous Study Briefing", briefing)

        # Verify router intercepts 'what did you learn yesterday?' queries cleanly
        recap = self.k_router.route_knowledge_query("what did you learn yesterday?", lambda q: "")
        self.assertIn("Autonomous Study Briefing", recap)

if __name__ == "__main__":
    unittest.main()
