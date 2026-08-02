from pydub import AudioSegment
from pydub.silence import split_on_silence
import os

# HARD BIND ffmpeg (bypass PATH issues)
base_dir = os.path.dirname(os.path.abspath(__file__))
AudioSegment.converter = os.path.join(base_dir, "ffmpeg", "bin", "ffmpeg.exe")
AudioSegment.ffmpeg = os.path.join(base_dir, "ffmpeg", "bin", "ffmpeg.exe")
AudioSegment.ffprobe = os.path.join(base_dir, "ffmpeg", "bin", "ffprobe.exe")

INPUT = "dataset_raw"
OUTPUT = "dataset_wav"

os.makedirs(OUTPUT, exist_ok=True)

for f in os.listdir(INPUT):
    if f.endswith(".wav"):
        audio = AudioSegment.from_wav(os.path.join(INPUT, f))
        chunks = split_on_silence(
            audio,
            min_silence_len=500,
            silence_thresh=-40
        )
        for i, chunk in enumerate(chunks):
            if len(chunk) > 1000:
                chunk = chunk.set_channels(1).set_frame_rate(40000)
                chunk.export(
                    f"{OUTPUT}/{f[:-4]}_{i}.wav",
                    format="wav"
                )
