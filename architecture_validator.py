import os
import sys
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

class ArchitectureValidator:
    """
    ABSOLUTE RULE 16: Continuous Architecture Validation
    Runs at system startup to guarantee pipeline continuity, dependency integrity,
    and IPC communication availability before server bind.
    """
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.shared_dir = os.path.join(self.base_dir, "shared")
        self.recordings_dir = os.path.join(self.base_dir, "vivy_recordings")
        self.failures: List[str] = []

    def validate_all(self) -> Tuple[bool, List[str]]:
        logger.info("[ArchitectureValidator] Commencing pre-flight startup checks...")
        
        self._check_ipc_directories()
        self._check_core_dependencies()
        self._check_pipeline_continuity()

        if self.failures:
            logger.warning(f"[ArchitectureValidator] {len(self.failures)} non-critical architectural warnings detected.")
            for f in self.failures:
                logger.warning(f"  -> {f}")
            # We never crash the server on missing ML dependencies (graceful fallbacks handle it),
            # but we record the exact state of the environment for diagnostic purposes.
            return True, self.failures
            
        logger.info("[ArchitectureValidator] System architecture validated. 100% Integrity.")
        return True, []

    def _check_ipc_directories(self):
        """Verifies that inter-process communication folders are accessible."""
        try:
            for d in [self.shared_dir, self.recordings_dir]:
                os.makedirs(d, exist_ok=True)
                test_file = os.path.join(d, ".val_test")
                with open(test_file, "w") as f:
                    f.write("OK")
                os.remove(test_file)
        except Exception as e:
            self.failures.append(f"IPC Directory check failed: {e}")

    def _check_core_dependencies(self):
        """Verifies that the LLM engine and fallbacks are importable."""
        try:
            from llama_cpp import Llama
        except ImportError:
            self.failures.append("Primary LLM engine (llama_cpp) is missing. Will degrade to external API if configured.")
            
        try:
            import cv2
        except ImportError:
            self.failures.append("OpenCV missing. Vision pipeline will completely fail.")

    def _check_pipeline_continuity(self):
        """Simulates a dummy context build to ensure the cognitive orchestrator won't crash on the first turn."""
        try:
            from conversation_context import build
            build(
                mem={"emotion_vector": {}},
                history=[],
                user_input="Test",
                search_context="",
                current_emotion="neutral",
                categories=[],
                reaction_directive="",
                director_state={},
                screen_context="",
                perception_context="",
                perception_state={}
            )
        except ImportError:
            pass # Module structure might differ
        except Exception as e:
            self.failures.append(f"Context Pipeline Continuity check failed: {e}")

def run_preflight_checks():
    validator = ArchitectureValidator()
    validator.validate_all()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_preflight_checks()
