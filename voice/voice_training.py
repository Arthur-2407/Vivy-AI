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
from runtime.environment_manager import get_runtime_manager

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
        
        # Real-time progress tracker for UI monitoring, keyed by job_id
        self.progress_states: Dict[str, Dict[str, Any]] = {}

        self.active_pid = None
        self.cancel_requested = False

        self._recover_orphaned_jobs()

        # Start worker thread
        self.worker_thread = threading.Thread(target=self._queue_consumer_loop, daemon=True, name="VoiceTrainingWorker")
        self.worker_thread.start()

    def enqueue_training_job(
        self,
        audio_path: str,
        voice_name: str,
        voice_id: Optional[str] = None,
        iterations: int = 1,
        job_mode: str = "FRESH_TRAINING",
        base_quality: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Submits a custom voice training or retraining job into the sequential VRAM queue.
        Returns initial job descriptor and tracking ID.
        """
        with self._lock:
            jid = f"job_{uuid.uuid4().hex[:8]}"
            if job_mode == "FRESH_TRAINING":
                vid = f"voice_{uuid.uuid4().hex[:8]}"
            else:
                vid = voice_id or f"voice_{uuid.uuid4().hex[:8]}"
            
            job_spec = {
                "job_id": jid,
                "voice_id": vid,
                "voice_name": voice_name.strip() or "Custom Voice",
                "audio_path": audio_path,
                "iterations": max(1, iterations),
                "job_mode": job_mode,
                "base_quality": base_quality,
                "status": "queued",
                "submitted_at": time.time()
            }

            self.job_queue.put(job_spec)
            
            # Always initialize the state for this job
            self.progress_states[jid] = {
                "job_id": jid,
                "status": "queuing" if self.is_busy else "training",
                "stage_label": "Queuing Job" if self.is_busy else "Starting Job",
                "percent": 5,
                "message": f"Job queued for '{job_spec['voice_name']}'..." if self.is_busy else f"Initializing '{job_spec['voice_name']}'..."
            }
            
            if not self.is_busy:
                self.mgr.notify_realtime_event("training_queued", dict(self.progress_states[jid]))

            print(f"[VoiceTraining] Enqueued job {jid} for voice '{job_spec['voice_name']}' (Mode={job_mode})")
            return job_spec

    def get_progress(self, job_id: str) -> Dict[str, Any]:
        """Returns real-time training progress and stage diagnostics for the specified job."""
        with self._lock:
            if not job_id or job_id not in self.progress_states:
                return {
                    "job_id": job_id,
                    "status": "idle",
                    "stage_label": "Standby",
                    "percent": 0,
                    "message": "Ready to train new vocal identities.",
                }
            return dict(self.progress_states[job_id])

    def cancel_training(self):
        """Manually aborts the active training job and kills the process tree."""
        with self._lock:
            if not self.is_busy:
                return False
            self.cancel_requested = True
            
            if self.active_pid:
                try:
                    import psutil
                    parent = psutil.Process(self.active_pid)
                    for child in parent.children(recursive=True):
                        child.terminate()
                    parent.terminate()
                    print(f"[VoiceTraining] Terminated process tree for PID {self.active_pid}")
                except Exception as e:
                    print(f"[VoiceTraining] Error terminating process: {e}")
                
            self.active_pid = None
            
            if self.active_job:
                jid = self.active_job.get("job_id")
                if jid and jid in self.progress_states:
                    self.progress_states[jid].update({
                        "status": "error",
                        "stage_label": "Training Canceled",
                        "percent": 0,
                        "message": "Training was manually aborted by the user."
                    })
            return True

    def _recover_orphaned_jobs(self):
        """Scans the system for running train.py processes from previous server instances and reattaches."""
        import psutil
        for p in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmd = p.info['cmdline']
                if cmd and any("infer/modules/train/train.py" in arg for arg in cmd):
                    vid = None
                    if "-e" in cmd:
                        vid_idx = cmd.index("-e") + 1
                        if vid_idx < len(cmd):
                            vid = cmd[vid_idx]
                    
                    if vid:
                        print(f"[VoiceTraining] Recovered orphaned training process for {vid} (PID: {p.info['pid']})")
                        self.is_busy = True
                        self.active_pid = p.info['pid']
                        
                        # We don't have the original job payload, so we construct a mock one
                        profile = self.mgr.db.get_profile(vid) or {}
                        self.active_job = {
                            "voice_id": vid,
                            "job_id": "orphaned_recovery",
                            "is_retrain": False, # Assume False so cancellation cleans up if needed, though risky. Better to assume based on if it's already in the DB.
                            "voice_name": profile.get("name", "Unknown")
                        }
                        # If profile already has a model_filename, it's likely a retrain
                        if profile.get("model_filename"):
                            self.active_job["job_mode"] = "INCREMENTAL_RETRAINING"
                        else:
                            self.active_job["job_mode"] = "FRESH_TRAINING"

                        self.progress_states["orphaned_recovery"] = {
                            "job_id": "orphaned_recovery",
                            "status": "training",
                            "stage_label": "Neural Training (Recovered)",
                            "percent": 70,
                            "message": "Re-attached to running training process..."
                        }
                        
                        threading.Thread(target=self._tail_orphaned_log, args=(vid, p.info['pid']), daemon=True).start()
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _tail_orphaned_log(self, vid: str, pid: int):
        """Tails the train.log file for an orphaned process until the process exits."""
        import psutil
        import re
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_file = os.path.join(base_dir, "rvc_cpu", "logs", vid, "train.log")
        
        epoch_pattern = re.compile(r"(?:====> Epoch:|Train Epoch:)\s*(\d+)")
        
        try:
            process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return
            
        if not os.path.exists(log_file):
            time.sleep(2) # Give it a moment to create the file
            if not os.path.exists(log_file):
                self._handle_orphaned_exit()
                return
                
        with open(log_file, "r", encoding="utf-8") as f:
            f.seek(0, 2) # Go to the end of the file
            
            while True:
                line = f.readline()
                if not line:
                    if not process.is_running():
                        break
                    time.sleep(0.5)
                    continue
                    
                match = epoch_pattern.search(line)
                if match:
                    epoch = match.group(1)
                    with self._lock:
                        if "orphaned_recovery" in self.progress_states:
                            self.progress_states["orphaned_recovery"].update({
                                "message": f"Recovered Training Epoch {epoch}..."
                            })
                        
        self._handle_orphaned_exit()

    def _handle_orphaned_exit(self):
        """Cleans up after an orphaned process finishes (or is canceled)."""
        if self.cancel_requested:
            self._resume_background_vram_tasks()
            with self._lock:
                self.is_busy = False
                self.active_job = None
                self.active_pid = None
        else:
            # Note: We can't easily trigger the "Building Index" stage for orphaned jobs 
            # because we lost the full state context, but we can set it to finished.
            with self._lock:
                if "orphaned_recovery" in self.progress_states:
                    self.progress_states["orphaned_recovery"].update({
                        "status": "finished",
                        "stage_label": "Training Complete",
                        "percent": 100,
                        "message": "Recovered training process finished successfully."
                    })
                self.is_busy = False
                self.active_job = None
                self.active_pid = None

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
                    jid = job.get('job_id')
                    if jid in self.progress_states:
                        self.progress_states[jid].update({
                            "status": "error",
                            "stage_label": "Training Failed",
                            "percent": 0,
                            "message": f"Error during training: {err}"
                        })
                        self.mgr.notify_realtime_event("training_failed", dict(self.progress_states[jid]))
            finally:
                if getattr(self, "cancel_requested", False) and job:
                    print(f"[VoiceTraining] Cleaning up after canceled job {job.get('job_id')}")
                    if job.get("job_mode") == "FRESH_TRAINING":
                        # Aggressively delete the dataset logs folder if it was a NEW clone
                        vid = job.get("voice_id")
                        if vid:
                            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                            exp_dir = os.path.join(base_dir, "rvc_cpu", "logs", vid)
                            if os.path.exists(exp_dir):
                                try:
                                    import shutil
                                    shutil.rmtree(exp_dir, ignore_errors=True)
                                    print(f"[VoiceTraining] Purged canceled dataset: {exp_dir}")
                                except Exception as cleanup_err:
                                    print(f"[VoiceTraining] Warning: Could not purge canceled dataset: {cleanup_err}")
                    self.cancel_requested = False
                    
                self._resume_background_vram_tasks()
                with self._lock:
                    self.is_busy = False
                    self.active_job = None
                self.job_queue.task_done()

    def _ensure_pretrained_weights_exist(self, base_dir: str):
        weights_dir = os.path.join(base_dir, "rvc_cpu", "assets", "pretrained_v2")
        os.makedirs(weights_dir, exist_ok=True)
        rmvpe_dir = os.path.join(base_dir, "rvc_cpu", "assets", "rmvpe")
        os.makedirs(rmvpe_dir, exist_ok=True)
        hubert_dir = os.path.join(base_dir, "rvc_cpu", "assets", "hubert")
        os.makedirs(hubert_dir, exist_ok=True)
        import urllib.request
        
        downloads = [
            (os.path.join(weights_dir, "f0G40k.pth"), "f0G40k.pth", "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/pretrained_v2/f0G40k.pth"),
            (os.path.join(weights_dir, "f0D40k.pth"), "f0D40k.pth", "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/pretrained_v2/f0D40k.pth"),
            (os.path.join(rmvpe_dir, "rmvpe.pt"), "rmvpe.pt", "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/rmvpe.pt"),
            (os.path.join(hubert_dir, "hubert_base.pt"), "hubert_base.pt", "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/hubert_base.pt")
        ]
        
        for path, name, url in downloads:
            if not os.path.exists(path):
                self._update_stage("sys", "downloading", f"Downloading {name}", 5, f"Fetching weights ({name})...")
                print(f"[VoiceTraining] Downloading {name} from huggingface...")
                success = False
                for attempt in range(3):
                    try:
                        urllib.request.urlretrieve(url, path)
                        success = True
                        break
                    except Exception as e:
                        print(f"[VoiceTraining] Failed to download {name} (Attempt {attempt+1}/3): {e}")
                        time.sleep(2)
                if not success or not os.path.exists(path):
                    raise RuntimeError(f"Failed to download required model weight: {name}. Pipeline cannot continue.")

    def _run_subprocess_stream(self, jid: str, cmd: list, cwd: str, stage_label: str, is_train_stage: bool = False, total_epochs: int = None, env: dict = None):
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
            
        # Explicitly inject ffmpeg/bin to prevent WinError 2 during extraction scripts
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ffmpeg_bin = os.path.join(base_dir, "ffmpeg", "bin")
        _env = env.copy() if env else os.environ.copy()
        if os.path.exists(ffmpeg_bin) and ffmpeg_bin not in _env.get("PATH", ""):
            _env["PATH"] = f"{ffmpeg_bin};{_env.get('PATH', '')}"
            
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=_env
        )
        
        with self._lock:
            self.active_pid = process.pid
        
        epoch_pattern = re.compile(r"(?:====> Epoch:|Train Epoch:)\s*(\d+)")
        loss_pattern = re.compile(r"loss_g:\s*([\d\.]+).*?loss_d:\s*([\d\.]+)")
        
        start_time = time.time()
        last_update = time.time()
        
        for line in process.stdout:
            if getattr(self, "cancel_requested", False):
                break
                
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
                    if jid in self.progress_states:
                        if "system_stats" not in self.progress_states[jid]:
                            self.progress_states[jid]["system_stats"] = {}
                        self.progress_states[jid]["system_stats"].update(stats)
                        
                        if is_train_stage:
                            if epoch_match:
                                cur_ep = int(epoch_match.group(1))
                                self.progress_states[jid]["system_stats"]["epoch"] = cur_ep
                                if total_epochs:
                                    self.progress_states[jid]["system_stats"]["total_epochs"] = total_epochs
                                    if cur_ep > 0:
                                        time_per_epoch = (now - start_time) / cur_ep
                                        rem_epochs = total_epochs - cur_ep
                                        self.progress_states[jid]["system_stats"]["eta_sec"] = round(rem_epochs * time_per_epoch, 1)
                                        self.progress_states[jid]["system_stats"]["time_per_epoch"] = round(time_per_epoch, 1)
                                    
                                    self.progress_states[jid]["percent"] = 70 + int((cur_ep / total_epochs) * 14)
                                    mode_prefix = "Fresh Training" if is_train_stage and "Resuming" not in stage_label else "Retraining"
                                    self.progress_states[jid]["message"] = f"{mode_prefix} Epoch {cur_ep}/{total_epochs}..."
                            if loss_match:
                                self.progress_states[jid]["system_stats"]["loss_g"] = float(loss_match.group(1))
                                self.progress_states[jid]["system_stats"]["loss_d"] = float(loss_match.group(2))
                                
                        self.mgr.notify_realtime_event("training_progress", dict(self.progress_states[jid]))
                
                last_update = now
                
        process.wait()
        if process.returncode != 0 and process.returncode != 2333333:
            raise RuntimeError(f"Subprocess failed with code {process.returncode} in stage {stage_label}")

    def _execute_training_lifecycle(self, job: Dict[str, Any]) -> None:
        """Executes genuine RVC subprocess training pipeline. Acts as a router."""
        if job.get("job_mode") == "FRESH_TRAINING":
            self._execute_fresh_training(job)
        else:
            self._execute_incremental_retraining(job)

    def _get_optimal_cpu_workers(self, is_f0=False) -> str:
        import multiprocessing
        import psutil
        total_cores = multiprocessing.cpu_count()
        cpu_load = psutil.cpu_percent(interval=0.5)
        available_ratio = 1.0 - (cpu_load / 100.0)
        optimal = int(total_cores * available_ratio)
        max_workers = total_cores if total_cores <= 4 else total_cores - 1
        if is_f0:
            max_workers = min(max_workers, 4)
        return str(max(1, min(optimal, max_workers)))

    def _execute_fresh_training(self, job: Dict[str, Any]) -> None:
        import subprocess
        import sys
        import shutil
        import glob
        
        jid = job["job_id"]
        vid = job["voice_id"]
        vname = job["voice_name"]
        audio_path = job["audio_path"]
        iters = job["iterations"]
        target_epochs = iters

        print(f"[VoiceTraining] Starting FRESH RVC job {jid} ({vname}) - Epochs: {iters}")
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rvc_dir = os.path.join(base_dir, "rvc_cpu")
        python_exe = get_runtime_manager().get_python_executable("rvc")
        
        self._ensure_pretrained_weights_exist(base_dir)

        self._update_stage(jid, "training", "Preparing Dataset", 5, "Analyzing audio file and setting up experiment workspace...")
        
        if not audio_path or not audio_path.strip() or not os.path.exists(audio_path):
            raise RuntimeError("Audio path is required and must exist for fresh cloning.")
            
        dataset_audit = self.validator.analyze_audio_sample(audio_path)
        if not dataset_audit["valid"]:
            raise RuntimeError(f"Dataset Validation Failed: {dataset_audit['message']}")
            
        stats = dataset_audit.get("dataset_stats", {})
        duration_sec = stats.get("total_duration_sec", 60.0)

        exp_dir = os.path.join(rvc_dir, "logs", vid)
        
        # [CRITICAL FIX] Clean legacy dataset chunks AND checkpoints to prevent mixture corruption
        if os.path.exists(exp_dir):
            for old_folder in ["0_raw", "0_gt_wavs", "1_16k_wavs", "2a_f0", "2b-f0nsf", "3_feature768", "mute"]:
                tgt_path = os.path.join(exp_dir, old_folder)
                if os.path.exists(tgt_path):
                    try:
                        shutil.rmtree(tgt_path, ignore_errors=True)
                    except:
                        pass
            for old_ckpt in glob.glob(os.path.join(exp_dir, "*.pth")):
                try:
                    os.remove(old_ckpt)
                except:
                    pass
            for old_index in glob.glob(os.path.join(exp_dir, "*.index")):
                try:
                    os.remove(old_index)
                except:
                    pass
        
        raw_dir = os.path.join(exp_dir, "0_raw")
        os.makedirs(raw_dir, exist_ok=True)
        
        target_audio = os.path.join(raw_dir, f"source_{vid}.wav")
        shutil.copy2(audio_path, target_audio)
        
        config_template = os.path.join(rvc_dir, "configs", "v1", "40k.json")
        exp_config = os.path.join(exp_dir, "config.json")
        if os.path.exists(config_template) and not os.path.exists(exp_config):
            shutil.copy2(config_template, exp_config)

        # Stage 1: Pre-processing
        opt_cores = self._get_optimal_cpu_workers()
        self._update_stage(jid, "training", "Initial Pre-processing", 12, f"Slicing {round(duration_sec/60, 1)} min of fresh audio into training segments using {opt_cores} CPU workers...")
        self._run_subprocess_stream(jid, [python_exe, "infer/modules/train/preprocess.py", raw_dir, "40000", opt_cores, exp_dir, "False", "3.7"], cwd=rvc_dir, stage_label="Initial Pre-processing")

        # Stage 2: F0 Extraction
        opt_cores = self._get_optimal_cpu_workers(is_f0=True)
        self._update_stage(jid, "training", "Initial F0 Extraction", 32, f"Extracting pitch contours (F0) from fresh segments using {opt_cores} CPU workers...")
        self._run_subprocess_stream(jid, [python_exe, "infer/modules/train/extract/extract_f0_print.py", exp_dir, opt_cores, "rmvpe"], cwd=rvc_dir, stage_label="Initial F0 Extraction")

        # Stage 3: Feature Extraction (HuBERT)
        opt_cores = self._get_optimal_cpu_workers()
        
        # [CRITICAL FIX] Process 100% of dataset (1 part, index 0) and multithread natively
        env_dict = os.environ.copy()
        env_dict["OMP_NUM_THREADS"] = str(opt_cores)
        
        has_cuda = False
        try:
            import pynvml
            pynvml.nvmlInit()
            has_cuda = pynvml.nvmlDeviceGetCount() > 0
            pynvml.nvmlShutdown()
        except:
            pass
            
        if has_cuda:
            self._update_stage(jid, "training", "Initial Feature Extraction", 52, f"Generating HuBERT embeddings using GPU acceleration...")
            feature_cmd = [python_exe, "infer/modules/train/extract_feature_print.py", "cuda:0", "1", "0", "0", exp_dir, "v2", "False"]
        else:
            self._update_stage(jid, "training", "Initial Feature Extraction", 52, f"Generating HuBERT embeddings for new dataset using {opt_cores} CPU workers...")
            feature_cmd = [python_exe, "infer/modules/train/extract_feature_print.py", "cpu", "1", "0", exp_dir, "v2", "False"]
            
        self._run_subprocess_stream(jid, feature_cmd, cwd=rvc_dir, stage_label="Initial Feature Extraction", env=env_dict)

        # Stage 4: Neural Network Training
        self._update_stage(jid, "training", "Fresh Neural Training", 70, f"Starting GPU-accelerated Neural Training ({target_epochs} epochs)...")
        self._prepare_filelist_and_train(jid, vid, vname, audio_path, exp_dir, rvc_dir, python_exe, target_epochs, True)

    def _execute_incremental_retraining(self, job: Dict[str, Any]) -> None:
        import subprocess
        import sys
        import shutil
        import glob
        import uuid
        
        jid = job["job_id"]
        vid = job["voice_id"]
        vname = job["voice_name"]
        audio_path = job["audio_path"]
        iters = job["iterations"]

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        rvc_dir = os.path.join(base_dir, "rvc_cpu")
        python_exe = get_runtime_manager().get_python_executable("rvc")
        
        self._ensure_pretrained_weights_exist(base_dir)

        profile = self.mgr.db.get_profile(vid)
        current_iters = profile.get("training_iterations", 0) if profile else 0
        target_epochs = current_iters + iters

        print(f"[VoiceTraining] Starting INCREMENTAL RETRAINING job {jid} ({vname}) - Target Epochs: {target_epochs} (Current: {current_iters})")

        exp_dir = os.path.join(rvc_dir, "logs", vid)

        if audio_path and audio_path.strip() and os.path.exists(audio_path):
            self._update_stage(jid, "training", "Preparing Dataset", 5, "Analyzing new audio file and appending to workspace...")
            dataset_audit = self.validator.analyze_audio_sample(audio_path)
            if not dataset_audit["valid"]:
                raise RuntimeError(f"Dataset Validation Failed: {dataset_audit['message']}")
            stats = dataset_audit.get("dataset_stats", {})
            duration_sec = stats.get("total_duration_sec", 60.0)
            
            raw_dir = os.path.join(exp_dir, "0_raw")
            os.makedirs(raw_dir, exist_ok=True)
            target_audio = os.path.join(raw_dir, f"source_{uuid.uuid4().hex[:6]}.wav")
            shutil.copy2(audio_path, target_audio)
            
            opt_cores = self._get_optimal_cpu_workers()
            self._update_stage(jid, "training", "Incremental Pre-processing", 18, f"Slicing {round(duration_sec/60, 1)} min of appended audio using {opt_cores} CPU workers...")
            self._run_subprocess_stream(jid, [python_exe, "infer/modules/train/preprocess.py", raw_dir, "40000", opt_cores, exp_dir, "False", "3.7"], cwd=rvc_dir, stage_label="Incremental Pre-processing")

            opt_cores = self._get_optimal_cpu_workers(is_f0=True)
            self._update_stage(jid, "training", "Incremental F0 Extraction", 38, f"Extracting F0 from appended segments using {opt_cores} CPU workers...")
            self._run_subprocess_stream(jid, [python_exe, "infer/modules/train/extract/extract_f0_print.py", exp_dir, opt_cores, "rmvpe"], cwd=rvc_dir, stage_label="Incremental F0 Extraction")

            opt_cores = self._get_optimal_cpu_workers()
            
            # [CRITICAL FIX] Process 100% of dataset (1 part, index 0) and multithread natively
            env_dict = os.environ.copy()
            env_dict["OMP_NUM_THREADS"] = str(opt_cores)
            
            has_cuda = False
            try:
                import pynvml
                pynvml.nvmlInit()
                has_cuda = pynvml.nvmlDeviceGetCount() > 0
                pynvml.nvmlShutdown()
            except:
                pass
                
            if has_cuda:
                self._update_stage(jid, "training", "Incremental Feature Extraction", 58, f"Generating HuBERT embeddings for appended segments using GPU acceleration...")
                feature_cmd = [python_exe, "infer/modules/train/extract_feature_print.py", "cuda:0", "1", "0", "0", exp_dir, "v2", "False"]
            else:
                self._update_stage(jid, "training", "Incremental Feature Extraction", 58, f"Generating HuBERT embeddings for appended segments using {opt_cores} CPU workers...")
                feature_cmd = [python_exe, "infer/modules/train/extract_feature_print.py", "cpu", "1", "0", exp_dir, "v2", "False"]
                
            self._run_subprocess_stream(jid, feature_cmd, cwd=rvc_dir, stage_label="Incremental Feature Extraction", env=env_dict)
        else:
            self._update_stage(jid, "training", "Preparing Dataset", 5, "Reusing existing dataset artifacts...")
            self._update_stage(jid, "training", "Incremental Pre-processing", 18, "Skipping pre-processing (dataset unmodified)...")
            self._update_stage(jid, "training", "Incremental Feature Extraction", 58, "Skipping feature extraction (dataset unmodified)...")

        self._update_stage(jid, "training", "Resuming Neural Training", 75, f"Resuming GPU-accelerated Neural Training (Target Epochs: {target_epochs})...")
        self._prepare_filelist_and_train(jid, vid, vname, audio_path, exp_dir, rvc_dir, python_exe, target_epochs, False)

    def _prepare_filelist_and_train(self, jid, vid, vname, audio_path, exp_dir, rvc_dir, python_exe, target_epochs, is_fresh):
        import os, shutil, glob, time
        gt_wavs_dir = os.path.join(exp_dir, "0_gt_wavs")
        feature_dir = os.path.join(exp_dir, "3_feature768")
        f0_dir = os.path.join(exp_dir, "2a_f0")
        f0nsf_dir = os.path.join(exp_dir, "2b-f0nsf")
        
        names = []
        if os.path.exists(gt_wavs_dir):
            names = [os.path.splitext(f)[0] for f in os.listdir(gt_wavs_dir) if f.endswith(".wav")]
        if not names:
            raise RuntimeError("Dataset slicing failed: 0 audio slices were generated. Check ffmpeg dependencies.")
        
        if os.path.exists(feature_dir) and os.path.exists(f0_dir) and os.path.exists(f0nsf_dir):
            intersection = (
                set([n.split(".")[0] for n in os.listdir(gt_wavs_dir)])
                & set([n.split(".")[0] for n in os.listdir(feature_dir)])
                & set([n.split(".")[0] for n in os.listdir(f0_dir)])
                & set([n.split(".")[0] for n in os.listdir(f0nsf_dir)])
            )
            if intersection:
                names = intersection
            else:
                raise RuntimeError("Feature/F0 intersection is empty. Feature extraction failed.")
        
        opt = []
        for name in names:
            opt.append(
                f"{gt_wavs_dir.replace(chr(92), '/')}/{name}.wav|"
                f"{feature_dir.replace(chr(92), '/')}/{name}.npy|"
                f"{f0_dir.replace(chr(92), '/')}/{name}.wav.npy|"
                f"{f0nsf_dir.replace(chr(92), '/')}/{name}.wav.npy|0"
            )
        with open(os.path.join(exp_dir, "filelist.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(opt))
        
        batch_size = "4"
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            total_vram_gb = mem_info.total / (1024**3)
            if total_vram_gb >= 24:
                batch_size = "16"
            elif total_vram_gb >= 16:
                batch_size = "12"
            elif total_vram_gb >= 10:
                batch_size = "8"
            elif total_vram_gb >= 8:
                batch_size = "6"
            else:
                batch_size = "4"
            pynvml.nvmlShutdown()
        except:
            batch_size = "4"
            
        cache_gpu = "0"
        save_freq = str(max(10, target_epochs // 5))
        
        # [CRITICAL FIX] Create weights output dir BEFORE training so savee doesn't crash
        weights_out_dir = os.path.join(rvc_dir, "assets", "weights")
        os.makedirs(weights_out_dir, exist_ok=True)
        
        pg_path = "assets/pretrained_v2/f0G40k.pth"
        pd_path = "assets/pretrained_v2/f0D40k.pth"
        
        if not is_fresh and glob.glob(os.path.join(exp_dir, "G_*.pth")):
            pg_path = ""
            pd_path = ""
        elif not os.path.exists(os.path.join(rvc_dir, pg_path)):
            pg_path = ""
            pd_path = ""
            
        train_cmd = [
            python_exe, "infer/modules/train/train.py",
            "-e", vid, "-sr", "40k", "-f0", "1", "-bs", batch_size,
            "-te", str(target_epochs), "-se", save_freq, "-l", "1", "-c", cache_gpu, "-v", "v2"
        ]
        if pg_path and pd_path:
            train_cmd.extend(["-pg", pg_path, "-pd", pd_path])

        self._run_subprocess_stream(jid, train_cmd, cwd=rvc_dir, stage_label="Neural Training", is_train_stage=True, total_epochs=target_epochs)

        self._update_stage(jid, "training", "Building Index", 85, "Generating FAISS index for timbre preservation...")
        index_script = os.path.join(rvc_dir, "infer", "modules", "train", "index", "train_index.py")
        if os.path.exists(index_script):
            try:
                self._run_subprocess_stream(jid, [python_exe, "infer/modules/train/index/train_index.py", exp_dir, "v2"], cwd=rvc_dir, stage_label="Building Index")
            except Exception as e:
                print(f"[VoiceTraining] Index building warning: {e}")
        
        model_filename = f"{vid}_{vname.lower().replace(' ', '_')}.pth"
        final_model_path = os.path.join(weights_out_dir, model_filename)
        
        trained_pth = os.path.join(weights_out_dir, f"{vid}.pth")
        if os.path.exists(trained_pth):
            shutil.copy2(trained_pth, final_model_path)
        else:
            print("[VoiceTraining] Target weights file not found. Attempting extraction from latest G checkpoint...")
            import sys
            if rvc_dir not in sys.path:
                sys.path.insert(0, rvc_dir)
            try:
                from infer.lib.train.process_ckpt import extract_small_model
                g_pths = glob.glob(os.path.join(exp_dir, "G_*.pth"))
                if g_pths:
                    latest_g = sorted(g_pths, key=os.path.getmtime)[-1]
                    res = extract_small_model(latest_g, model_filename.replace(".pth", ""), "40k", "1", "Extracted model fallback", "v2")
                    print(f"[VoiceTraining] Extracted small model from {latest_g}: {res}")
                else:
                    raise RuntimeError("Training failed: No generator checkpoints found to extract.")
            except Exception as e:
                raise RuntimeError(f"Training failed: Failed to extract from checkpoint. {e}")
                
        index_src = os.path.join(exp_dir, f"added_IVF_*.index")
        indexes = glob.glob(index_src)
        if indexes:
            shutil.copy2(indexes[-1], os.path.join(weights_out_dir, f"{vid}_{vname.lower().replace(' ', '_')}.index"))

        self._update_stage(jid, "evaluating", "Objective Validation", 90, "Running benchmark inference and computing acoustic metrics...")
        
        previews = self.preview_engine.prepare_comparison_previews(original_audio_path=audio_path, model_filename=model_filename, voice_id=vid)
        quality_eval = self.validator.evaluate_model_quality_acoustic(original_audio=previews.get("original_file_path", audio_path or ""), cloned_audio=previews.get("cloned_file_path", ""), model_filename=model_filename, training_iterations=target_epochs)

        completed_summary = {
            "job_id": jid, "voice_id": vid, "voice_name": vname, "model_filename": model_filename,
            "iterations": target_epochs, "quality_audit": quality_eval, "comparison_previews": previews,
            "dataset_stats": {}, "completed_at": time.time()
        }
        try:
            import json
            with open(os.path.join(weights_out_dir, f"{vid}_metadata.json"), "w", encoding="utf-8") as meta_f:
                json.dump(completed_summary, meta_f, indent=4)
        except Exception as meta_err:
            pass

        with self._lock:
            if jid in self.progress_states:
                self.progress_states[jid].update({
                    "status": "finished", "stage_label": "Training Complete", "percent": 100,
                    "message": f"Training completed. Score: {quality_eval.get('overall_score', 0)}%",
                    "last_completed_job": completed_summary
                })
                self.mgr.notify_realtime_event("training_finished", dict(self.progress_states[jid]))
        print(f"[VoiceTraining] Job {jid} completed successfully.")
    def _update_stage(self, jid: str, status: str, label: str, pct: int, msg: str) -> None:
        with self._lock:
            if jid not in self.progress_states:
                self.progress_states[jid] = {"job_id": jid}
            self.progress_states[jid].update({
                "status": status,
                "stage_label": label,
                "percent": pct,
                "message": msg
            })
            self.mgr.notify_realtime_event("training_progress", dict(self.progress_states[jid]))
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
