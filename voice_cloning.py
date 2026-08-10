import os
import vivy_env
import sys
import shutil
import argparse
import traceback
import warnings

# [CRITICAL FIX] Suppress safe SM_120 forward-compatibility JIT JIT warnings from PyTorch
warnings.filterwarnings("ignore", category=UserWarning, module="torch\.cuda.*")
warnings.filterwarnings("ignore", category=UserWarning, module="torch.nn.utils.weight_norm")

# [CRITICAL FIX] Runtime Monkeypatch for Deprecated weight_norm API
try:
    import torch.nn.utils
    from torch.nn.utils.parametrizations import weight_norm as new_weight_norm
    torch.nn.utils.weight_norm = new_weight_norm
    
    from torch.nn.utils.parametrize import remove_parametrizations
    def _patched_remove_weight_norm(module, name="weight"):
        try:
            return remove_parametrizations(module, name)
        except Exception:
            return module
    torch.nn.utils.remove_weight_norm = _patched_remove_weight_norm
except Exception as e:
    pass

# Add ffmpeg to PATH automatically
base_dir = os.path.dirname(os.path.abspath(__file__))
ffmpeg_path = os.path.join(base_dir, "ffmpeg", "bin")
if os.path.exists(ffmpeg_path) and ffmpeg_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ.get("PATH", "")

# Reconfigure stdout/stderr to use utf-8 to avoid encoding errors with emojis on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Dynamic paths setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RVC_DIR = os.path.join(BASE_DIR, "rvc_cpu")

if RVC_DIR not in sys.path:
    sys.path.insert(0, RVC_DIR)

# Set environment variables for RVC
os.environ["weight_root"] = os.path.join(RVC_DIR, "assets", "weights")
os.environ["index_root"] = os.path.join(RVC_DIR, "logs")
os.environ["outside_index_root"] = os.path.join(RVC_DIR, "assets", "indices")
os.environ["rmvpe_root"] = os.path.join(RVC_DIR, "assets", "rmvpe")


class VoiceCloningEngine:
    def __init__(self):
        self.vc = None
        self.config = None
        self.current_model = None
        self.f0_method = "rmvpe"
        self._initialize()

    def _initialize(self):
        orig_cwd = os.getcwd()
        try:
            os.chdir(RVC_DIR)
            from configs.config import Config
            from infer.modules.vc.modules import VC
            
            self.config = Config()
            self.vc = VC(self.config)
            
            if not os.path.exists(os.path.join(RVC_DIR, "assets", "rmvpe", "rmvpe.pt")):
                self.f0_method = "pm"
                
        except Exception as e:
            print(f"[VoiceCloningEngine] Initialization error: {e}")
            traceback.print_exc()
        finally:
            os.chdir(orig_cwd)

    def convert_voice(self, input_path, output_path, pitch=0, method=None, model_name=None):
        if not os.path.exists(input_path):
            return {"status": "error", "message": f"Input file not found: {input_path}"}
            
        weights_dir = os.environ["weight_root"]
        os.makedirs(weights_dir, exist_ok=True)
        pth_files = [
            f for f in os.listdir(weights_dir)
            if f.endswith(".pth") and f != "Synthesizer_inputs.pth"
            and os.path.isfile(os.path.join(weights_dir, f))
            and os.path.getsize(os.path.join(weights_dir, f)) > 1024
        ]
        
        if not pth_files:
            shutil.copy2(input_path, output_path)
            return {"status": "success", "message": "No model found. Copied raw TTS."}
            
        target_model = model_name if model_name and model_name in pth_files else pth_files[0]
        
        # Resolve corresponding .index file for the model to ensure accurate voice timbre
        index_file = ""
        expected_index = target_model.replace(".pth", ".index")
        if os.path.exists(os.path.join(weights_dir, expected_index)):
            index_file = os.path.join(weights_dir, expected_index)
        
        orig_cwd = os.getcwd()
        try:
            os.chdir(RVC_DIR)
            import soundfile as sf
            
            if self.current_model != target_model:
                print(f"Loading RVC model: {target_model}...")
                self.vc.get_vc(target_model)
                self.current_model = target_model
                
            info, opt = self.vc.vc_single(
                sid=0,
                input_audio_path=input_path,
                f0_up_key=pitch,
                f0_file=None,
                f0_method=method or self.f0_method,
                file_index=index_file,
                file_index2="",
                index_rate=0.75,
                filter_radius=3,
                resample_sr=0,
                rms_mix_rate=0.25,
                protect=0.33
            )
            
            if "Success" in info and opt[1] is not None:
                tgt_sr, audio_opt = opt
                sf.write(output_path, audio_opt, tgt_sr)
                return {"status": "success", "message": f"Converted {target_model}"}
            else:
                shutil.copy2(input_path, output_path)
                return {"status": "error", "message": f"Inference failed. Copied raw. {info}"}
        except Exception as e:
            shutil.copy2(input_path, output_path)
            return {"status": "error", "message": str(e)}
        finally:
            os.chdir(orig_cwd)

def run_server(port=8766):
    from xmlrpc.server import SimpleXMLRPCServer
    print(f"Starting RVC Voice Cloning XML-RPC Server on port {port}...")
    engine = VoiceCloningEngine()
    server = SimpleXMLRPCServer(("127.0.0.1", port), allow_none=True)
    server.register_instance(engine)
    server.serve_forever()

def main():
    parser = argparse.ArgumentParser(description="Vivy AI Voice Cloning")
    parser.add_argument("--server", action="store_true", help="Run as XML-RPC background server")
    parser.add_argument("--port", type=int, default=8766, help="XML-RPC server port")
    parser.add_argument("--input", type=str, default=os.path.join(BASE_DIR, "shared", "tts.wav"))
    parser.add_argument("--output", type=str, default=os.path.join(BASE_DIR, "shared", "rvc.wav"))
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument("--method", type=str, default="rmvpe")
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()
    
    if args.server:
        run_server(args.port)
    else:
        args.input = os.path.abspath(args.input)
        args.output = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        engine = VoiceCloningEngine()
        res = engine.convert_voice(args.input, args.output, args.pitch, args.method, args.model)
        if res["status"] == "error":
            print(f"Error: {res['message']}")
        else:
            print(f"Success: {res['message']}")

if __name__ == "__main__":
    main()
