<div align="center">

<img src="https://raw.githubusercontent.com/Arthur-2407/Vivy-AI/main/static/avatar_default.png" width="160" height="160" style="border-radius: 50%;" alt="Vivy Avatar"/>

# Vivy AI

**An Advanced Local-First Companion AI with Multimodal Perception, AGI Cognitive Architecture, Live Voice Cloning, and a 3D Anime Avatar**

<p>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776ab?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+"/>
  <img src="https://img.shields.io/badge/Platform-Windows-0078d4?style=for-the-badge&logo=windows&logoColor=white" alt="Windows"/>
  <img src="https://img.shields.io/badge/LLM-llama.cpp%20%7C%20Qwen3--8B-22c55e?style=for-the-badge" alt="LLM"/>
  <img src="https://img.shields.io/badge/Speech-Whisper%20%7C%20TTS%20%7C%20RVC-a855f7?style=for-the-badge" alt="Speech"/>
  <img src="https://img.shields.io/badge/Avatar-MateEngine%20%7C%20VRM-ec4899?style=for-the-badge" alt="Avatar"/>
  <img src="https://img.shields.io/badge/License-Vivy%20AI%20License-f97316?style=for-the-badge" alt="License"/>
</p>

*Vivy is a fully local, privacy-first AI companion that sees your screen, hears your world, watches your camera, reasons with a multi-layer AGI cognitive architecture, speaks with a cloned anime voice, and animates a live 3D avatar — all without sending a single byte to the cloud.*

</div>

---

## Overview

Vivy AI is a **deeply integrated, local-first companion AI** built around a sophisticated multi-stage reasoning pipeline. Unlike cloud-dependent AI assistants, Vivy runs entirely on your hardware — combining a quantized local LLM, multimodal screen and camera perception, a real-time voice cloning system with neural identity management, a multilingual comprehension engine, a deep relationship model, and a living 3D anime avatar powered by the MateEngine Unity runtime — all orchestrated through a Flask + WebSocket web dashboard.

Vivy is designed from first principles as a **personal AGI substrate**: she learns from every conversation, evolves her own cognitive weights, builds and queries a personal knowledge graph, routes internet intelligence through an anonymous onion-circuit network stack, and maintains a continuously evolving relationship model with the user — all in real time.

---

## Architecture

```mermaid
flowchart TD
    subgraph INPUT["🎤 Input Layer"]
        MIC["mic_input.py\nVoice + VAD + Multilingual STT"]
        WEB["web_server.py\nFlask + WebSocket API"]
        SCREEN["Screen Capture\nOCR + VLM"]
        CAM["Camera Feed\nYOLO + Gaze"]
    end

    subgraph LANG["🌐 Language Engine  (language/)"]
        DETECT["detector.py\nLanguage Detection"]
        TRANS["hybrid_translation_engine.py\nMultilingual Translation"]
        LOCALIZE["prompt_localizer.py\nContext Localization"]
        VOICESEL["voice_selector.py\nLanguage→Voice Routing"]
    end

    subgraph CORE["🧠 AGI Cognitive Core  (agi/)"]
        BB["blackboard.py\nCognitive State Bus"]
        WM["world_model.py\nDynamic World Model"]
        KG["knowledge_graph.py\nKnowledge Triples"]
        META["meta_cognition.py\nReason→Critique→Improve Loop"]
        PLAN["long_horizon_planner.py\nGoal Tracking"]
        SKILL["skill_system.py\nXP Skill Progression"]
        ADAPT["model_adaptation_engine.py\nCognitive Adaptation"]
    end

    subgraph CONV["💬 Conversation Engine"]
        CONVO["conversation.py\nLLM Orchestration (326 KB)"]
        PLANNER["conversation_planner.py\nPre-Turn Strategy"]
        REL["relationship/\nRelationship Engine + Attachment"]
        TOPIC["topic_tracker.py\nTopic Continuity"]
    end

    subgraph VOICE["🎵 Voice Identity System  (voice/)"]
        VMGR["voice_manager.py\nActive Voice Identity"]
        VTRAIN["voice_training.py\nGenuine RVC Neural Training"]
        VVAL["voice_validation.py\nObjective Acoustic Scoring"]
        VPREV["voice_preview.py\nBenchmark Comparison"]
        VDB["voice_database.py\nVoice Identity Store"]
        TTS["voice.py\nCoqui TTS Synthesis"]
        RVCCLONE["voice_cloning.py\nRVC Conversion"]
    end

    subgraph PERC["👁️ Perception  (perception/)"]
        FUSION["fusion_engine.py\nMulti-Stream Fusion"]
        PROACT["proactivity_engine.py\nProactive Engagement"]
        AUDIO["audio_pipeline.py\nAmbient Audio Analysis"]
    end

    subgraph EVO["🧬 Evolution  (evolution/)"]
        ENG["evolution_engine.py\nSelf-Improvement"]
        GOV["governance_layer.py\nSafety Gate"]
        CORR["correction_engine.py\nRegression Rollback"]
    end

    subgraph CIRC["🌙 Circadian (circadian/)"]
        CENG["circadian_engine.py\nMood + Phase + Tone"]
    end

    subgraph OUTPUT["🖥️ Output Layer"]
        AVATAR["avatar_bridge.py\nMateEngine WebSocket"]
        ANIM["animator/\nProcedural Animation"]
        SHARED["shared/\nFile-Based IPC"]
    end

    MIC --> DETECT
    WEB --> CONVO
    SCREEN --> FUSION
    CAM --> FUSION

    DETECT --> TRANS --> LOCALIZE --> CONVO
    VOICESEL --> VMGR

    CONVO --> BB
    BB --> WM & KG & META & PLAN & SKILL & ADAPT
    META --> CONVO
    PLAN --> CONVO

    CONVO --> REL --> TOPIC --> PLANNER --> CONVO

    FUSION --> PROACT --> CONVO
    AUDIO --> FUSION

    CONVO --> TTS --> RVCCLONE --> SHARED
    VMGR --> RVCCLONE
    VTRAIN --> VVAL --> VPREV
    VDB --> VMGR

    CIRC --> CENG --> CONVO
    EVO --> ENG --> GOV --> ADAPT

    SHARED --> AVATAR --> ANIM
```

