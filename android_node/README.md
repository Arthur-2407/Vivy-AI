# Vivy Node

**Android edge client for Vivy AI**

Vivy Node is the Android distributed edge client for the Vivy AI ecosystem. It acts as a secure, authenticated bridge connecting mobile device capabilities (camera, microphone, display) to the primary Vivy Hub orchestrator.

> **Important:** This is a component of the larger **Vivy AI** platform. It is not a standalone AI assistant. Canonical, heavy computation remains on the primary Vivy host.

## Relationship to Main Vivy AI Project

The Android Node operates under the dynamic capability lease model dictated by the Vivy Hub. 
- **Host Execution:** The primary Vivy host runs the AGI Cognitive Core, Multimodal Fusion Engine, Voice Manager, and MateEngine runtime.
- **Node Execution:** The Android Node streams sensors to the Hub and renders output received from the Hub.

```text
User
 ↓
Vivy Node (Android)
 ↓
Vivy Hub (Primary Host)
 ↓
authentication & capability lease validation
 ↓
canonical Vivy service execution
 ↓
result/event/stream
 ↓
Vivy Node
```

## System Requirements

Because Vivy Node acts as a thin client streaming to the Hub, the hardware requirements are minimal. The heavy lifting (AI inference, LLMs) is done entirely on the Primary Host.

- **OS Minimum:** Android 8.0 (Oreo / API Level 26) or higher.
- **Hardware Minimum:** Any standard smartphone or tablet with at least 2 GB RAM, a working camera, and a microphone.
- **Hardware Recommended:** A modern device with 4 GB+ RAM is recommended for smooth, high-FPS bidirectional video and avatar streaming.
- **Network:** A stable, high-bandwidth local Wi-Fi connection to the Vivy Hub (5GHz recommended for low latency).

## Features

The following features are supported based on dynamic capability leases:

- **Hub Discovery & Connection:** UDP broadcast, mDNS ZeroConf, and Fast Reconnect caching. [IMPLEMENTED]
- **Authentication & Security:** PIN pairing, persistent cryptographic device identity, credential management. [IMPLEMENTED]
- **Camera Pipeline:** Streams device camera frames to the primary host's perception engine. [IMPLEMENTED]
- **Microphone Pipeline:** Captures and streams audio for Voice Activity Detection and Whisper transcription. [IMPLEMENTED]
- **Screen Sharing:** Captures the Android screen for VLM/OCR analysis. [PARTIAL]
- **Avatar Display:** Renders out-of-band HTTP streams of the 3D Avatar state. [PARTIAL]
- **Voice Identity & Cloning UI:** UI to interact with RVC models running on the primary host. [INTEGRATED]
- **Cognition & Actions:** UI interfaces to view blackboard cognition and approve action intents. [INTEGRATED]

## Security & Privacy

Vivy Node employs strict security mechanisms for distributed operation:
- **Authorization:** Capabilities (e.g., `vision.stream`, `audio.stream`) are explicitly leased by the Hub.
- **Identity Storage:** Uses `androidx.security.crypto` to encrypt persistent node identity tokens.
- **Local Control:** Only activated when explicitly connected and authorized by the host.

## Licensing and Attribution

Vivy Node is proprietary software authored by Satyajeet Aich, and inherits the **Vivy AI License** from the parent project. Please see the [`LICENSE`](./LICENSE) file for full details.

For third-party open-source components used by this Android app (such as Kotlin, AndroidX, and OkHttp), please see the [`NOTICE`](./NOTICE) file.
