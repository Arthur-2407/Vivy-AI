<div align="center">

<h1>🎙️ Vivy AI</h1>
<p><strong>An Advanced Local-First Companion AI with Multimodal Perception, AGI Cognitive Architecture, and a Live 3D Avatar</strong></p>

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey?style=for-the-badge&logo=windows" alt="Windows"/>
  <img src="https://img.shields.io/badge/LLM-llama.cpp%20%7C%20Qwen3-8B-green?style=for-the-badge" alt="LLM"/>
  <img src="https://img.shields.io/badge/Speech-Whisper%20%7C%20TTS%20%7C%20RVC-purple?style=for-the-badge" alt="Speech"/>
  <img src="https://img.shields.io/badge/Avatar-MateEngine%20%7C%20VRM-ff69b4?style=for-the-badge" alt="Avatar"/>
  <img src="https://img.shields.io/badge/License-Vivy%20AI%20License-orange?style=for-the-badge" alt="License"/>
</p>

<p><em>Vivy is a fully local, privacy-first AI companion that sees your screen, hears your world, watches your camera, reasons with a multi-layer AGI cognitive architecture, speaks with a cloned voice, and animates a live 3D avatar — all without sending a single byte to the cloud.</em></p>

</div>

---

## ✨ Overview

Vivy AI is a **deeply integrated, local-first companion AI** built around a sophisticated multi-stage reasoning pipeline. Unlike cloud-dependent AI assistants, Vivy runs entirely on your hardware — combining a quantized local LLM, multimodal screen and camera perception, real-time voice cloning, and a living 3D avatar powered by the MateEngine Unity runtime, all orchestrated through a Flask + WebSocket web dashboard.

Vivy is designed from first principles as a **personal AGI substrate**: she learns from every conversation, evolves her own cognitive weights, builds and queries a personal knowledge graph, and routes internet intelligence through an anonymous onion-circuit network stack — all in real time.

---

## 🏗️ Architecture

Vivy's pipeline is divided into eight cooperating subsystems:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            run_vivy.py (Main Pipeline)                  │
│                                                                         │
│  ┌────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────┐  │
│  │  Mic Input │──▶│ Whisper STT  │──▶│  Conversation │──▶│   TTS /  │  │
│  │  (Voice)   │   │  (whisper.c) │   │  Planner &    │   │   RVC    │  │
│  └────────────┘   └──────────────┘   │  LLM (llama)  │   │  Voice   │  │
│                                      └───────┬───────┘   └──────────┘  │
│  ┌────────────┐   ┌──────────────┐           │                          │
│  │  Web UI    │──▶│  Flask API   │           │                          │
│  │  (Text)    │   │  web_server  │           │                          │
│  └────────────┘   └──────────────┘           │                          │
│                                              ▼                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                   AGI Cognitive Core (agi/)                       │  │
│  │  Blackboard · WorldModel · KnowledgeGraph · BeliefEngine          │  │
│  │  MetaCognition · LongHorizonPlanner · SkillSystem                 │  │
│  │  LearningEngine · ExperimentEngine · SimulationEngine             │  │
│  │  JobScheduler · ToolRouter · ModelAdaptationEngine                │  │
│  │  SelfEvaluationLoop · SelfModificationEngine                      │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐  │
│  │  Perception  │  │  Circadian   │  │  Evolution  │  │  Internet  │  │
│  │  (Camera +   │  │  Intelligence│  │  Engine     │  │  Intelligence│  │
│  │   Screen +   │  │  (Mood/Phase)│  │  (Self-Evo) │  │  (Tor/DDG) │  │
│  │   Audio)     │  └──────────────┘  └─────────────┘  └────────────┘  │
│  └──────────────┘                                                       │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │          MateEngine (Unity 3D Avatar — Mate-Engine/)             │   │
│  │   VRM Avatar · Lip Sync · Procedural Animation · Emotion Rig    │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

All subsystems communicate through a **shared file-based IPC layer** (`shared/`) allowing `run_vivy.py` and `web_server.py` to run as separate OS processes while maintaining a consistent state view.