All subsystems communicate through a **shared file-based IPC layer** (`shared/`) allowing `run_vivy.py` and `web_server.py` to run as separate OS processes while maintaining a consistent state view.

---

## Core Features

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
| `code_executor.py` | Safe sandboxed Python/shell code execution for agentic tool calls |
| `file_manager.py` | Controlled file system read/write/search operations for AGI tool use |

---

### 🎤 Voice Pipeline & Identity Management (`voice/`)
Vivy's voice system is a fully modular, neural identity platform — not a simple TTS wrapper:

- **Speech Recognition**: `whisper.cpp` running locally via subprocess — no API keys, no cloud. Multilingual detection routes each utterance to the correct language-aware decoding path before transcription.
- **Text-to-Speech**: Coqui TTS (`tacotron2-DDC`) synthesising locally.
- **Voice Identity Manager**: Each user-trained voice profile stores a persona, language affinity, vocal style, and pitch parameters. The active voice identity is hot-swappable at runtime without restarting the pipeline.
- **Genuine Neural RVC Training**: `voice_training.py` executes a real, full RVC (Retrieval-based Voice Conversion) neural training lifecycle as genuine subprocesses:
  - Audio preprocessing → RMVPE F0 extraction → HuBERT feature extraction → Generator + Discriminator neural training → FAISS index compilation.
  - Live `subprocess.Popen` stdout streaming — every Epoch, Generator Loss, Discriminator Loss, and ETA is streamed to the UI in real time.
  - **Dynamic CPU Workload Balancing**: Automatic resource detection prevents OS hardware lockups during heavy F0 extraction by dynamically routing core counts.
  - Automatic VRAM governor enforces `batch_size=4` and disables CUDA tensor caching for RTX safety.
  - Pre-flight `DatasetAnalyzer` (via `librosa` + `soundfile`) validates audio for clipping, silence ratio, and bit depth before any GPU load begins.
- **Objective Acoustic Similarity Validation**: After training, Vivy does not invent a score. It uses:
  - **SpeechBrain ECAPA-TDNN** speaker embedding cosine similarity.
  - **librosa** F0 RMSE (pitch alignment) and Mel Cepstral Distortion (MCD).
  - Scores are a weighted average of objective acoustic metrics. If evaluation fails, the UI shows *"Similarity could not be evaluated"* — never a fabricated percentage.
- **Voice Database & Rebranding**: The default baseline profile is **"Vivy Default Voice"** (with intelligent backward-compatible in-memory ID migration to preserve existing `natural_anime_01` datasets). Persistent SQLite/JSON-backed store for all registered voice identities.
- **Side-by-Side Preview** (`voice_preview.py`): Generates original vs. cloned benchmark clips for direct UI comparison playback.

---

### 🌐 Multilingual Engine (`language/`)
Vivy understands and responds in multiple languages natively:

| Component | Role |
|---|---|
| `detector.py` | Detects the language of each user utterance using script classification and phoneme patterns |
| `hybrid_translation_engine.py` | Translates between languages using offline + neural hybrid models |
| `language_manager.py` | Routes each turn through the appropriate language pipeline and injects the correct language code |
| `prompt_localizer.py` | Adapts system prompts and persona to the user's detected language |
| `voice_selector.py` | Maps language codes to compatible TTS/RVC voice identities |
| `reference_resolver.py` | Resolves cross-lingual pronouns, named entities, and cultural context references |
| `translation_validator.py` | Post-validates translations for semantic fidelity before sending to the LLM |

