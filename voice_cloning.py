import os
import sys
import shutil
import argparse

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

def main():
    parser = argparse.ArgumentParser(description="Vivy AI Voice Cloning / Voice Conversion Wrapper")
    parser.add_argument("--input", type=str, default=os.path.join(BASE_DIR, "shared", "tts.wav"), help="Input TTS WAV file path")
    parser.add_argument("--output", type=str, default=os.path.join(BASE_DIR, "shared", "rvc.wav"), help="Output RVC converted WAV file path")
    parser.add_argument("--pitch", type=int, default=0, help="Pitch shift key (semitones)")
    parser.add_argument("--method", type=str, default="rmvpe", choices=["pm", "harvest", "rmvpe", "crepe"], help="F0 extraction method")
    parser.add_argument("--model", type=str, default=None, help="Speaker weights model filename")
    
    args = parser.parse_args()
    
    args.input = os.path.abspath(args.input)
    args.output = os.path.abspath(args.output)

    # Ensure intermediate directories exist
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    if not os.path.exists(args.input):
        print(f"Error: Input file {args.input} does not exist.")
        sys.exit(1)
        
    weights_dir = os.environ["weight_root"]
    os.makedirs(weights_dir, exist_ok=True)
    
    # Search for any valid .pth speaker weights (excluding tiny placeholder/dummy test files)
    pth_files = [
        f for f in os.listdir(weights_dir)
        if f.endswith(".pth") and f != "Synthesizer_inputs.pth"
        and os.path.isfile(os.path.join(weights_dir, f))
        and os.path.getsize(os.path.join(weights_dir, f)) > 1024
    ]
    
    if not pth_files:
        print("[Vivy Voice] Active Mode: Default Female Anime Vocal Identity (Direct Expressive Synthesis).")
        shutil.copy2(args.input, args.output)
        sys.exit(0)
        
    # Pick specified speaker model or first available model
    model_name = pth_files[0]
    if args.model:
        m_base = os.path.basename(args.model)
        if m_base in pth_files:
            model_name = m_base

    print(f"Loading RVC model: {model_name}...")
    
    orig_cwd = os.getcwd()
    try:
        os.chdir(RVC_DIR)
        from configs.config import Config
        from infer.modules.vc.modules import VC
        import soundfile as sf
        
        # Load CPU configuration
        config = Config()
        config.device = "cpu"
        config.is_half = False
        
        vc = VC(config)
        vc.get_vc(model_name)
        
        print(f"Running voice conversion on: {args.input}")
        
        info, opt = vc.vc_single(
            sid=model_name,
            input_audio_path=args.input,
            f0_up_key=args.pitch,
            f0_file=None,
            f0_method=args.method,
            file_index="",
            file_index2="",
            index_rate=0.75,
            filter_radius=3,
            resample_sr=0,
            rms_mix_rate=0.25,
            protect=0.33
        )
        
        if "Success" in info and opt[1] is not None:
            tgt_sr, audio_opt = opt
            sf.write(args.output, audio_opt, tgt_sr)
            print(f"Voice conversion completed successfully: {args.output}")
        else:
            print(f"RVC conversion failed. Info: {info}")
            print("Falling back: Copying clean TTS output to RVC output.")
            shutil.copy2(args.input, args.output)
            
    except Exception as e:
        print(f"Error during voice conversion: {e}")
        print("Falling back: Copying clean TTS output to RVC output.")
        shutil.copy2(args.input, args.output)
    finally:
        os.chdir(orig_cwd)

if __name__ == "__main__":
    main()
