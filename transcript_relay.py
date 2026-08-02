"""
transcript_relay.py — Vivy AI Bridge
Watches d:/Vivy/transcripts/ for new Whisper transcriptions and
writes the text into shared/user_text.txt so run_vivy.py picks it up.
"""
import os
import sys
import time
from colorama import Fore, Style, init

# Reconfigure stdout/stderr to use utf-8 to avoid encoding errors with emojis on Windows
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

init(autoreset=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRANSCRIPT_DIR = os.path.join(BASE_DIR, "transcripts")
USER_TXT = os.path.join(BASE_DIR, "shared", "user_text.txt")

os.makedirs(TRANSCRIPT_DIR, exist_ok=True)

seen = set(os.listdir(TRANSCRIPT_DIR))

print(Fore.CYAN + "=== Vivy AI Transcript Relay ACTIVE ===" + Style.RESET_ALL)
print(Fore.GREEN + f"Watching: {TRANSCRIPT_DIR}" + Style.RESET_ALL)
print(Fore.YELLOW + "Speak into the mic. Vivy will respond in shared/reply_text.txt\n" + Style.RESET_ALL)

while True:
    try:
        current = set(os.listdir(TRANSCRIPT_DIR))
        new_files = current - seen

        for fname in sorted(new_files):
            fpath = os.path.join(TRANSCRIPT_DIR, fname)
            if not fname.endswith(".txt"):
                seen.add(fname)
                continue

            # Wait a moment to ensure file is fully written
            time.sleep(0.3)

            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read().strip()

            if text:
                print(Fore.WHITE + f"\n🎤 You said: {text}" + Style.RESET_ALL)

                # Wait until shared/user_text.txt is empty (previous turn done)
                for _ in range(20):
                    with open(USER_TXT, "r", encoding="utf-8") as uf:
                        if uf.read().strip() == "":
                            break
                    time.sleep(0.5)

                # Write input source first
                source_file = os.path.join(BASE_DIR, "shared", "input_source.txt")
                try:
                    with open(source_file, "w", encoding="utf-8") as sf:
                        sf.write("voice")
                except Exception as se:
                    print(Fore.RED + f"Relay error writing source: {se}" + Style.RESET_ALL)

                # Write to shared/user_text.txt for run_vivy.py to pick up
                with open(USER_TXT, "w", encoding="utf-8") as uf:
                    uf.write(text)

                print(Fore.CYAN + "→ Sent to Vivy AI..." + Style.RESET_ALL)

            seen.add(fname)

        time.sleep(0.25)

    except KeyboardInterrupt:
        print(Fore.YELLOW + "\nRelay stopped." + Style.RESET_ALL)
        break
    except Exception as e:
        print(Fore.RED + f"Relay error: {e}" + Style.RESET_ALL)
        time.sleep(1)