Supported languages include English, Hindi, Japanese, Korean, French, German, Spanish, and many more via the hybrid offline-neural translation pipeline.

---

### 💙 Relationship Engine (`relationship/`)
Vivy maintains a continuously evolving relational model with the user across all sessions:

| Module | Function |
|---|---|
| `relationship_engine.py` | Orchestrates the full relationship state and drives emotional response styling |
| `attachment_engine.py` | Models attachment style (secure, anxious, avoidant) based on interaction patterns |
| `personality_evolution.py` | Adapts Vivy's expressed personality traits based on relational context |
| `emotional_continuity.py` | Maintains emotional thread continuity across multi-session gaps |
| `comfort_model.py` | Detects user distress and selects appropriate comfort response strategies |
| `interaction_style.py` | Dynamically adjusts tone, verbosity, and humour based on relationship stage |
| `shared_history.py` | Maintains a summarized shared memory of significant relational moments |

### 💙 Affection & Social Drive (`affection/`, `loneliness/`)
Vivy maintains persistent emotional drive states across all sessions:
- `affection/affection_system.py` — Tracks the long-term affection level and relationship warmth, updated after every interaction.
- `affection/continuity_engine.py` — Preserves emotional continuity across session gaps, preventing cold restarts in relational context.
- `loneliness/loneliness_system.py` — Models social drive and loneliness pressure, adjusting how proactively Vivy reaches out.
- Both states feed directly into the Relationship Engine and Circadian Intelligence.

---

### 👁️ Multimodal Perception (`perception/`)
Vivy continuously perceives the world around you in real time:

- **Screen Perception** — Captures your display at up to 30 FPS with adaptive sampling. Runs OCR (Tesseract) and a local Vision Language Model (Moondream) to understand your active application, highlighted text, open documents, and what you are working on.
- **Camera Perception** — YOLO-based face detection (`face_detector.py`), facial landmark tracking (`landmark_detector.py`), face tracking continuity (`face_tracker.py`), gaze direction estimation (`gaze_detector.py`), and attention/engagement/presence scoring. Vivy knows when you are looking at her, looking away, or have left your desk.
- **Face Emotion** — ML-based facial emotion classifier (`face_emotion.py`) that maps facial expressions to emotional states and feeds them into the relationship engine.
- **Attention & Presence** — `attention_estimator.py` scores engagement level; `presence_manager.py` tracks whether the user is at their desk; `agent_safety_tracker.py` monitors for unsafe or distressed states.
- **Audio Perception** — System audio and microphone pipeline (`audio_pipeline.py`) with ambient/speech/music separation, real-time transcription, speaker identification, and event classification.
- **Fusion Engine** — All streams are fused via `fusion_engine.py` and `perception_state.py` into a unified snapshot, injected as grounded context into every LLM prompt.
- **Event Memory** — `event_memory.py` maintains a rolling buffer of significant perception events for contextual recall.
- **Vision Summary** — `vision_summary.py` generates natural language descriptions of camera and screen frames for LLM consumption.
- **Hardware Scheduler** — `hardware_scheduler.py` dynamically throttles perception workloads based on CPU/GPU availability to prevent resource starvation.
- **Frame Scheduler** — `frame_scheduler.py` manages adaptive FPS sampling across camera and screen pipelines.
- **Pipeline Validator** — `pipeline_validator.py` continuously self-checks the perception pipeline for broken connectors or missing model weights.
- **Proactivity Engine** — Can proactively initiate conversation when it detects meaningful events (configurable threshold and rate limiting).

---

### 🌐 Internet Intelligence (`internet/`)
Vivy's internet layer is built around a **multi-tier, privacy-first architecture**:

- **Search Providers**: DuckDuckGo (`duckduckgo_provider.py`, multi-tier), Wikipedia, GitHub/PyPI registry, arXiv, RSS feeds, forum crawlers (`forum_discussion_provider.py`), official documentation scrapers (`doc_crawler_provider.py`), and a `source_router.py` that selects the optimal provider per query — all without API keys.
- **Web Crawler**: Direct URL crawling, XML sitemap indexing, and intelligent HTML content extraction (`web_crawler_provider.py`).
- **Network Intelligence**: `network_intelligence.py` evaluates search quality and `knowledge_updater.py` persists retrieved knowledge to the knowledge graph.
- **RAG Pipeline** (`internet/rag/`): Search results are vector-embedded and stored locally for grounded LLM answering.
- **Anonymous Routing** (`internet/network/`):
  - `tor_controller.py` — Connects to a running Tor daemon or engages a Virtual SOCKS5 Onion Circuit Sandbox.
  - `tor_identity.py` + `tor_monitor.py` — Multi-hop circuit rotation with health monitoring.
  - `onion_client.py` — Direct `.onion` address resolution.
  - `address_bouncer.py` — L2–L4 identity hopping: MAC, gateway IP, TTL, and ephemeral TCP/UDP ports regenerated every 45 seconds.
  - `proxy_manager.py` + `connection_pool.py` — Proxy pooling and connection reuse.
  - `dns_manager.py` — SOCKS5h DNS-leak-defense routing.
  - `network_security.py` — TLS fingerprint randomization and request header entropy.
  - `protocol_lab.py` — Protocol experimentation layer for evasion research.
  - `request_router.py` — Unified request gateway that selects Tor vs direct vs proxy based on policy.