---

## 🧠 Core Features

### 🤖 AGI Cognitive Architecture (`agi/`)
Vivy's reasoning is not simply a prompt + LLM call. Every conversation turn is processed through a **15-module General Cognitive Core**:

| Module | Function |
|---|---|
| `blackboard.py` | Central shared cognitive state bus — all subsystems publish and subscribe |
| `world_model.py` | Maintains a dynamic, updating model of the user's world and environment |
| `knowledge_graph.py` | Builds and queries personal knowledge triples and entity relationships |
| `belief_engine.py` | Asserts, revises, and retrieves epistemic beliefs with confidence scores |
| `meta_cognition.py` | Reason → Critique → Improve → Verify loop over candidate responses |
| `long_horizon_planner.py` | Tracks and executes multi-turn conversation goals and active plans |
| `skill_system.py` | XP-based skill progression (e.g., `conversational_empathy`, `code_reasoning`) |
| `learning_engine.py` | Curiosity-driven continual learning with retention buffers |
| `experiment_engine.py` | Safe sandbox experiments for self-optimizing cognitive weights |
| `simulation_engine.py` | Internal counterfactual simulation: Plan A vs. Plan B selection |
| `job_scheduler.py` | Background autonomous task queue and scheduled cognitive jobs |
| `tool_router.py` | Autonomous tool selection and execution pipeline |
| `model_adaptation_engine.py` | High-reward experience replay and controlled adaptation cycles |
| `self_evaluation_loop.py` | Per-turn quality scoring and feedback integration |
| `self_modification_engine.py` | Safe, governed self-improvement proposals and patches |

### 👁️ Multimodal Perception (`perception/`)
Vivy continuously perceives the world around you in real time:

- **Screen Perception** — Captures your display at up to 30 FPS with adaptive sampling. Runs OCR (Tesseract) and a local Vision Language Model (Moondream) to understand your active application, highlighted text, open documents, and what you are reading or working on.
- **Camera Perception** — YOLO-based face detection, facial landmark tracking, gaze direction estimation, eye-contact scoring, attention/engagement/presence scoring, and hand-held object recognition. Vivy knows when you are looking at her, looking away, or have left your desk.
- **Audio Perception** — System audio and microphone pipeline with ambient/speech/music separation, real-time transcription of playing audio (lyrics, speech), speaker identification, and event classification.
- **Fusion Engine** — All perception streams are fused into a unified `perception_state.json` snapshot, injected as grounded context into every LLM prompt.
- **Proactivity Engine** — Can proactively initiate conversation when it detects meaningful events (configurable threshold and rate limiting).

### 🎤 Voice Pipeline
- **Speech Recognition**: `whisper.cpp` running locally — no API keys, no cloud.
- **Text-to-Speech**: Coqui TTS (`tacotron2-DDC`) synthesising Vivy's voice locally.
- **Voice Cloning**: Retrieval-based Voice Conversion (RVC) transforms the TTS output into Vivy's personal cloned vocal identity.
- **Lip Sync**: MuseTalk and Wav2Lip integration for real-time avatar mouth synchronisation.

### 🌐 Internet Intelligence (`internet/`)
Vivy's internet layer is built around a **multi-tier, privacy-first architecture**:

- **Search Providers**: DuckDuckGo (DDGS library + HTML scraping + Lite fallback), Wikipedia, GitHub/PyPI package registry, academic literature (arXiv), RSS feeds, forum discussions, and official documentation crawlers — all without API keys.
- **Web Crawler**: Direct URL crawling, XML sitemap indexing, and intelligent HTML content extraction with boilerplate removal.
- **RAG Pipeline** (`internet/rag/`): Search results are vector-embedded and stored in a local retrieval-augmented generation database for grounded LLM answering.
- **Search Cache**: In-memory + disk cache with configurable TTL (default 24h) and up to 1,000 entries.
- **Anonymous Routing**: All outbound requests flow through:
  - **Tor Controller** — Connects to a running system Tor daemon or engages a Virtual SOCKS5 Onion Circuit Sandbox (antivirus-safe, no binary required).
  - **Tor Identity Rotation** — Automatic circuit rotation with multi-hop country chains.
  - **L2–L4 Address Bouncer** — Dynamically regenerates MAC addresses, virtual gateway IPs, TTL values, and ephemeral TCP/UDP port identities every 45 seconds during active sessions.
  - **DNS Manager** — SOCKS5h DNS-leak-defense routing with Cloudflare/Google/Quad9 fallback.

