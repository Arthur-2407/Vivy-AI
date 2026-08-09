"""
language/hybrid_translation_engine.py
=======================================
Hybrid Translation Engine — Brain of the multilingual system.

Decides per-turn whether NLLB-200 (CPU/CUDA adaptive, CTranslate2) or
Qwen3 handles translation/localization, then validates confidence and applies
Vivy's personality preservation pass if needed.

Adaptive Hardware Strategy (RTX 5050 6GB + Intel Core):
  - NLLB-200 dynamically switches between GPU (CUDA int8_float16) and CPU (int8)
    based on real-time system load, free VRAM, and predicted CPU spikes.
  - When VRAM is plentiful (>1200MB free) and GPU utilization is low, NLLB runs on CUDA (~15-30ms).
  - When Qwen3 or XTTS/RVC spike GPU memory under heavy load, NLLB automatically pivots to CPU (~300MB RAM) to eliminate bottlenecking and hardware contention.
  - NLLB model auto-downloads from HuggingFace Hub and converts to CTranslate2 format on first use.
"""

import os
import re
import time
import logging
import threading
import subprocess
from collections import OrderedDict
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class HybridTranslationEngine:
    """
    Orchestrates NLLB-200 (Adaptive CPU/CUDA) and Qwen3 for multilingual translation.

    Pipeline:
      1. classify_complexity(text) → rule key from config
      2. decide_engine(rule_key)   → "nllb" | "qwen" | "nllb_then_qwen_validate"
      3. _ensure_nllb_loaded()     → checks real-time system load and pivots CPU/CUDA device adaptively
      4. translate(text, src, tgt) → (translated_text, confidence)
      5. If confidence < threshold → Qwen review pass
      6. If personality_preservation_pass enabled → Qwen warms up literal translation
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._nllb_translator = None      # ctranslate2.Translator, lazy-loaded & adaptive
        self._nllb_tokenizer = None       # transformers tokenizer, lazy-loaded
        self._nllb_loaded = False
        self._nllb_load_attempted = False
        self._current_device: Optional[str] = None
        self._last_device_check_time: float = 0.0

        # Load config
        self._cfg: Dict[str, Any] = {}
        self._nllb_cfg: Dict[str, Any] = {}
        self._hybrid_cfg: Dict[str, Any] = {}
        self._cache_cfg: Dict[str, Any] = {}
        self._lang_map: Dict[str, str] = {}
        self._reload_config()

        # LRU translation cache
        self._cache: OrderedDict = OrderedDict()
        self._cache_ttl: float = float(self._cache_cfg.get("ttl_seconds", 3600))
        self._cache_max: int = int(self._cache_cfg.get("max_entries", 500))
        self._cache_enabled: bool = self._cache_cfg.get("enabled", True)

        # Validator
        from language.translation_validator import get_translation_validator
        self._validator = get_translation_validator()

        logger.info("[HybridTranslationEngine] Initialized (Adaptive Hybrid NLLB load switcher active).")

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _reload_config(self):
        try:
            from config.config_manager import get_config_manager
            cfg = get_config_manager()
            eng = cfg.get("multilingual_engine", {})
            self._nllb_cfg = eng.get("nllb_model", {})
            self._hybrid_cfg = eng.get("hybrid_translation", {})
            self._cache_cfg = eng.get("translation_cache", {})
            self._lang_map = self._nllb_cfg.get("nllb_lang_map", {})
        except Exception as err:
            logger.warning(f"[HybridTranslationEngine] Config reload warning: {err}")

    # ------------------------------------------------------------------
    # Adaptive System Load & Resource Inspection
    # ------------------------------------------------------------------

    def _inspect_system_resources(self) -> Tuple[str, str, Dict[str, Any]]:
        """
        Dynamically inspect system load (VRAM, GPU utilization, and predicted CPU spikes)
        to decide whether NLLB should execute on CUDA or CPU. Zero hardcoded thresholds.
        Returns: (target_device, target_compute_type, load_stats_dict)
        """
        mode = str(self._nllb_cfg.get("device", "hybrid")).lower()
        cpu_compute = self._nllb_cfg.get("cpu_compute_type", self._nllb_cfg.get("compute_type", "int8"))
        cuda_compute = self._nllb_cfg.get("cuda_compute_type", "int8_float16")

        if mode != "hybrid" and mode != "auto":
            compute = cuda_compute if mode == "cuda" else cpu_compute
            return mode, compute, {"mode": mode, "reason": "static_config"}

        adaptive_cfg = self._nllb_cfg.get("adaptive_load_switching", {})
        min_free_vram = float(adaptive_cfg.get("min_free_vram_mb", 1200))
        max_gpu_util = float(adaptive_cfg.get("max_gpu_utilization_percent", 85))
        max_cpu_load = float(adaptive_cfg.get("max_cpu_load_percent", 75))

        stats: Dict[str, Any] = {"mode": "hybrid"}

        # Check if CTranslate2 supports CUDA on this runtime
        try:
            import ctranslate2
            cuda_types = ctranslate2.get_supported_compute_types("cuda")
            if not cuda_types:
                return "cpu", cpu_compute, {"reason": "ctranslate2_no_cuda", **stats}
            if cuda_compute not in cuda_types:
                cuda_compute = "int8" if "int8" in cuda_types else "float16"
        except Exception:
            return "cpu", cpu_compute, {"reason": "ctranslate2_check_error", **stats}

        # Inspect real-time GPU hardware via nvidia-smi (non-blocking subprocess)
        gpu_free_mb = -1.0
        gpu_util_pct = 0.0
        try:
            cmd = ["nvidia-smi", "--query-gpu=memory.free,utilization.gpu", "--format=csv,noheader,nounits"]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=0.8).decode("utf-8", errors="ignore").strip()
            if out:
                parts = out.split("\n")[0].split(",")
                if len(parts) >= 2:
                    gpu_free_mb = float(parts[0].strip())
                    gpu_util_pct = float(parts[1].strip())
                    stats["gpu_free_mb"] = gpu_free_mb
                    stats["gpu_util_pct"] = gpu_util_pct
        except Exception as _gpu_err:
            logger.debug(f"[HybridTranslationEngine] GPU metric interrogation silenced: {_gpu_err}")

        # Inspect predicted CPU load from Vivy's existing neural ResourceSchedulerML
        predicted_cpu = 50.0
        try:
            from resource_scheduler_ml import get_resource_scheduler_ml
            scheduler = get_resource_scheduler_ml()
            scheduler.record_usage()
            predicted_cpu = float(scheduler.predict_next_cpu_load())
            stats["predicted_cpu"] = round(predicted_cpu, 1)
        except Exception as _cpu_err:
            try:
                import psutil
                predicted_cpu = float(psutil.cpu_percent(interval=None))
                stats["predicted_cpu_psutil"] = predicted_cpu
            except Exception:
                pass

        # Decision routing logic:
        # 1. If we couldn't detect GPU VRAM or free VRAM is below safe threshold OR GPU is saturated by Qwen/RVC -> switch to CPU
        if gpu_free_mb < min_free_vram or gpu_util_pct >= max_gpu_util:
            stats["decision"] = "cpu_due_to_gpu_load_or_vram_constraint"
            return "cpu", cpu_compute, stats

        # 2. If CPU is predicted to spike (> max_cpu_load) and GPU has available buffer -> preferentially route to CUDA
        if predicted_cpu >= max_cpu_load and gpu_free_mb >= min_free_vram:
            stats["decision"] = "cuda_to_offload_heavy_cpu"
            return "cuda", cuda_compute, stats

        # 3. Optimal nominal conditions: GPU VRAM plentiful (> min_free_vram) -> use high-speed CUDA execution
        stats["decision"] = "cuda_optimal_vram_and_headroom"
        return "cuda", cuda_compute, stats

    # ------------------------------------------------------------------
    # Complexity Classification
    # ------------------------------------------------------------------

    def classify_complexity(self, text: str) -> str:
        """
        Classify input text into a complexity category using config thresholds.
        Returns one of: "simple", "normal", "emotional", "technical", "creative", "code"
        """
        thresholds = self._hybrid_cfg.get("complexity_word_thresholds", {})
        word_count = len(text.split())
        simple_threshold = int(thresholds.get("simple", 5))
        normal_threshold = int(thresholds.get("normal", 30))
        emotional_keywords = thresholds.get("emotional_keywords", [])

        # Code detection
        if re.search(r'```|def |class |import |<html|SELECT |FROM |function ', text):
            return "code"

        # Emotional detection — keywords from config (multilingual)
        if any(kw.lower() in text.lower() for kw in emotional_keywords if kw):
            return "emotional"

        # Length-based
        if word_count <= simple_threshold:
            return "simple"
        if word_count <= normal_threshold:
            return "normal"
        return "normal"  # default for long conversation

    # ------------------------------------------------------------------
    # Engine Decision
    # ------------------------------------------------------------------

    def decide_engine(self, complexity: str) -> str:
        """
        Returns engine decision based on complexity rules from config.
        Possible values: "nllb", "qwen", "nllb_then_qwen_validate"
        """
        rules = self._hybrid_cfg.get("complexity_rules", {})
        return rules.get(complexity, "nllb")

    # ------------------------------------------------------------------
    # NLLB Model Loading & Adaptive Device Switching
    # ------------------------------------------------------------------

    def _ensure_nllb_loaded(self) -> bool:
        """
        Lazily loads NLLB model on first use and performs real-time adaptive
        load switching between CPU and CUDA without blocking or connection breaks.
        Returns True if model is ready, False on failure.
        """
        now = time.time()
        adaptive_cfg = self._nllb_cfg.get("adaptive_load_switching", {})
        check_interval = float(adaptive_cfg.get("check_interval_seconds", 3.0))

        # Fast path if model loaded and check interval has not elapsed
        if self._nllb_loaded and (now - self._last_device_check_time) < check_interval:
            return True

        with self._lock:
            # Recheck inside lock
            now = time.time()
            if self._nllb_loaded and (now - self._last_device_check_time) < check_interval:
                return True
            if self._nllb_load_attempted and not self._nllb_loaded:
                return False  # Previous initial loading attempt failed — don't retry incessantly

            self._nllb_load_attempted = True
            model_id = self._nllb_cfg.get("model_id", "facebook/nllb-200-distilled-600M")
            local_path = self._nllb_cfg.get("local_converted_path", "models/nlp/nllb-200-distilled-600M-ct2")
            inter_threads = int(self._nllb_cfg.get("inter_threads", 4))
            intra_threads = int(self._nllb_cfg.get("intra_threads", 4))

            # Inspect real-time hardware resources to pick optimal device & compute type
            target_device, compute_type, load_stats = self._inspect_system_resources()

            try:
                import ctranslate2
                from transformers import AutoTokenizer

                # Convert model path to absolute path if relative
                abs_local_path = local_path
                if not os.path.isabs(abs_local_path):
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    abs_local_path = os.path.join(base_dir, abs_local_path)

                # Check if converted CTranslate2 binary format exists; if not, auto-download from HuggingFace Hub & convert
                model_bin_path = os.path.join(abs_local_path, "model.bin")
                if not os.path.exists(model_bin_path):
                    logger.info(
                        f"[HybridTranslationEngine] CTranslate2 binary not found at '{abs_local_path}'. "
                        f"Auto-downloading and converting '{model_id}' from HuggingFace Hub..."
                    )
                    print(f"[HybridTranslationEngine] Auto-downloading and converting NLLB model '{model_id}' from HuggingFace Hub...")
                    os.makedirs(abs_local_path, exist_ok=True)
                    converter = ctranslate2.converters.TransformersConverter(model_id)
                    converter.convert(abs_local_path, force=True)
                    logger.info(f"[HybridTranslationEngine] Successfully converted NLLB-200 to CTranslate2 at '{abs_local_path}'.")

                # If already loaded on a different device, perform live adaptive runtime device switch!
                if self._nllb_loaded and self._current_device != target_device:
                    logger.info(
                        f"[HybridTranslationEngine] Adaptive Load Switch: Pivoting NLLB from '{self._current_device.upper()}' "
                        f"to '{target_device.upper()}' (compute={compute_type}, stats={load_stats})."
                    )
                    print(f"[HybridTranslationEngine] Adaptive Load Pivot: NLLB switching -> {target_device.upper()} ({compute_type})")
                    self._nllb_translator = ctranslate2.Translator(
                        abs_local_path,
                        device=target_device,
                        compute_type=compute_type,
                        inter_threads=inter_threads,
                        intra_threads=intra_threads,
                    )
                    self._current_device = target_device
                    self._last_device_check_time = now
                    return True

                # First-time load
                if not self._nllb_loaded:
                    logger.info(f"[HybridTranslationEngine] Loading NLLB translator on {target_device.upper()} ({compute_type})...")
                    t0 = time.time()
                    self._nllb_translator = ctranslate2.Translator(
                        abs_local_path,
                        device=target_device,
                        compute_type=compute_type,
                        inter_threads=inter_threads,
                        intra_threads=intra_threads,
                    )
                    self._nllb_tokenizer = AutoTokenizer.from_pretrained(model_id)
                    self._nllb_loaded = True
                    self._current_device = target_device
                    self._last_device_check_time = now
                    elapsed = time.time() - t0
                    logger.info(
                        f"[HybridTranslationEngine] NLLB ready in {elapsed:.2f}s on {target_device.upper()} ({compute_type}). "
                        f"Adaptive hardware load switching active."
                    )
                    print(f"[HybridTranslationEngine] NLLB-200 loaded on {target_device.upper()} in {elapsed:.2f}s (Adaptive Hybrid Switch active).")
                else:
                    self._last_device_check_time = now

                return True

            except Exception as load_err:
                logger.error(f"[HybridTranslationEngine] NLLB load/switch failed: {load_err}")
                if not self._nllb_loaded:
                    print(f"[HybridTranslationEngine] NLLB unavailable ({load_err}). Falling back to Qwen for translation.")
                return False

    # ------------------------------------------------------------------
    # Translation Cache
    # ------------------------------------------------------------------

    def _cache_key(self, text: str, src: str, tgt: str) -> str:
        return f"{src}|{tgt}|{text[:120]}"

    def _cache_get(self, key: str) -> Optional[str]:
        if not self._cache_enabled:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        result, ts = entry
        if time.time() - ts > self._cache_ttl:
            del self._cache[key]
            return None
        # Move to end (LRU)
        self._cache.move_to_end(key)
        return result

    def _cache_set(self, key: str, value: str):
        if not self._cache_enabled:
            return
        self._cache[key] = (value, time.time())
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Core Translation API
    # ------------------------------------------------------------------

    def translate_with_nllb(
        self, text: str, src_lang: str, tgt_lang: str
    ) -> Tuple[str, float]:
        """
        Translate text using NLLB-200 (Adaptive CPU/CUDA).
        Returns (translated_text, confidence_score).
        Falls back to empty string on failure (caller will use Qwen).
        """
        # Map language codes to NLLB flores200 codes
        src_nllb = self._lang_map.get(src_lang, f"{src_lang}_Latn")
        tgt_nllb = self._lang_map.get(tgt_lang, f"{tgt_lang}_Latn")

        if not self._ensure_nllb_loaded():
            return "", 0.0

        beam_size = int(self._nllb_cfg.get("beam_size", 2))
        max_tokens = int(self._nllb_cfg.get("max_input_tokens", 256))

        try:
            self._nllb_tokenizer.src_lang = src_nllb
            source_tokens = self._nllb_tokenizer.convert_ids_to_tokens(self._nllb_tokenizer.encode(text, truncation=True, max_length=max_tokens))

            # Target language token prefix
            target_prefix = [tgt_nllb]

            result = self._nllb_translator.translate_batch(
                [source_tokens],
                target_prefix=[target_prefix],
                beam_size=beam_size,
            )
            output_tokens = result[0].hypotheses[0]
            
            # The output may include the target prefix, decode it cleanly
            if output_tokens and output_tokens[0] == tgt_nllb:
                output_tokens = output_tokens[1:]
                
            output_ids = self._nllb_tokenizer.convert_tokens_to_ids(output_tokens)
            translated = self._nllb_tokenizer.decode(output_ids, skip_special_tokens=True)

            # Score the translation
            confidence, _ = self._validator.score(text, translated, src_lang, tgt_lang)
            return translated, confidence

        except Exception as tr_err:
            logger.warning(f"[HybridTranslationEngine] NLLB translation error: {tr_err}")
            return "", 0.0

    def translate_with_qwen(
        self, text: str, src_lang: str, tgt_lang: str,
        nllb_draft: str = "", personality_pass: bool = False
    ) -> Tuple[str, float]:
        """
        Translate or review/improve text using Qwen3.
        If nllb_draft is provided, Qwen reviews and improves it.
        If personality_pass=True, Qwen restores Vivy's warmth after literal translation.
        Returns (translated_text, confidence_score).
        """
        try:
            from conversation import llm
            from language.language_config import get_language_config
            lang_cfg = get_language_config()
            profile = lang_cfg.get_profile(tgt_lang)
            tone = profile.get("tone", "warm_friendly")

            if nllb_draft and not personality_pass:
                # Qwen review mode — improve NLLB draft
                prompt = (
                    f"<|im_start|>system\n"
                    f"You are Vivy AI's multilingual quality reviewer. "
                    f"Review the following translation from {src_lang} to {tgt_lang} "
                    f"and improve it if needed. Preserve emotional warmth and natural flow. "
                    f"Return ONLY the improved translation, nothing else.<|im_end|>\n"
                    f"<|im_start|>user\n"
                    f"Original ({src_lang}): {text}\n"
                    f"Draft translation ({tgt_lang}): {nllb_draft}\n"
                    f"Improved translation ({tgt_lang}):<|im_end|>\n"
                    f"<|im_start|>assistant\n"
                )
            elif personality_pass and nllb_draft:
                # Personality preservation — make literal translation sound like Vivy
                prompt = (
                    f"<|im_start|>system\n"
                    f"You are Vivy AI. Rephrase this translated text in {tgt_lang} "
                    f"to match your personality: {tone}. "
                    f"Keep the same meaning. Return ONLY the rephrased text.<|im_end|>\n"
                    f"<|im_start|>user\n"
                    f"{nllb_draft}<|im_end|>\n"
                    f"<|im_start|>assistant\n"
                )
            else:
                # Direct Qwen translation (for technical/creative content)
                prompt = (
                    f"<|im_start|>system\n"
                    f"You are Vivy AI's native multilingual speaker. "
                    f"Translate the following text into natural, fluent {tgt_lang}. "
                    f"Match the tone: {tone}. "
                    f"Return ONLY the translation, no explanation.<|im_end|>\n"
                    f"<|im_start|>user\n"
                    f"Translate to {tgt_lang}: \"{text}\"<|im_end|>\n"
                    f"<|im_start|>assistant\n"
                )

            res = llm(prompt, max_tokens=200, temperature=0.15, stop=["<|im_end|>", "<|endoftext|>"])
            translated = res["choices"][0]["text"].strip().strip('"\'')
            if translated:
                confidence, _ = self._validator.score(text, translated, src_lang, tgt_lang)
                return translated, confidence
        except Exception as q_err:
            logger.warning(f"[HybridTranslationEngine] Qwen translation error: {q_err}")

        return "", 0.0

    # ------------------------------------------------------------------
    # Main Public API
    # ------------------------------------------------------------------

    def translate(
        self,
        text: str,
        src_lang: str,
        tgt_lang: str,
        force_engine: Optional[str] = None,
    ) -> Tuple[str, float]:
        """
        Translate text from src_lang to tgt_lang using the hybrid strategy.
        Returns (translated_text, confidence_score).

        force_engine: optionally force "nllb" or "qwen" (for testing/override).
        """
        if not text or not text.strip():
            return text, 1.0

        if src_lang == tgt_lang:
            return text, 1.0

        if not self._hybrid_cfg.get("enabled", True):
            return text, 1.0

        # Cache check
        cache_key = self._cache_key(text, src_lang, tgt_lang)
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.debug(f"[HybridTranslationEngine] Cache hit: {src_lang}→{tgt_lang}")
            return cached, 1.0

        # Engine decision
        complexity = self.classify_complexity(text)
        engine = force_engine or self.decide_engine(complexity)
        logger.info(f"[HybridTranslationEngine] {src_lang}→{tgt_lang} | complexity={complexity} | engine={engine}")

        translated = ""
        confidence = 0.0

        if engine == "nllb":
            translated, confidence = self.translate_with_nllb(text, src_lang, tgt_lang)
            if not translated:
                # NLLB unavailable or failed — Qwen fallback
                translated, confidence = self.translate_with_qwen(text, src_lang, tgt_lang)

        elif engine == "qwen":
            translated, confidence = self.translate_with_qwen(text, src_lang, tgt_lang)

        elif engine == "nllb_then_qwen_validate":
            translated, confidence = self.translate_with_nllb(text, src_lang, tgt_lang)
            if translated and self._validator.needs_qwen_review(confidence):
                logger.info(f"[HybridTranslationEngine] Low confidence ({confidence:.2f}) → Qwen review")
                improved, q_conf = self.translate_with_qwen(
                    text, src_lang, tgt_lang, nllb_draft=translated
                )
                if improved and q_conf >= confidence:
                    translated, confidence = improved, q_conf
            elif not translated:
                translated, confidence = self.translate_with_qwen(text, src_lang, tgt_lang)

        # Personality preservation pass
        if (
            translated
            and self._hybrid_cfg.get("personality_preservation_pass", True)
            and tgt_lang != "en"
            and engine != "qwen"  # Qwen output already has personality
        ):
            try:
                warm, w_conf = self.translate_with_qwen(
                    text, src_lang, tgt_lang,
                    nllb_draft=translated, personality_pass=True
                )
                if warm and w_conf >= confidence * 0.9:
                    translated = warm
            except Exception:
                pass  # Non-fatal — keep original translation

        if translated:
            self._cache_set(cache_key, translated)

        return translated or text, confidence

    def is_nllb_available(self) -> bool:
        """Returns True if NLLB has been successfully loaded."""
        return self._nllb_loaded

    def get_stats(self) -> Dict[str, Any]:
        """Return engine runtime stats for telemetry/diagnostics."""
        return {
            "nllb_loaded": self._nllb_loaded,
            "nllb_load_attempted": self._nllb_load_attempted,
            "current_device": self._current_device,
            "cache_entries": len(self._cache),
            "cache_enabled": self._cache_enabled,
        }


# Module-level singleton
_instance: Optional[HybridTranslationEngine] = None
_init_lock = threading.Lock()


def get_hybrid_translation_engine() -> HybridTranslationEngine:
    global _instance
    if _instance is None:
        with _init_lock:
            if _instance is None:
                _instance = HybridTranslationEngine()
    return _instance
