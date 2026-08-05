"""
voice/voice_training.py
=======================
Iterative Voice Training Engine, Queue & RTX 5050 VRAM Scheduler for Vivy AI.
Manages custom voice cloning training epochs without causing memory contention:
  1. Multi-Upload Training Queue to prevent concurrent VRAM saturation.
  2. Automatic suspension of non-essential background tasks during active training epochs.
  3. Semantic visual progress tracking (Preparing Dataset -> Training Epochs -> Building Index -> Evaluating Model).
  4. Interactive Retrain capability to incrementally improve similarity scores (e.g., 82% -> 91% -> 95%).
  5. Post-training evaluation and automatic Left/Right comparison audio preparation.
"""

import os
import time
import uuid
import queue
import threading
from typing import Dict, Any, Optional, List

from .voice_validation import VoiceQualityAnalyzer
from .voice_preview import get_voice_preview_engine
from .voice_manager import get_voice_manager

class VoiceTrainingManager:
    """Coordinates iterative custom voice training jobs with VRAM protection and real-time UI synchronization."""

    def __init__(self):
        self._lock = threading.RLock()
        self.job_queue: queue.Queue = queue.Queue()
        self.active_job: Optional[Dict[str, Any]] = None
        self.is_busy = False
        self.vram_suspended_background_tasks = False
        self.validator = VoiceQualityAnalyzer(retrain_threshold=75)
        self.preview_engine = get_voice_preview_engine()
        self.mgr = get_voice_manager()
        
        # Real-time progress tracker for UI monitoring
        self.progress_state = {
            "job_id": None,
            "status": "idle", # idle, queuing, training, evaluating, finished, error
            "stage_label": "Standby",
            "percent": 0,
            "message": "Ready to train new vocal identities.",
            "last_completed_job": None
        }

        # Start worker thread
        self.worker_thread = threading.Thread(target=self._queue_consumer_loop, daemon=True, name="VoiceTrainingWorker")
        self.worker_thread.start()

    def enqueue_training_job(
        self,
        audio_path: str,
        voice_name: str,
        voice_id: Optional[str] = None,
        iterations: int = 1,
        is_retrain: bool = False,
        base_quality: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Submits a custom voice training or retraining job into the sequential VRAM queue.
        Returns initial job descriptor and tracking ID.
        """
        with self._lock:
            jid = f"job_{uuid.uuid4().hex[:8]}"
            vid = voice_id or f"voice_{uuid.uuid4().hex[:8]}"
            
            job_spec = {
                "job_id": jid,
                "voice_id": vid,
                "voice_name": voice_name.strip() or "Custom Voice",
                "audio_path": audio_path,
                "iterations": max(1, iterations),
                "is_retrain": is_retrain,
                "base_quality": base_quality,
                "status": "queued",
                "submitted_at": time.time()
            }

            self.job_queue.put(job_spec)
            
            if not self.is_busy:
                self.progress_state.update({
                    "job_id": jid,
                    "status": "queuing",
                    "stage_label": "Queuing Job",
                    "percent": 5,
                    "message": f"Job queued for '{job_spec['voice_name']}'..."
                })
                self.mgr.notify_realtime_event("training_queued", dict(self.progress_state))

            print(f"[VoiceTraining] Enqueued job {jid} for voice '{job_spec['voice_name']}' (Retrain={is_retrain})")
            return job_spec

    def get_progress(self) -> Dict[str, Any]:
        """Returns real-time training progress and stage diagnostics for the web interface."""
        with self._lock:
            return dict(self.progress_state)

    def _suspend_background_vram_tasks(self) -> None:
        """
        Signals system hardware schedulers to suspend proactive background LLM/perception tasks
        to allocate dedicated RTX 5050 6GB VRAM capacity to RVC neural training.
        """
        self.vram_suspended_background_tasks = True
        print("[VoiceTraining] VRAM Governor: Suspending non-essential background tasks for training execution.")
        try:
            from agi.cognitive_core import GeneralCognitiveCore
            # Flag system as busy to defer self-evolution background cycles
            GeneralCognitiveCore._rvc_training_lock_active = True
        except Exception as e:
            print(f"[VoiceTraining] VRAM suspend signal warning: {e}")

    def _resume_background_vram_tasks(self) -> None:
        """Restores background proactive processing once RVC training epochs conclude."""
        self.vram_suspended_background_tasks = False
        print("[VoiceTraining] VRAM Governor: Training complete. Restoring normal background task scheduling.")
        try:
            from agi.cognitive_core import GeneralCognitiveCore
            GeneralCognitiveCore._rvc_training_lock_active = False
        except Exception as e:
            print(f"[VoiceTraining] VRAM resume signal warning: {e}")

    def _queue_consumer_loop(self) -> None:
        """Continuous consumer loop processing training jobs sequentially."""
        while True:
            try:
                job = self.job_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            with self._lock:
                self.is_busy = True
                self.active_job = job

            try:
                self._suspend_background_vram_tasks()
                self._execute_training_lifecycle(job)
            except Exception as err:
                print(f"[VoiceTraining] Fatal error in training loop for job {job.get('job_id')}: {err}")
                with self._lock:
                    self.progress_state.update({
                        "status": "error",
                        "stage_label": "Training Failed",
                        "percent": 0,
                        "message": f"Error during training: {err}"
                    })
                    self.mgr.notify_realtime_event("training_failed", dict(self.progress_state))
            finally:
                self._resume_background_vram_tasks()
                with self._lock:
                    self.is_busy = False
                    self.active_job = None
                self.job_queue.task_done()

    def _ensure_pretrained_weights_exist(self, base_dir: str):
        weights_dir = os.path.join(base_dir, "rvc_cpu", "assets", "pretrained_v2")
        os.makedirs(weights_dir, exist_ok=True)
        import urllib.request
        
        urls = {
            "f0G40k.pth": "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/pretrained_v2/f0G40k.pth",
            "f0D40k.pth": "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/pretrained_v2/f0D40k.pth"
        }
        for name, url in urls.items():
            path = os.path.join(weights_dir, name)
            if not os.path.exists(path):
                self._update_stage("sys", "downloading", f"Downloading {name}", 5, f"Fetching pre-trained weights ({name}) to accelerate convergence...")
                print(f"[VoiceTraining] Downloading {name} from huggingface...")
                try:
                    urllib.request.urlretrieve(url, path)
                except Exception as e:
                    print(f"[VoiceTraining] Failed to download {name}: {e}")

    def _run_subprocess_stream(self, jid: str, cmd: list, cwd: str, stage_label: str, is_train_stage: bool = False):
        import subprocess
        import re
        import time
        import psutil
        
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            has_nvml = True
        except:
            has_nvml = False
            
        process = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        
        epoch_pattern = re.compile(r"Epoch\s+(\d+)/(\d+)")
        loss_pattern = re.compile(r"loss_g:\s*([\d\.]+).*?loss_d:\s*([\d\.]+)")
        
        start_time = time.time()
        last_update = time.time()
        
        for line in process.stdout:
            line = line.strip()
            if not line: continue
            
            now = time.time()
            if now - last_update > 0.5 or is_train_stage:
                epoch_match = epoch_pattern.search(line)
                loss_match = loss_pattern.search(line)
                
                stats = {
                    "cpu_percent": psutil.cpu_percent(),
                    "ram_percent": psutil.virtual_memory().percent,
                    "elapsed_sec": round(now - start_time, 1)
                }
                
                if has_nvml:
                    try:
                        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                        util_rates = pynvml.nvmlDeviceGetUtilizationRates(handle)
                        temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                        stats["gpu_util"] = util_rates.gpu
                        stats["gpu_mem_gb"] = round(mem_info.used / (1024**3), 2)
                        stats["gpu_temp"] = temp
                    except:
                        pass
                
                with self._lock:
                    if "system_stats" not in self.progress_state:
                        self.progress_state["system_stats"] = {}
                    self.progress_state["system_stats"].update(stats)
                    
                    if is_train_stage:
                        if epoch_match:
                            cur_ep, total_ep = int(epoch_match.group(1)), int(epoch_match.group(2))
                            self.progress_state["system_stats"]["epoch"] = cur_ep
                            self.progress_state["system_stats"]["total_epochs"] = total_ep
                            if cur_ep > 0:
                                time_per_epoch = (now - start_time) / cur_ep
                                rem_epochs = total_ep - cur_ep
                                self.progress_state["system_stats"]["eta_sec"] = round(rem_epochs * time_per_epoch, 1)
                        if loss_match:
                            self.progress_state["system_stats"]["loss_g"] = float(loss_match.group(1))
                            self.progress_state["system_stats"]["loss_d"] = float(loss_match.group(2))
                            
                    self.mgr.notify_realtime_event("training_progress", dict(self.progress_state))
                
                last_update = now
                
        process.wait()
        if process.returncode != 0:
            raise RuntimeError(f"Subprocess failed with code {process.returncode} in stage {stage_label}")

    def _execute_training_lifecycle(self, job: Dict[str, Any]) -> None:
        """Executes genuine RVC subprocess training pipeline."""
        import subprocess
        import sys
        import shutil
        import glob
        
        jid = job["job_id"]
        vid = job["voice_id"]
        vname = job["voice_name"]
        audio_path = job["audio_path"]
        iters = job["iterations"]
        is_retrain = job["is_retrain"]

        print(f"[VoiceTraining] Starting genuine RVC job {jid} ({vname}) - Epochs: {iters}")
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rvc_dir = os.path.join(base_dir, "rvc_cpu")
        python_exe = sys.executable
        
        self._ensure_pretrained_weights_exist(base_dir)

        # 1. Dataset Analysis (Before Training)
        self._update_stage(jid, "training", "Preparing Dataset", 10, "Setting up experiment workspace and analyzing audio...")
        dataset_audit = self.validator.analyze_audio_sample(audio_path)
        if not dataset_audit["valid"]:
            raise RuntimeError(f"Dataset Validation Failed: {dataset_audit['message']}")
            
        stats = dataset_audit.get("dataset_stats", {})
        duration_sec = stats.get("total_duration_sec", 60.0)
        rec_epochs = stats.get("recommended_epochs", iters)
        
        # Override iters if too low for the dataset size
        if iters < rec_epochs and not is_retrain:
            iters = rec_epochs
            print(f"[VoiceTraining] Auto-scaled epochs to {iters} based on dataset duration.")

        exp_dir = os.path.join(rvc_dir, "logs", vid)
        raw_dir = os.path.join(exp_dir, "0_raw")
        os.makedirs(raw_dir, exist_ok=True)
        target_audio = os.path.join(raw_dir, "source.wav")
        shutil.copy2(audio_path, target_audio)

        # Stage 1: Pre-processing
        self._update_stage(jid, "training", "Pre-processing", 20, "Slicing and normalizing audio dataset...")
        self._run_subprocess_stream(jid, [
            python_exe, "infer/modules/train/preprocess.py",
            raw_dir, "40000", "4", exp_dir, "False", "3.7"
        ], cwd=rvc_dir, stage_label="Pre-processing")

        # Stage 2: F0 Extraction
        self._update_stage(jid, "training", "F0 Extraction", 30, "Extracting pitch contours via RMVPE...")
        self._run_subprocess_stream(jid, [
            python_exe, "infer/modules/train/extract/extract_f0_print.py",
            exp_dir, "4", "rmvpe"
        ], cwd=rvc_dir, stage_label="F0 Extraction")

        # Stage 3: Feature Extraction (HuBERT)
        self._update_stage(jid, "training", "Feature Extraction", 45, "Generating HuBERT voice embeddings...")
        self._run_subprocess_stream(jid, [
            python_exe, "infer/modules/train/extract_feature_print.py",
            "cpu", "4", "1", exp_dir, "v2"
        ], cwd=rvc_dir, stage_label="Feature Extraction")

        # Stage 4: Neural Network Training
        self._update_stage(jid, "training", "Neural Training", 50, f"Training Voice Model (Epochs: {iters}). This will take time...")
        
        batch_size = "4" # strict for 6GB VRAM
        cache_gpu = "0"
        save_freq = str(max(10, iters // 5))
        
        pg_path = "assets/pretrained_v2/f0G40k.pth"
        pd_path = "assets/pretrained_v2/f0D40k.pth"
        
        if not os.path.exists(os.path.join(rvc_dir, pg_path)):
            pg_path = ""
            pd_path = ""

        self._run_subprocess_stream(jid, [
            python_exe, "infer/modules/train/train.py",
            "-e", vid,
            "-sr", "40k",
            "-f0", "1",
            "-bs", batch_size,
            "-te", str(iters),
            "-se", save_freq,
            "-pg", pg_path,
            "-pd", pd_path,
            "-l", "1",
            "-c", cache_gpu
        ], cwd=rvc_dir, stage_label="Neural Training", is_train_stage=True)

        # Stage 5: Building FAISS Index
        self._update_stage(jid, "training", "Building Index", 85, "Generating FAISS index for timbre preservation...")
        try:
            self._run_subprocess_stream(jid, [
                python_exe, "infer/modules/train/index/train_index.py",
                exp_dir, "v2"
            ], cwd=rvc_dir, stage_label="Building Index")
        except Exception as e:
            print(f"[VoiceTraining] Index building warning: {e}")

        # Extract weights
        weights_out_dir = os.path.join(rvc_dir, "assets", "weights")
        os.makedirs(weights_out_dir, exist_ok=True)
        model_filename = f"{vid}_{vname.lower().replace(' ', '_')}.pth"
        final_model_path = os.path.join(weights_out_dir, model_filename)
        
        trained_pth = os.path.join(weights_out_dir, f"{vid}.pth")
        if os.path.exists(trained_pth):
            shutil.copy2(trained_pth, final_model_path)
        else:
            log_pths = glob.glob(os.path.join(exp_dir, "*.pth"))
            if log_pths:
                shutil.copy2(log_pths[-1], final_model_path)
            else:
                raise RuntimeError("Training failed: .pth file was not generated.")
                
        index_src = os.path.join(exp_dir, f"added_IVF_*.index")
        indexes = glob.glob(index_src)
        if indexes:
            shutil.copy2(indexes[-1], os.path.join(weights_out_dir, f"{vid}_{vname.lower().replace(' ', '_')}.index"))

        # Evaluating Model (Objective Validation)
        self._update_stage(jid, "evaluating", "Objective Validation", 90, "Running benchmark inference and computing acoustic metrics...")
        
        previews = self.preview_engine.prepare_comparison_previews(
            original_audio_path=audio_path,
            model_filename=model_filename,
            voice_id=vid
        )
        
        quality_eval = self.validator.evaluate_model_quality_acoustic(
            original_audio=previews.get("original_file_path", audio_path),
            cloned_audio=previews.get("cloned_file_path", ""),
            model_filename=model_filename,
            training_iterations=iters
        )

        completed_summary = {
            "job_id": jid,
            "voice_id": vid,
            "voice_name": vname,
            "model_filename": model_filename,
            "iterations": iters,
            "quality_audit": quality_eval,
            "comparison_previews": previews,
            "dataset_stats": stats,
            "completed_at": time.time()
        }

        with self._lock:
            self.progress_state.update({
                "status": "finished",
                "stage_label": "Training Complete",
                "percent": 100,
                "message": f"Training completed. Score: {quality_eval.get('overall_score', 0)}%",
                "last_completed_job": completed_summary
            })
            self.mgr.notify_realtime_event("training_finished", dict(self.progress_state))

        print(f"[VoiceTraining] Job {jid} completed successfully.")

    def _update_stage(self, jid: str, status: str, label: str, pct: int, msg: str) -> None:
        with self._lock:
            self.progress_state.update({
                "job_id": jid,
                "status": status,
                "stage_label": label,
                "percent": pct,
                "message": msg
            })
            self.mgr.notify_realtime_event("training_progress", dict(self.progress_state))
        print(f"[VoiceTraining Stage - {label} ({pct}%)] {msg}")

# Singleton Training Manager
_global_trainer = None
_tr_lock = threading.RLock()

def get_voice_training_manager() -> VoiceTrainingManager:
    global _global_trainer
    with _tr_lock:
        if _global_trainer is None:
            _global_trainer = VoiceTrainingManager()
        return _global_trainer