### 🧬 Self-Evolution Engine (`evolution/`)
Vivy continuously improves herself between conversations:

- **Evolution Engine** — Proposes and evaluates self-modification candidates.
- **Adaptation Engine** — Applies approved changes to cognitive parameters.
- **Correction Engine** — Detects and reverses regressions.
- **Governance Layer** — Safety-gated approval pipeline preventing harmful self-modifications.
- **Experience Replay** — Learns from past high-reward interactions.
- **Meta-Learning** — Cross-task generalisation and strategy abstraction.

### 🌙 Circadian Intelligence (`circadian/`)
Vivy's behaviour and tone adapt to a **biologically inspired circadian rhythm**:
- Tracks time-of-day phases: Morning, Afternoon, Evening, Night, Deep-Night.
- Adjusts energy, social drive, tone, and verbosity based on the current phase.
- Integrates hardware sleep state (system idle detection) for realistic presence awareness.

### 💙 Affection & Social Drive (`affection/`, `loneliness/`)
- Persistent `affection_level` and `loneliness_level` memory fields updated across sessions.
- `social_drive` modulates how proactively Vivy reaches out.
- Relationship progression arc tracked over long-term conversation history.

### 🎭 3D Avatar — MateEngine (`Mate-Engine/`)
Vivy's visual presence is powered by **MateEngine**, a Unity-based real-time VRM avatar runtime:
- Full VRM 0.x / VRM 1.0 avatar loading and rendering.
- Procedural animation authoring pipeline with a visual keyframe editor.
- Emotion-driven facial expression blending.
- Real-time lip sync driven by audio waveform data from Vivy's TTS output.
- MToon shader, spring bone physics, Discord Rich Presence, and Steam integration.
- Communicates with the Python pipeline via WebSocket on port 8765.

### 🖥️ Web Dashboard (`web_server.py`)
A full Flask application serving a rich browser-based UI:
- Live chat interface with audio playback for every response.
- Real-time system status, telemetry, and cognitive state readouts.
- Screen share and camera feed capture directly from the browser.
- Developer Diagnostic Dashboard with prompt trace, WebSocket monitor, and fallback analytics.
- 60+ REST API endpoints covering every subsystem.

---

## 📦 Project Structure

