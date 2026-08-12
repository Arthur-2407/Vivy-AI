"""
Vivy AI — General Cognitive Core Facade
======================================
Unified programmatic bridge integrating all 10 specialized AGI cognitive subsystems
into clean pre-turn synthesis and post-turn experiential learning loops without
disrupting legacy dialogue orchestration or neural model pipelines.
"""

import time
import threading
from typing import Dict, Any, Optional

from agi.blackboard import get_cognitive_blackboard
from agi.world_model import get_world_model
from agi.knowledge_graph import get_knowledge_graph
from agi.belief_engine import get_belief_engine
from agi.meta_cognition import get_meta_cognition
from agi.long_horizon_planner import get_long_horizon_planner
from agi.skill_system import get_skill_system
from agi.learning_engine import get_learning_engine
from agi.experiment_engine import get_experiment_engine
from agi.simulation_engine import get_simulation_engine
from agi.job_scheduler import get_job_scheduler
from agi.tool_router import get_autonomous_tool_router
from agi.model_adaptation_engine import get_model_adaptation_engine
from agi.self_evaluation_loop import get_self_evaluation_loop
from agi.self_modification_engine import get_self_modification_engine

class GeneralCognitiveCore:
    """Singleton orchestration facade governing AGI cognitive processing layers."""
    _instance = None
    _lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "GeneralCognitiveCore":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self.bb = get_cognitive_blackboard()
        self.wm = get_world_model()
        self.kg = get_knowledge_graph()
        self.be = get_belief_engine()
        self.mc = get_meta_cognition()
        self.lp = get_long_horizon_planner()
        self.sk = get_skill_system()
        self.le = get_learning_engine()
        self.ee = get_experiment_engine()
        self.sim = get_simulation_engine()
        self.js = get_job_scheduler()
        self.router = get_autonomous_tool_router()
        self.ad = get_model_adaptation_engine()
        self.sel = get_self_evaluation_loop()
        self.sme = get_self_modification_engine()
        self.turn_count = 0

    def evaluate_pre_turn_cognition(self, user_text: str, mem: dict, perception_state: Optional[dict], initial_plan: dict) -> Dict[str, Any]:
        """
        Synthesizes multimodal perceptions, world models, knowledge triples, beliefs,
        and mental counterfactual simulations before LLM prompt generation.
        Returns enhanced plan modifications.
        """
        with self._lock:
            self.turn_count += 1
            enhanced_plan = dict(initial_plan)
            try:
                # 1. Assimilate real-time context into World Model and Knowledge Graph
                topic_ctx = str(initial_plan.get("topic", "General")).strip()
                self.wm.assimilate_perception_and_context(perception_state or {}, mem, topic_context=topic_ctx)
                self.kg.assimilate_from_memory(mem.get("long_term_facts", {}))

                # 2. Publish initial sensory frames to the Cognitive Blackboard
                # Phase 2 Integration: If upstream drops perception_state, fetch it dynamically
                if not perception_state:
                    try:
                        from perception.fusion_engine import get_global_engine
                        from perception.context_injector import get_perception_diagnostic_block
                        narrative = get_global_engine().get_observation_narrative()
                        snapshot = get_perception_diagnostic_block()
                        perception_state = {"narrative": narrative, "snapshot": snapshot}
                    except Exception:
                        perception_state = {}
                        
                self.bb.publish_state("user_query", user_text, source_engine="CognitiveCore")
                self.bb.publish_state("active_perception", perception_state or {}, source_engine="PerceptionManager")

                # 3. Assert active hypothesis if user displays affective load
                if any(w in user_text.lower() for w in ["help", "bug", "sad", "love", "tired"]):
                    self.bb.assert_hypothesis(f"h_turn_{self.turn_count}", f"User expresses salient emotional or technical need in query: '{user_text[:40]}'", confidence=0.85, source_engine="CognitiveCore")

                # 4. Perform multihop Knowledge Graph query & retrieve authoritative Epistemic Beliefs
                keywords = [w for w in user_text.split() if len(w) > 3]
                kg_hint = self.kg.generate_graph_summary_for_prompt(keywords)
                be_hint = self.be.generate_belief_summary_for_prompt()
                wm_hint = self.wm.generate_prompt_grounding()
                sk_hint = self.sk.generate_skill_prompt_hint()
                le_hint = self.le.get_curiosity_prompt_hint()
                lp_hint = self.lp.get_active_goal_summary()
                sim_hint = ""

                # 5. Execute Internal Counterfactual Simulation (Plan A vs Plan B)
                plan_b = dict(initial_plan)
                plan_b["tone"] = "analytical and highly precise"
                winner_plan, winner_lbl, sim_scores = self.sim.simulate_and_select_plan(user_text, initial_plan, plan_b, mem)
                if sim_scores["score_b"] > sim_scores["score_a"] + 0.1:
                    enhanced_plan["tone"] = winner_plan["tone"]
                sim_hint = self.sim.get_simulation_summary()

                # 6. Aggregate cognitive context blocks and evaluate active scheduled jobs / autonomous tools
                due_jobs = self.js.evaluate_due_jobs()
                job_hint = f"Active due background tasks: {len(due_jobs)}" if due_jobs else ""
                tool_res = self.router.evaluate_and_invoke(user_text, initial_plan)
                tool_hint = f"Autonomous Tool Execution ({tool_res.get('tool_selected')}): {tool_res.get('result')}" if tool_res.get("tool_selected", "none") != "none" else ""

                context_blocks = [blk for blk in [wm_hint, kg_hint, be_hint, sk_hint, le_hint, lp_hint, sim_hint, job_hint, tool_hint] if blk]

                # 6.5 Incorporate Relationship Intelligence Layer (Human Conversation Layer & Internal State Awareness)
                try:
                    from relationship import get_relationship_engine
                    rel_eng = get_relationship_engine()
                    hcl = rel_eng.execute_human_conversation_layer(user_text, mem)
                    enhanced_plan["relationship_intelligence"] = hcl
                    enhanced_plan["internal_state_awareness"] = rel_eng.get_internal_state()
                    if hcl.get("natural_response_directive"):
                        context_blocks.append(hcl["natural_response_directive"])
                except Exception as rel_err:
                    print(f"[GeneralCognitiveCore] Relationship Intelligence pre-turn warning: {rel_err}")

                enhanced_plan["agi_cognitive_grounding"] = "\n".join(context_blocks)
                enhanced_plan["tool_invocation_result"] = tool_res
                enhanced_plan["meta_directive"] = self.mc.generate_meta_reasoning_prompt(user_text, enhanced_plan)

                # 7. Snapshot blackboard state
                enhanced_plan["blackboard_snapshot"] = self.bb.synthesize_cognitive_snapshot()

            except Exception as _err:
                print(f"[GeneralCognitiveCore] Pre-turn exception caught (preserving fallback plan): {_err}")
                
            return enhanced_plan

    def evaluate_post_turn_cognition(self, user_text: str, ai_reply: str, turn_plan: dict, mem: dict, eval_score: float = 0.85) -> None:
        """
        Executes post-turn reflexive evaluations: skill XP upgrades, curiosity study queues,
        belief assimilation, and safe sandbox self-improvement experiments.
        """
        with self._lock:
            try:
                # 1. Update Capability & Skill progression
                success = eval_score >= 0.7
                self.sk.evaluate_and_upgrade_skill("conversational_empathy" if "empath" in str(turn_plan.get("tone","")) else "code_reasoning", success=success)

                # 2. Feed Continual Learning Engine (curiosity & retention buffer)
                topic = turn_plan.get("topic", "General")
                self.le.log_interaction_evaluation(user_text, ai_reply, eval_score, topic=str(topic))

                # 3. Discover declarative user statements to register Epistemic Beliefs
                user_lower = user_text.lower()
                if "i am " in user_lower or "my favorite " in user_lower or "i work " in user_lower or "i prefer " in user_lower:
                    self.be.assert_belief(f"User fact: {user_text}", confidence=0.88, evidence="Direct interaction utterance", category="user_persona")

                # 4. Periodically run Safe Sandbox Experiment to self-optimize cognitive weights
                if self.turn_count % 3 == 0:
                    base_cfg = {"empathy_weight": 1.2, "analytical_weight": 1.0, "latency_cap_ms": 300}
                    cand_cfg = {"empathy_weight": 1.3, "analytical_weight": 1.1, "latency_cap_ms": 280}
                    self.ee.run_sandbox_experiment("cognitive_weight_tuning", base_cfg, cand_cfg)

                # 5. Register high-reward turn experiences with Continual Model Adaptation Engine
                self.ad.register_high_reward_experience(user_text, ai_reply, eval_score, [str(topic)])
                self.ad.execute_controlled_adaptation_cycle()

                # 6. Execute Relationship Intelligence Self-Reflection & Experiential Learning Loop
                try:
                    from relationship import get_relationship_engine
                    get_relationship_engine().execute_self_reflection_and_learning_loop(user_text, ai_reply, eval_score)
                except Exception as rel_err:
                    print(f"[GeneralCognitiveCore] Relationship Intelligence post-turn warning: {rel_err}")

            except Exception as _err:
                print(f"[GeneralCognitiveCore] Post-turn evaluation exception caught: {_err}")

    def verify_and_refine_response(self, user_text: str, candidate_reply: str, plan: dict, mem: dict) -> str:
        """Invokes Meta-Cognition reflexive loop (Reason->Critique->Improve->Verify)."""
        with self._lock:
            try:
                refined, telemetry = self.mc.evaluate_and_refine(user_text, candidate_reply, plan, mem, max_iterations=1)
                return refined
            except Exception as _err:
                print(f"[GeneralCognitiveCore] Meta verification warning: {_err}")
                return candidate_reply

_global_cognitive_core = None
def get_cognitive_core() -> GeneralCognitiveCore:
    global _global_cognitive_core
    if _global_cognitive_core is None:
        _global_cognitive_core = GeneralCognitiveCore.get_instance()
    return _global_cognitive_core
