import queue

# Centralized queues for the pipeline
# We apply hard maxsize limits to provide backpressure.
# If downstream is slow (e.g. TTS), we don't want LLM to infinitely buffer thousands of tokens.

MAX_TOKEN_QUEUE = 500
MAX_TTS_QUEUE = 20
MAX_RVC_QUEUE = 20
MAX_PLAYBACK_QUEUE = 50

# Text queue from STT -> Main Orchestrator
# Dict: {"type": "partial"|"final", "text": str}
text_queue = queue.Queue(maxsize=100)

# Token queue from LLM -> Sentence Chunker
token_queue = queue.Queue(maxsize=MAX_TOKEN_QUEUE)

# TTS queue from Sentence Chunker -> TTS Worker
tts_queue = queue.Queue(maxsize=MAX_TTS_QUEUE)

# RVC queue from TTS Worker -> RVC Worker
rvc_queue = queue.Queue(maxsize=MAX_RVC_QUEUE)

# Playback queue from RVC Worker -> Playback Worker
playback_queue = queue.Queue(maxsize=MAX_PLAYBACK_QUEUE)