```
Vivy/
├── run_vivy.py                  # Main entry point — orchestrates the full pipeline
├── web_server.py                # Flask API server and Web UI backend (60+ routes)
├── conversation.py              # Core LLM conversation engine (317 KB)
├── vivy_config.json             # Central configuration — all tunable parameters
│
├── agi/                         # AGI Cognitive Architecture (15 subsystems)
│   ├── cognitive_core.py        # Unified pre/post-turn cognitive orchestration facade
│   ├── blackboard.py            # Shared cognitive state bus
│   ├── world_model.py           # Dynamic world model
│   ├── knowledge_graph.py       # Personal knowledge triple store
│   ├── belief_engine.py         # Epistemic belief management
│   ├── meta_cognition.py        # Reason→Critique→Improve→Verify loop
│   ├── long_horizon_planner.py  # Multi-turn goal planning
│   ├── skill_system.py          # XP-based skill progression
│   ├── learning_engine.py       # Continual learning with curiosity
│   ├── experiment_engine.py     # Safe sandbox cognitive experiments
│   ├── simulation_engine.py     # Counterfactual plan simulation
│   ├── job_scheduler.py         # Autonomous background job queue
│   ├── tool_router.py           # Autonomous tool selection
│   ├── model_adaptation_engine.py  # High-reward experience adaptation
│   ├── self_evaluation_loop.py  # Per-turn quality scoring
│   └── self_modification_engine.py # Governed self-improvement
│
├── perception/                  # Multimodal perception subsystem
│   ├── perception_manager.py    # Central perception state writer/reader (78 KB)
│   ├── camera_manager.py        # Camera input and frame scheduling
│   ├── face_detector.py         # YOLO-based face detection
│   ├── face_emotion.py          # Facial emotion classification
│   ├── gaze_detector.py         # Eye contact and gaze direction
│   ├── object_detector.py       # Real-time object recognition
│   ├── screen_pipeline.py       # Screen capture, OCR, and VLM analysis (72 KB)
│   ├── audio_pipeline.py        # System audio capture and classification
│   ├── fusion_engine.py         # Multi-stream perceptual fusion
│   ├── context_injector.py      # LLM context grounding from perception
│   ├── proactivity_engine.py    # Proactive conversation initiation
│   └── vision_adapter.py        # Vision model routing and inference
│
├── internet/                    # Internet Intelligence Layer
│   ├── internet_manager.py      # Provider registry and search orchestration
│   ├── duckduckgo_provider.py   # Multi-tier DuckDuckGo adapter
│   ├── search_cache.py          # TTL-based search result cache
│   ├── search_planner.py        # Query strategy and necessity evaluation
│   ├── network/                 # Anonymous network stack
│   │   ├── tor_controller.py    # Tor daemon + Virtual SOCKS5 sandbox
│   │   ├── tor_identity.py      # Multi-hop circuit rotation
│   │   ├── address_bouncer.py   # L2–L4 identity hopping (45s cycles)
│   │   ├── request_router.py    # Unified request gateway
│   │   ├── dns_manager.py       # DNS-leak-defense resolution
│   │   └── protocol_lab.py      # Protocol experimentation layer
│   ├── providers/               # Search provider adapters
│   │   ├── web_crawler_provider.py       # Direct URL crawling + sitemap indexing
│   │   ├── wikipedia_provider.py         # Wikipedia search adapter
│   │   ├── academic_literature_provider.py  # arXiv and open journals
│   │   ├── github_package_provider.py    # GitHub/PyPI/npm registry
│   │   ├── rss_monitor_provider.py       # RSS feed monitoring
│   │   ├── forum_discussion_provider.py  # Forum search adapter
│   │   └── doc_crawler_provider.py       # Official documentation crawler
│   ├── rag/                     # Retrieval-Augmented Generation pipeline
│   └── verification/            # Source credibility and fact verification
│
├── circadian/                   # Circadian rhythm intelligence
│   ├── circadian_engine.py      # Phase detection and behavioural modulation (26 KB)
│   └── hardware_manager.py      # System idle/sleep state integration
│
├── evolution/                   # Self-Evolution subsystem
│   ├── evolution_engine.py      # Continuous self-improvement proposals
│   ├── governance_layer.py      # Safety-gated approval pipeline
│   ├── adaptation_engine.py     # Parameter adaptation and application
│   ├── correction_engine.py     # Regression detection and rollback
│   └── experience_replay.py     # High-reward interaction replay
│
├── emotion/                     # Emotion classification engine
│   ├── emotion_engine.py        # Text-based emotion detection
│   └── emotion_engine_ml.py     # ML-backed emotion classification
│
├── animator/                    # Avatar animation system
│   └── animator.py              # Procedural animation controller
│
├── affection/                   # Affection and relationship engine
├── loneliness/                  # Social drive and loneliness modelling
├── contracts/                   # Dialogue and behavioural contracts
├── database/                    # Persistent knowledge storage
├── logging_framework/           # Structured telemetry and audit logging
├── config/                      # Configuration management
├── mic_input.py                 # Microphone capture and VAD pipeline (22 KB)
├── voice.py                     # TTS synthesis orchestration
├── voice_cloning.py             # RVC voice cloning integration
├── avatar_bridge.py             # Unity/MateEngine WebSocket bridge (26 KB)
├── animation_authoring_pipeline.py  # Visual animation authoring tool (54 KB)
├── memory_orchestrator.py       # Long-term memory management
├── cognitive_orchestrator.py    # High-level conversation orchestration
├── telemetry_manager.py         # Full system telemetry and event bus (29 KB)
├── resource_manager.py          # Global resource lifecycle and cleanup
├── knowledge_router.py          # Online/offline knowledge routing
├── topic_tracker.py             # Conversation topic continuity tracker
├── conversation_planner.py      # Pre-turn conversation strategy planning
├── vivy_memory.json             # Persistent long-term memory store
├── vivy_animation_registry.json # Animation clip registry
├── shared/                      # File-based IPC channel (process bridge)
├── static/                      # Web UI static assets
├── templates/                   # Flask HTML templates
├── models/                      # Local model files (LLM, Whisper, VLM, etc.)
├── rvc_cpu/                     # RVC voice cloning models
├── whisper.cpp/                 # Whisper.cpp binary
├── Retrieval-based-Voice-Conversion-WebUI-main/  # RVC WebUI integration
└── Mate-Engine/                 # MateEngine Unity 3D avatar runtime (separate license)
```