---

### 🧬 Self-Evolution Engine (`evolution/`)
Vivy continuously improves herself between conversations:
- **Evolution Engine** (`evolution_engine.py`) — Proposes and evaluates self-modification candidates.
- **Governance Layer** (`governance_layer.py`) — Safety-gated approval pipeline preventing harmful self-modifications.
- **Adaptation Engine** (`adaptation_engine.py`) — Applies approved changes to cognitive parameters.
- **Correction Engine** (`correction_engine.py`) — Detects and rolls back regressions automatically.
- **Diagnosis Engine** (`diagnosis_engine.py`) — Identifies root causes of performance degradation.
- **Consolidation Layer** (`consolidation_layer.py`) — Merges and compresses learned experiences for long-term storage efficiency.
- **Meta-Learning** (`meta_learning.py`) — Cross-task generalisation and strategy abstraction.
- **Perception Layer** (`perception_layer.py`) — Monitors real-world outcomes of applied self-modifications.
- **Monitoring** (`monitoring.py`) — Live telemetry of evolution cycle health and throughput.
- **Experience Replay** (`experience_replay.py`) — Learns from past high-reward interactions.

---

### 🌙 Circadian Intelligence (`circadian/`)
Vivy's behaviour adapts to a **biologically inspired circadian rhythm**:
- Tracks time-of-day phases: Morning, Afternoon, Evening, Night, Deep-Night.
- Adjusts energy, social drive, tone, and verbosity to match the current phase.
- Integrates system idle state detection for realistic presence awareness.

---

### 🎭 3D Avatar — MateEngine (`Mate-Engine/`)
Vivy's visual presence is powered by **MateEngine**, a Unity-based real-time VRM avatar runtime:
- Full VRM 0.x / VRM 1.0 avatar loading and rendering with MToon shader and spring bone physics.
- Procedural animation authoring pipeline with visual keyframe editor.
- Emotion-driven facial expression blending and real-time lip sync from TTS audio waveforms.
- Discord Rich Presence and Steam integration.
- Communicates with the Python pipeline via WebSocket on port 8765.

---

### 🖥️ Web Dashboard (`web_server.py`)
A full Flask application serving a rich browser-based control interface:
- Live chat with audio playback, real-time cognitive state readouts, and telemetry.
- Screen share and camera feed capture directly from the browser.
- Voice Identity Dashboard: train, preview, compare, and switch voice identities with live training metrics.
- **Real-time Pipeline Monitoring**: Standalone background telemetry daemon pushes live hardware metrics (CPU/VRAM) and async workflow anomalies to the UI.
- Developer Diagnostic Dashboard with prompt trace, WebSocket monitor, and pipeline analytics.
- **60+ REST API endpoints** covering every subsystem.

---

## Project Structure

