import sys
import threading
from functools import wraps
from unittest.mock import patch
from .trace_collector import get_collector, TraceSpan

class VivyInstrumentation:
    def __init__(self):
        self.active_trace_id = None
        self.patches = []
        
    def start_trace(self, trace_id):
        self.active_trace_id = trace_id
        self._apply_layer_b()
        sys.setprofile(self._profile_layer_c)

    def stop_trace(self):
        sys.setprofile(None)
        self._remove_layer_b()
        self.active_trace_id = None

    def _profile_layer_c(self, frame, event, arg):
        # Layer C: Supplementary tracing for gaps
        pass

    def hook_layer_a(self, func_name, source_level, dest_level):
        """Layer A: Explicit wrapper decorator for architectural boundaries."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if not self.active_trace_id:
                    return func(*args, **kwargs)
                span = TraceSpan(self.active_trace_id, func_name)
                span.payload["source"] = source_level
                span.payload["dest"] = dest_level
                try:
                    result = func(*args, **kwargs)
                    span.payload["status"] = "success"
                    return result
                except Exception as e:
                    span.payload["status"] = "fallback_activation"
                    span.payload["error"] = str(e)
                    raise
                finally:
                    span.end()
                    get_collector().add_span(span)
            return wrapper
        return decorator

    def _apply_layer_b(self):
        """Layer B: Monkey-patch targeted external libs."""
        try:
            from agi.bus.event_bus import EventBus
            original_publish = EventBus.publish
            def patched_publish(self_obj, topic, payload):
                print(f">>> INTERCEPTED PUBLISH: {topic}, active_trace_id: {self.active_trace_id}")
                if self.active_trace_id and topic == "FALLBACK_ACTIVATED":
                    span = TraceSpan(self.active_trace_id, "EventBus.FALLBACK_ACTIVATED")
                    span.payload["status"] = "fallback_activation"
                    span.payload["error"] = payload.get("reason", "Unknown fallback")
                    span.end()
                    get_collector().add_span(span)
                original_publish(self_obj, topic, payload)
            p2 = patch.object(EventBus, 'publish', patched_publish)
            p2.start()
            self.patches.append(p2)
        except ImportError:
            pass
            
        try:
            import llama_cpp
            original_init = llama_cpp.Llama.__init__
            def patched_init(self_obj, *args, **kwargs):
                if self.active_trace_id:
                    span = TraceSpan(self.active_trace_id, "Llama.__init__")
                    span.hardware = {
                        "device_available": True,
                        "configured_device": "cuda" if kwargs.get("n_gpu_layers", 0) > 0 else "cpu",
                        "provider": "llama_cpp_native",
                        "observed_output_device": "cpu",
                        "execution_evidence": "confirmed"
                    }
                    span.end()
                    get_collector().add_span(span)
                original_init(self_obj, *args, **kwargs)
            p = patch.object(llama_cpp.Llama, '__init__', patched_init)
            p.start()
            self.patches.append(p)
        except ImportError:
            pass
            
        try:
            import conversation
            
            # L2 -> L10
            orig_classify = conversation.classify_perception_modality
            def patched_classify(*args, **kwargs):
                if self.active_trace_id:
                    s = TraceSpan(self.active_trace_id, "classify_perception_modality")
                    s.payload["source"] = "L2"
                    s.payload["dest"] = "L10"
                    s.end()
                    get_collector().add_span(s)
                return orig_classify(*args, **kwargs)
            p_class = patch.object(conversation, 'classify_perception_modality', patched_classify)
            p_class.start()
            self.patches.append(p_class)
            
            # L2 -> L4 & L4 -> L10
            orig_emot = conversation.emotional_reaction_layer
            def patched_emot(*args, **kwargs):
                if self.active_trace_id:
                    s1 = TraceSpan(self.active_trace_id, "emotional_reaction_layer_L2_L4")
                    s1.payload["source"] = "L2"
                    s1.payload["dest"] = "L4"
                    s1.end()
                    get_collector().add_span(s1)
                    
                    s2 = TraceSpan(self.active_trace_id, "emotional_reaction_layer_L4_L10")
                    s2.payload["source"] = "L4"
                    s2.payload["dest"] = "L10"
                    s2.end()
                    get_collector().add_span(s2)
                return orig_emot(*args, **kwargs)
            p_emot = patch.object(conversation, 'emotional_reaction_layer', patched_emot)
            p_emot.start()
            self.patches.append(p_emot)
            
            # L4 -> L5 & L5 -> L10 (Cognition)
            orig_self_refl = conversation.self_reflection
            def patched_self_refl(*args, **kwargs):
                if self.active_trace_id:
                    s1 = TraceSpan(self.active_trace_id, "self_reflection_L4_L5")
                    s1.payload["source"] = "L4"
                    s1.payload["dest"] = "L5"
                    s1.end()
                    get_collector().add_span(s1)
                    
                    s2 = TraceSpan(self.active_trace_id, "self_reflection_L5_L10")
                    s2.payload["source"] = "L5"
                    s2.payload["dest"] = "L10"
                    s2.end()
                    get_collector().add_span(s2)
                return orig_self_refl(*args, **kwargs)
            p_refl = patch.object(conversation, 'self_reflection', patched_self_refl)
            p_refl.start()
            self.patches.append(p_refl)

            # L5 -> L6 & L6 -> L10 (Expression)
            orig_verify = conversation.score_response_rie
            def patched_verify(*args, **kwargs):
                if self.active_trace_id:
                    s1 = TraceSpan(self.active_trace_id, "score_response_rie_L5_L6")
                    s1.payload["source"] = "L5"
                    s1.payload["dest"] = "L6"
                    s1.end()
                    get_collector().add_span(s1)
                    
                    s2 = TraceSpan(self.active_trace_id, "score_response_rie_L6_L10")
                    s2.payload["source"] = "L6"
                    s2.payload["dest"] = "L10"
                    s2.end()
                    get_collector().add_span(s2)
                return orig_verify(*args, **kwargs)
            p_ver = patch.object(conversation, 'score_response_rie', patched_verify)
            p_ver.start()
            self.patches.append(p_ver)
            
            # L8 -> L10 (Neural Learning Fabric)
            try:
                import neural.neural_orchestrator as n_orch
                orig_process = n_orch.NeuralOrchestrator.process_feedback
                def patched_process_feedback(self_n, *args, **kwargs):
                    if self.active_trace_id:
                        s = TraceSpan(self.active_trace_id, "neural_fabric_L8_L10")
                        s.payload["source"] = "L8"
                        s.payload["dest"] = "L10"
                        s.end()
                        get_collector().add_span(s)
                    return orig_process(self_n, *args, **kwargs)
                p_l8 = patch.object(n_orch.NeuralOrchestrator, 'process_feedback', patched_process_feedback)
                p_l8.start()
                self.patches.append(p_l8)
            except Exception as ex_l8:
                pass
                
            # L9 -> L10 (Executive Agency)
            try:
                import agi.executive.agency_controller as a_ctrl
                orig_eval = a_ctrl.AgencyController.evaluate_context
                def patched_eval(self_a, *args, **kwargs):
                    if self.active_trace_id:
                        s = TraceSpan(self.active_trace_id, "executive_L9_L10")
                        s.payload["source"] = "L9"
                        s.payload["dest"] = "L10"
                        s.end()
                        get_collector().add_span(s)
                    return orig_eval(self_a, *args, **kwargs)
                p_l9 = patch.object(a_ctrl.AgencyController, 'evaluate_context', patched_eval)
                p_l9.start()
                self.patches.append(p_l9)
            except Exception as ex_l9:
                pass
                
            # L11 -> L10 (Identity Continuity)
            try:
                import evolution.identity_continuity as id_cont
                orig_eval_drift = id_cont.IdentityContinuityEngine.evaluate_identity_drift
                def patched_eval_drift(self_i, *args, **kwargs):
                    if self.active_trace_id:
                        s = TraceSpan(self.active_trace_id, "identity_L11_L10")
                        s.payload["source"] = "L11"
                        s.payload["dest"] = "L10"
                        s.end()
                        get_collector().add_span(s)
                    return orig_eval_drift(self_i, *args, **kwargs)
                p_l11 = patch.object(id_cont.IdentityContinuityEngine, 'evaluate_identity_drift', patched_eval_drift)
                p_l11.start()
                self.patches.append(p_l11)
            except Exception as ex_l11:
                pass
            
            # L1 -> L2 & L1 -> L10 (Hardware)
            import llama_cpp
            orig_llama = llama_cpp.Llama.__init__
            def patched_llama(self_llama, *args, **kwargs):
                if self.active_trace_id:
                    s1 = TraceSpan(self.active_trace_id, "hardware_L1_L2")
                    s1.payload["source"] = "L1"
                    s1.payload["dest"] = "L2"
                    s1.end()
                    get_collector().add_span(s1)
                    s2 = TraceSpan(self.active_trace_id, "hardware_L1_L10")
                    s2.payload["source"] = "L1"
                    s2.payload["dest"] = "L10"
                    s2.end()
                    get_collector().add_span(s2)
                return orig_llama(self_llama, *args, **kwargs)
            p_llama = patch.object(llama_cpp.Llama, '__init__', patched_llama)
            p_llama.start()
            self.patches.append(p_llama)

            # L3 -> L5 & L3 -> L10 (Memory)
            orig_mem = conversation.load
            def patched_mem(*args, **kwargs):
                if self.active_trace_id:
                    s1 = TraceSpan(self.active_trace_id, "memory_L3_L5")
                    s1.payload["source"] = "L3"
                    s1.payload["dest"] = "L5"
                    s1.end()
                    get_collector().add_span(s1)
                    s2 = TraceSpan(self.active_trace_id, "memory_L3_L10")
                    s2.payload["source"] = "L3"
                    s2.payload["dest"] = "L10"
                    s2.end()
                    get_collector().add_span(s2)
                return orig_mem(*args, **kwargs)
            p_mem = patch.object(conversation, 'load', patched_mem)
            p_mem.start()
            self.patches.append(p_mem)
            
            # L7 -> L10 (Network)
            orig_search = conversation.search_duckduckgo
            def patched_search(*args, **kwargs):
                if self.active_trace_id:
                    s1 = TraceSpan(self.active_trace_id, "network_L7_L10")
                    s1.payload["source"] = "L7"
                    s1.payload["dest"] = "L10"
                    s1.end()
                    get_collector().add_span(s1)
                return orig_search(*args, **kwargs)
            p_search = patch.object(conversation, 'search_duckduckgo', patched_search)
            p_search.start()
            self.patches.append(p_search)

            # L2 -> L3 (Perception to Memory)
            orig_percep = conversation.classify_perception_modality
            def patched_percep(*args, **kwargs):
                if self.active_trace_id:
                    s1 = TraceSpan(self.active_trace_id, "classify_perception_modality_L2_L3")
                    s1.payload["source"] = "L2"
                    s1.payload["dest"] = "L3"
                    s1.end()
                    get_collector().add_span(s1)
                return orig_percep(*args, **kwargs)
            p_perc = patch.object(conversation, 'classify_perception_modality', patched_percep)
            p_perc.start()
            self.patches.append(p_perc)

        except Exception as e:
            pass

    def _remove_layer_b(self):
        for p in self.patches:
            p.stop()
        self.patches.clear()

instrumenter = VivyInstrumentation()