---

## 🔧 Configuration

All system behaviour is controlled through `vivy_config.json`. No source code changes are required to tune the system.

```jsonc
{
  "models": {
    "llm":     "models/Qwen3-8B-Q4_K_M.gguf",   // Local LLM
    "whisper": "models/ggml-small.bin",           // Speech recognition
    "vision":  "models/moondream-vision.gguf"    // Screen/camera VLM
  },
  "pipeline": {
    "llm_n_ctx":         8192,   // Context window
    "llm_n_gpu_layers":  -1,     // -1 = all layers on GPU
    "llm_temperature":   0.75
  },
  "screen_perception": {
    "enabled": true,
    "fps":     30,
    "ocr_enabled": true,
    "vision_model_enabled": true
  },
  "internet_intelligence": {
    "enabled":           true,
    "cache_ttl_seconds": 86400   // 24-hour search cache
  }
}
```

---

## 🚀 Getting Started

### Prerequisites

- **Windows 10/11** (64-bit)
- **Python 3.10+**
- **CUDA-capable GPU** (recommended; CPU fallback available)
- **Tesseract OCR** (for screen reading) — [Install from here](https://github.com/tesseract-ocr/tesseract)
- **FFmpeg** (for audio processing) — place binary in `ffmpeg/`

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/Arthur-2407/Vivy-AI.git
cd Vivy-AI

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Place your local model files in models/
#    - LLM: models/Qwen3-8B-Q4_K_M.gguf (or any llama.cpp-compatible GGUF)
#    - Whisper: models/ggml-small.bin
#    - Vision: models/moondream-vision.gguf (optional)

# 5. Configure vivy_config.json as needed

# 6. Launch Vivy
python run_vivy.py
```

The web dashboard will be available at **http://127.0.0.1:8080** once the pipeline has initialised.

### Starting the 3D Avatar

```bash
# Open a separate terminal
start_avatar.bat
# Or launch the MateEngine Unity application directly from Mate-Engine/
```

The avatar connects automatically to Vivy's pipeline via WebSocket on port 8765.

---

## 🌐 API Reference

The web server exposes **60+ REST API endpoints**. Key endpoints include:

| Endpoint | Method | Description |
|---|---|---|
| `/api/send` | POST | Send a text message to Vivy |
| `/api/history` | GET | Retrieve chat history with audio URLs |
| `/api/status` | GET | Current pipeline status |
| `/api/health` | GET | Full system health report |
| `/api/cognitive/state` | GET | AGI cognitive subsystem state |
| `/api/internet/search` | POST | Execute an internet search |
| `/api/internet/status` | GET | Network and Tor status |
| `/api/perception/status` | GET | Full perception pipeline state |
| `/api/camera/start` | POST | Start camera perception |
| `/api/screen/start` | POST | Initiate screen sharing |
| `/api/memory` | GET | Inspect long-term memory |
| `/api/evolution/status` | GET | Self-evolution engine state |
| `/api/telemetry` | GET | Live telemetry event stream |
| `/api/config` | GET/POST | Read or update configuration |
| `/diagnostics` | GET | Developer diagnostic dashboard |

---

## 🔬 Validation & Testing

Vivy ships with a multi-stage automated validation and certification suite:

```bash
# System-level integration validation (all subsystems)
python validate_system.py

# Full 15-stage enterprise pipeline certification audit
python validate_pipeline_hyper.py

# Architecture graph and import validation
python architecture_validator.py

# Production stress test
python production_stress_tester.py
```

The certification suite validates:
- AST correctness across all 459+ Python source files
- 100% pipeline component discovery and mapping
- All inter-module communication channels and shared states
- All core dependency availability
- Flask endpoint signature integrity
- Memory schema compatibility
- Live DuckDuckGo search connectivity

---

## 🧩 Key Dependencies

| Category | Library |
|---|---|
| LLM Inference | `llama-cpp-python` |
| Speech Recognition | `whisper.cpp` (via subprocess) |
| Text-to-Speech | `TTS` (Coqui) |
| Voice Cloning | RVC (Retrieval-based Voice Conversion) |
| Vision / Object Detection | `ultralytics` (YOLO11), `mediapipe` |
| Web Framework | `flask`, `websockets` |
| Computer Vision | `opencv-python`, `Pillow` |
| Audio | `sounddevice`, `soundfile`, `librosa` |
| ML / NLP | `torch`, `transformers`, `onnxruntime` |
| Search | `duckduckgo-search` / `ddgs` |
| OCR | `tesseract` (via `pytesseract`) |
| Anonymous Networking | `stem` (Tor), `scapy` |
| Embeddings | `sentence-transformers` (BAAI/bge-small-en-v1.5) |
| System Monitoring | `psutil` |

---

## ⚙️ System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 8-core x86-64 | 12-core+ (for CPU LLM inference) |
| RAM | 16 GB | 32 GB |
| GPU VRAM | 6 GB (GPU layers) | 8–12 GB |
| Storage | 20 GB | 40 GB (models + audio data) |
| OS | Windows 10 64-bit | Windows 11 64-bit |
| Python | 3.10 | 3.11 |

> **Note:** Vivy runs fully on CPU if no compatible GPU is available. GPU acceleration is strongly recommended for LLM inference and RVC voice cloning performance.

---

## 🛡️ Privacy

Vivy is designed with privacy as a non-negotiable first principle:

- **100% local inference** — The LLM, Whisper STT, TTS, and vision models all run on your machine. No data is sent to external servers.
- **Anonymous internet routing** — All outbound web requests are routed through the Tor SOCKS5 network stack (or a Virtual Onion Sandbox when Tor is unavailable).
- **L2–L4 identity hopping** — The Address Bouncer engine automatically regenerates MAC-layer and network-layer identities every 45 seconds during active internet sessions.
- **Zero telemetry exfiltration** — All telemetry data is stored locally in `logs/`.

---

## 📄 Licensing

Vivy AI is licensed under the **Vivy AI License**.

This repository also contains **MateEngine**, located in the `Mate-Engine/` directory.

MateEngine and any files derived from it are licensed separately under the **MateEngine Pro License**. See `Mate-Engine/LICENSE` for details.

---

## 🤝 Contributing

Contributions that improve Vivy's capabilities, fix bugs, or extend her subsystems are welcome. Please ensure:

1. No features or pipeline connections are removed.
2. All changes are validated against `validate_system.py` before submission.
3. Code style follows the existing patterns (type annotations, docstrings, graceful fallbacks).
4. No API keys, cloud endpoints, or user-identifying information are introduced.

---

<div align="center">

*Built with 💙 for a future where AI companions are personal, private, and truly present.*

</div>