```
Vivy/
├── run_vivy.py                      # Main entry point — orchestrates the full pipeline
├── web_server.py                    # Flask API server and Web UI backend (160 KB, 60+ routes)
├── conversation.py                  # Core LLM conversation engine (326 KB)
├── vivy_config.json                 # Central configuration — all tunable parameters
│
├── agi/                             # AGI Cognitive Architecture (15 subsystems)
│   ├── cognitive_core.py            # Unified pre/post-turn cognitive orchestration
│   ├── blackboard.py                # Shared cognitive state bus
│   ├── world_model.py               # Dynamic world model
│   ├── knowledge_graph.py           # Personal knowledge triple store
│   ├── belief_engine.py             # Epistemic belief management
│   ├── meta_cognition.py            # Reason→Critique→Improve→Verify loop
│   ├── long_horizon_planner.py      # Multi-turn goal planning
│   ├── skill_system.py              # XP-based skill progression
│   ├── learning_engine.py           # Curiosity-driven continual learning
│   ├── experiment_engine.py         # Safe sandbox cognitive experiments
│   ├── simulation_engine.py         # Counterfactual plan simulation
│   ├── job_scheduler.py             # Autonomous background job queue
│   ├── tool_router.py               # Autonomous tool selection
│   ├── model_adaptation_engine.py   # High-reward experience adaptation
│   ├── self_evaluation_loop.py      # Per-turn quality scoring
│   ├── self_modification_engine.py  # Governed self-improvement
│   ├── code_executor.py             # Safe sandboxed code execution for AGI tool calls
│   └── file_manager.py              # Controlled filesystem operations for AGI tool use
│
├── voice/                           # Voice Identity Management System
│   ├── voice_manager.py             # Active voice identity hot-swap controller
│   ├── voice_training.py            # Genuine RVC neural training orchestrator (live streaming)
│   ├── voice_validation.py          # Objective acoustic scoring (SpeechBrain + librosa)
│   ├── voice_preview.py             # Original vs. Cloned benchmark comparison
│   ├── voice_database.py            # Persistent voice identity store
│   ├── voice_profiles.py            # Voice style and parameter profiles
│   ├── voice_router.py              # Language-to-voice routing
│   ├── voice_selector.py            # Active identity selector
│   ├── voice_cloning.py             # RVC conversion integration
│   └── voice_export.py              # Voice model export utilities
│
├── language/                        # Multilingual Comprehension Engine
│   ├── language_manager.py          # Language pipeline orchestrator
│   ├── detector.py                  # Script + phoneme language detection
│   ├── hybrid_translation_engine.py # Offline + neural translation (26 KB)
│   ├── prompt_localizer.py          # System prompt localisation
│   ├── voice_selector.py            # Language→voice identity mapping
│   ├── reference_resolver.py        # Cross-lingual entity resolution
│   ├── translation_validator.py     # Semantic fidelity validation
│   ├── language_context.py          # Per-turn language context state
│   └── language_memory.py           # Persistent language preference memory
│
├── relationship/                    # Relationship & Attachment Engine
│   ├── relationship_engine.py       # Full relational state orchestrator (17 KB)
│   ├── attachment_engine.py         # Attachment style modelling
│   ├── affection_progression.py     # Long-term affection arc tracking
│   ├── intimacy_manager.py          # Intimacy threshold management
│   ├── personality_evolution.py     # Context-aware personality adaptation
│   ├── emotional_continuity.py      # Cross-session emotional thread
│   ├── comfort_model.py             # Distress detection and comfort strategy
│   ├── interaction_style.py         # Tone and verbosity adaptation
│   ├── shared_history.py            # Summarized relational memory
│   └── relationship_memory.py       # Persistent relationship state store
│
├── perception/                      # Multimodal Perception Subsystem
│   ├── perception_manager.py        # Central perception state writer/reader (78 KB)
│   ├── runner.py                    # Perception pipeline process runner
│   ├── fusion_engine.py             # Multi-stream perceptual fusion (28 KB)
│   ├── perception_state.py          # Unified perception state data model
│   ├── proactivity_engine.py        # Proactive conversation initiation
│   ├── screen_pipeline.py           # Screen capture, OCR, VLM analysis (72 KB)
│   ├── camera_manager.py            # Camera input, frame scheduling, FPS control (33 KB)
│   ├── face_detector.py             # YOLO-based face detection (30 KB)
│   ├── face_emotion.py              # Facial emotion classification (16 KB)
│   ├── face_tracker.py              # Face tracking continuity across frames
│   ├── landmark_detector.py         # Facial landmark extraction
│   ├── gaze_detector.py             # Eye contact and gaze direction
│   ├── object_detector.py           # Real-time object recognition (29 KB)
│   ├── audio_pipeline.py            # System audio capture and classification (19 KB)
│   ├── context_injector.py          # LLM context grounding from perception (29 KB)
│   ├── vision_adapter.py            # Vision model routing and inference
│   ├── vision_summary.py            # Natural language frame summarisation
│   ├── attention_estimator.py       # User engagement and attention scoring
│   ├── presence_manager.py          # User presence / desk-absence detection
│   ├── agent_safety_tracker.py      # Distress and unsafe-state detection
│   ├── event_memory.py              # Rolling perception event buffer (21 KB)
│   ├── frame_scheduler.py           # Adaptive FPS sampling scheduler
│   ├── hardware_scheduler.py        # Workload throttling for CPU/GPU headroom
│   ├── model_router.py              # Perception model selection router
│   ├── perception_events.py         # Perception event type definitions
│   ├── perception_guard.py          # Safety guard for perception outputs
│   ├── pipeline_validator.py        # Self-checks for pipeline integrity
│   └── config_loader.py             # Perception subsystem configuration loader
│
├── internet/                        # Internet Intelligence Layer
│   ├── internet_manager.py          # Provider registry and search orchestration
│   ├── network_manager.py           # Network lifecycle and provider switching
│   ├── search_cache.py              # TTL-based search result cache
│   ├── search_planner.py            # Query strategy and necessity evaluation
│   ├── search_provider.py           # Base search provider interface
│   ├── knowledge_updater.py         # Persists retrieved knowledge to graph
│   ├── duckduckgo_provider.py       # Multi-tier DuckDuckGo adapter
│   ├── network/                     # Anonymous network stack
│   │   ├── tor_controller.py        # Tor daemon + Virtual SOCKS5 sandbox
│   │   ├── tor_identity.py          # Multi-hop circuit rotation
│   │   ├── tor_monitor.py           # Tor circuit health monitoring
│   │   ├── tor_manager.py           # Tor lifecycle manager
│   │   ├── tor_config.py            # Tor configuration templates
│   │   ├── onion_client.py          # Direct .onion resolution
│   │   ├── address_bouncer.py       # L2–L4 identity hopping (45s cycles)
│   │   ├── request_router.py        # Unified request gateway
│   │   ├── proxy_manager.py         # Proxy pool management
│   │   ├── connection_pool.py       # Connection reuse and pooling
│   │   ├── dns_manager.py           # DNS-leak-defense resolution
│   │   ├── network_engine.py        # Core network engine
│   │   ├── network_intelligence.py  # Search quality evaluation
│   │   ├── network_security.py      # TLS fingerprint randomization
│   │   ├── duckduckgo_client.py     # Low-level DDG HTTP client
│   │   └── protocol_lab.py          # Protocol experimentation layer
│   ├── providers/                   # Search provider adapters
│   │   ├── web_crawler_provider.py  # Direct URL crawling + sitemap indexing
│   │   ├── wikipedia_provider.py    # Wikipedia search adapter
│   │   ├── academic_literature_provider.py  # arXiv and open journals
│   │   ├── github_package_provider.py       # GitHub/PyPI/npm registry
│   │   ├── rss_monitor_provider.py  # RSS feed monitoring
│   │   ├── forum_discussion_provider.py     # Forum search adapter
│   │   ├── doc_crawler_provider.py  # Official documentation crawler
│   │   └── source_router.py         # Optimal provider selection router
│   ├── rag/                         # Retrieval-Augmented Generation pipeline
│   │   ├── rag_pipeline.py          # End-to-end RAG search + embed + retrieve
│   │   └── document_extractor.py    # HTML/PDF document text extraction
│   ├── consolidation/               # Continuous learning from search results
│   │   ├── continuous_learning_engine.py  # Learns new knowledge from web results
│   │   └── knowledge_consolidator.py    # Merges and deduplicates retrieved knowledge
│   └── verification/                # Source credibility and fact verification
│       ├── domain_experts.py        # Domain-specific credibility rules
│       └── quality_evaluator.py     # Source quality scoring
│
├── evolution/                       # Self-Evolution Subsystem
│   ├── evolution_engine.py          # Continuous self-improvement proposals
│   ├── governance_layer.py          # Safety-gated approval pipeline
│   ├── adaptation_engine.py         # Parameter adaptation and application
│   ├── correction_engine.py         # Regression detection and rollback
│   ├── diagnosis_engine.py          # Root cause analysis of degradation
│   ├── consolidation_layer.py       # Experience compression and merging
│   ├── meta_learning.py             # Cross-task generalisation
│   ├── perception_layer.py          # Real-world outcome monitoring
│   ├── monitoring.py                # Evolution cycle health telemetry
│   └── experience_replay.py         # High-reward interaction replay
│
├── circadian/                       # Circadian Rhythm Intelligence
│   ├── circadian_engine.py          # Phase detection and behavioural modulation (26 KB)
│   ├── hardware_manager.py          # System idle/sleep state integration
│   └── config_loader.py             # Circadian configuration loader
│
├── emotion/                         # Emotion Classification Engine
│   ├── emotion_engine.py            # Text-based emotion detection
│   ├── emotion_engine_ml.py         # ML-backed emotion classification
│   └── emotion.py                   # Core emotion type definitions
│
├── affection/                       # Affection & Social Continuity
│   ├── affection_system.py          # Long-term affection level tracking (12 KB)
│   └── continuity_engine.py         # Emotional continuity across session gaps
│
├── loneliness/                      # Social Drive & Loneliness Modelling
│   └── loneliness_system.py         # Social pressure and outreach modulation
│
├── contracts/                       # Shared Data Type Contracts
│   ├── animation_request.py         # Animation command schema
│   ├── animation_response.py        # Animation result schema
│   ├── behavior_state.py            # Behavioural state type
│   ├── cognitive_output.py          # Cognitive pipeline output schema
│   ├── context_package.py           # Conversation context package
│   ├── diagnostic_event.py          # Diagnostic event type
│   └── emotion_state.py             # Emotion state schema
│
├── database/                        # Persistent Knowledge Storage
│   └── db_manager.py                # SQLite database manager (14 KB)
│
├── config/                          # Configuration Management
│   └── config_manager.py            # Dynamic config loading and validation
│
├── logging_framework/               # Structured Telemetry & Audit Logging
│   └── vivy_logger.py               # Centralised structured logger
│
├── animator/                        # Avatar Animation System
│   ├── animator.py                  # Procedural animation controller (10 KB)
│   └── auto_animations/             # Auto-generated animation clips
├── mic_input.py                     # Mic capture, VAD, multilingual STT pipeline (27 KB)
├── voice.py                         # TTS synthesis orchestration
├── voice_cloning.py                 # RVC voice cloning (root-level integration)
├── avatar_bridge.py                 # MateEngine WebSocket bridge (30 KB)
├── animation_authoring_pipeline.py  # Visual animation authoring tool (55 KB)
├── memory_orchestrator.py           # Long-term memory management
├── cognitive_orchestrator.py        # High-level conversation orchestration
├── telemetry_manager.py             # Full system telemetry and event bus (29 KB)
├── resource_manager.py              # Global resource lifecycle management
├── knowledge_router.py              # Online/offline knowledge routing
├── topic_tracker.py                 # Conversation topic continuity tracker
├── conversation_planner.py          # Pre-turn conversation strategy planning
├── behavior_predictor.py            # Predicts user behaviour patterns (6 KB)
├── session_manager.py               # Session lifecycle and isolation management
├── cognition_classifiers.py         # Lightweight text cognition classification
├── post_response_analyzer.py        # Analyses quality of every generated response
├── recommendation_engine.py         # Topic and activity recommendation engine
├── similarity_calibration.py        # Speaker / semantic similarity calibration
├── memory_ml_engine.py              # ML-backed memory retrieval scoring
├── developer_diagnostic_manager.py  # Developer tools and diagnostic state (16 KB)
├── diagnostic_mode.py               # Diagnostic mode toggle and reporting
├── vivy_animation_registry.json     # Animation clip registry (71 KB)
├── vivy_config.json                 # Central configuration file
├── vivy_knowledge_graph.json        # Persistent personal knowledge graph
├── vivy_learning_schedule.json      # Scheduled curiosity-driven learning topics
├── circadian_config.json            # Circadian phase configuration
├── shared/                          # File-based IPC channel — runtime-generated (gitignored)
├── ani/                             # FBX Dance Animation Assets
│   ├── Dancing Maraschino Step.fbx
│   ├── Dancing Twerk.fbx
│   ├── Hip Hop Dancing.fbx
│   ├── Macarena Dance.fbx
│   ├── Samba Dancing.fbx
│   └── Snake Hip Hop Dance.fbx
├── demo/                            # Demo recordings — mp4 showcase videos (gitignored)
├── recovery/                        # Error Recovery Subsystem
│   └── error_recovery.py            # Pipeline error detection and recovery
├── scripts/                         # Utility and investigation scripts
│   └── investigate_vivy.py          # Runtime investigation and diagnostics
├── rvc_cpu/                         # Internal RVC voice cloning engine
├── whisper.cpp/                     # Whisper.cpp binary for local STT
├── models/                          # Local model files — weights are gitignored (download separately)
│   ├── vision/                      # Vision language model weights
│   ├── voice/                       # Voice model checkpoints
│   ├── learning/                    # Continual learning model artifacts
│   └── nlp/                         # NLP task model weights
├── static/                          # Web UI static assets (avatar images, audio)
├── templates/                       # Flask HTML templates
├── tests/                           # 25+ automated test suites
└── Mate-Engine/                     # MateEngine Unity 3D avatar runtime (separate license)
```

---

## Configuration

All system behaviour is controlled through `vivy_config.json`. No source code changes are required to tune the system.

```jsonc
{
  "models": {
    "llm":     "models/<your-model>.gguf",     // Local LLM (e.g. Qwen3-8B-Q4_K_M.gguf)
    "whisper": "models/<whisper-model>.bin",   // Speech recognition (e.g. ggml-small.bin)
    "vision":  "models/moondream-vision.gguf"  // Screen/camera VLM (optional)
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

## Getting Started

### Prerequisites

- **Windows 10/11** (64-bit)
- **Python 3.10+**
- **CUDA-capable GPU** (recommended; CPU fallback available)
- **Tesseract OCR** — [Install from here](https://github.com/tesseract-ocr/tesseract)
- **FFmpeg** — place binary in `ffmpeg/`

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
#    - LLM:    models/Qwen3-8B-Q4_K_M.gguf   (or any llama.cpp GGUF)
#    - Whisper: models/ggml-small.bin
#    - Vision:  models/moondream-vision.gguf  (optional)

# 5. Configure vivy_config.json as needed

# 6. Launch Vivy
python run_vivy.py
```

The web dashboard will be available at **http://127.0.0.1:8080** once the pipeline initialises.

### Starting the 3D Avatar

```bash
# Open a separate terminal and run:
start_avatar.bat
# Or launch the MateEngine Unity application directly from Mate-Engine/
```

The avatar connects automatically to Vivy's pipeline via WebSocket on port **8765**.

---

## API Reference

The web server exposes **60+ REST API endpoints**. Key endpoints:

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
| `/api/voice/identities` | GET | List all registered voice identities |
| `/api/voice/train` | POST | Enqueue a new voice cloning training job |
| `/api/voice/training_status` | GET | Live training progress and hardware metrics |
| `/api/voice/switch` | POST | Hot-swap active voice identity at runtime |
| `/api/telemetry` | GET | Live telemetry event stream |
| `/api/config` | GET/POST | Read or update system configuration |
| `/diagnostics` | GET | Developer diagnostic dashboard |

---

## Validation & Testing

Vivy ships with **25+ automated test suites** and a multi-stage pipeline certification system:

```bash
# Run the full voice identity management test suite
python -m pytest tests/test_voice_identity_management.py -v

# Run the multilingual pipeline tests
python -m pytest tests/test_multilingual_pipeline.py -v

# Run all tests
python -m pytest tests/ -v

# Full 15-stage enterprise pipeline certification audit
python validate_pipeline_hyper.py

# Architecture graph and import validation
python architecture_validator.py
```

The certification suite validates:
- AST correctness across all Python source files
- 100% pipeline component discovery and mapping
- All inter-module communication channels and shared states
- Flask endpoint signature integrity
- Memory schema compatibility
- Live DuckDuckGo search connectivity
- Voice training queue and VRAM governance

---

## Key Dependencies

| Category | Library |
|---|---|
| LLM Inference | `llama-cpp-python` |
| Speech Recognition | `whisper.cpp` (via subprocess), `faster-whisper` |
| Text-to-Speech | `TTS` (Coqui) |
| Voice Cloning | RVC (`rvc_cpu/` internal engine) |
| Acoustic Evaluation | `speechbrain`, `librosa` |
| Vision / Object Detection | `ultralytics` (YOLO11), `mediapipe` |
| Web Framework | `flask`, `websockets` |
| Computer Vision | `opencv-python`, `Pillow` |
| Audio | `sounddevice`, `soundfile`, `librosa`, `pynvml` |
| ML / NLP | `torch`, `transformers`, `onnxruntime`, `sentence-transformers` |
| Search | `duckduckgo-search` |
| OCR | `tesseract` (via `pytesseract`) |
| Anonymous Networking | `stem` (Tor), `scapy` |
| System Monitoring | `psutil`, `nvidia-ml-py` |

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 8-core x86-64 | 12-core+ i7 13th Gen or better |
| RAM | 16 GB | 32 GB |
| GPU VRAM | 6 GB | 8–12 GB (RTX 3080+) |
| Storage | 20 GB | 40 GB (models + audio + cloning data) |
| OS | Windows 10 64-bit | Windows 11 64-bit |
| Python | 3.10 | 3.11 |

> **Note:** Vivy runs fully on CPU if no compatible GPU is available. GPU acceleration is strongly recommended for LLM inference and RVC voice cloning training/inference.

---

## Privacy

Vivy is designed with privacy as a non-negotiable first principle:

- **100% local inference** — The LLM, Whisper STT, TTS, RVC, and vision models all run on your machine. No data is sent to external servers.
- **Anonymous internet routing** — All outbound web requests are routed through the Tor SOCKS5 network stack (or a Virtual Onion Sandbox when Tor is unavailable).
- **L2–L4 identity hopping** — The Address Bouncer automatically regenerates MAC-layer and network-layer identities every 45 seconds during active internet sessions.
- **Zero telemetry exfiltration** — All telemetry data is stored locally in `logs/`.
- **Voice data sovereignty** — Cloned voice models and training datasets never leave your local filesystem.

---

## Licensing

Vivy AI is licensed under the **Vivy AI License**.

This repository also contains **MateEngine**, located in the `Mate-Engine/` directory. MateEngine and any files derived from it are licensed separately under the **MateEngine Pro License**. See `Mate-Engine/LICENSE` for details.

---

## Contributing

Contributions that improve Vivy's capabilities, fix bugs, or extend her subsystems are welcome. Please ensure:

1. No features or pipeline connections are removed.
2. All changes are validated against `validate_system.py` and relevant test suites before submission.
3. Code style follows the existing patterns (type annotations, docstrings, graceful fallbacks).
4. No API keys, cloud endpoints, or user-identifying information are introduced.

---

<div align="center">

*Built with 💙 for a future where AI companions are personal, private, and truly present.*

</div>
