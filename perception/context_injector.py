"""
perception/context_injector.py
================================
Adapter between the FusionEngine/EventMemory and the LLM prompt.
Prioritizes: current scene, recent dialogue, intent, and memories.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def get_perception_context(screen_context: str = "", token_budget: int = None, wants_vision: bool = True, wants_audio: bool = True, is_perception_query: bool = False) -> str:
    """
    Build a unified hierarchical perception context string for LLM injection.

    Filters out redundant screen events if screen_context is already populated,
    but keeps high-importance screen events (OCR/VLM) that add value.

    Gap 4 fix: Returns any non-empty content, not just content > 2 lines.
    Fine-grained upgrade: Prepends a live snapshot of actual content (OCR text,
    VLM caption, audio description) from PerceptionManager as Section 0.
    """
    import os
    if os.environ.get("VIVY_PROCESS_ROLE") == "runner":
        try:
            import requests
            url = "http://127.0.0.1:8080/api/perception/context"
            params = {}
            if screen_context:
                params["screen_context"] = screen_context
            if token_budget:
                params["token_budget"] = token_budget
            if wants_vision is not True:
                params["wants_vision"] = "false"
            if wants_audio is not True:
                params["wants_audio"] = "false"
            if is_perception_query:
                params["is_perception_query"] = "true"
            resp = requests.get(url, params=params, timeout=2.5)
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            logger.debug(f"[ContextInjector] HTTP fetch failed: {e}. Falling back to disk load...")
            try:
                from perception.fusion_engine import get_global_engine
                get_global_engine()._memory.load_state()
            except Exception as _err:
                print(f"[context_injector.py] Silenced exception: {_err}")

    try:
        from perception.config_loader import get
        # Increase budget to 800 tokens (3200 chars) for richer perception data
        budget = token_budget or int(get("multimodal", "context_token_budget", default=800))
        char_budget = budget * 4

        from perception.fusion_engine import get_global_engine
        engine = get_global_engine()
        memory = engine._memory

        # Get session components from memory
        long_term       = memory.get_long_term_memories()
        episodes        = memory.get_episodic_summaries()
        rolling_summary = memory._summary

        # Get recent events within the retention window (last 5 minutes)
        recent = engine.get_recent_events(max_age_seconds=300)

        # Filter events:
        # - If screen_context present: keep high-importance screen events (OCR/VLM rich)
        #   but skip low-importance heuristic-only screen duplicates.
        # - Always filter out noise-only events that don't add context value.
        def _should_include(e: dict) -> bool:
            src = e.get("source", "")
            sem = e.get("semantic", "")
            imp = e.get("importance", 0.5)

            # Skip low-signal user_action events that just echo emotion labels
            if src == "user_action" and sem.startswith("Vivy responded with emotion:"):
                return False

            # If we already have file-based screen_context, skip low-importance screen events
            # but keep high-importance ones (OCR text, vision descriptions)
            if screen_context and src == "screen" and imp < 0.8:
                return False

            return True

        filtered = [e for e in recent if _should_include(e)]

        # Sort chronologically
        filtered.sort(key=lambda x: x["timestamp"])

        lines: list[str] = []
        used = 0

        # ── SECTION HEADER ──────────────────────────────────────────────────────
        section_header = "[Multimodal Perception Log — What Vivy is observing in the background]"
        lines.append(section_header)
        used += len(section_header) + 1

        # ── SECTION 0: Live Fine-Grained Content Snapshot (NEW) ─────────────────
        # Pull actual content (OCR text, VLM caption, audio description) from
        # PerceptionManager. This is the most critical section for answering
        # specific perception queries like "what word is highlighted" or "what do you hear".
        try:
            snapshot = _build_live_snapshot(wants_vision=wants_vision, wants_audio=wants_audio, has_screen_context=bool(screen_context))
            if snapshot and used + len(snapshot) + 5 <= char_budget:
                lines.append(snapshot)
                used += len(snapshot) + 1
                logger.debug(f"[ContextInjector] Live snapshot injected: {len(snapshot)} chars")
        except Exception as snap_err:
            logger.debug(f"[ContextInjector] Live snapshot failed (non-fatal): {snap_err}")

        # ── 1. Observation Narrative (rolling summary from FusionEngine) ────────
        # This is a synthesized plain-text narrative: "Vivy has been watching X for Y minutes"
        try:
            narrative = engine.get_observation_narrative()
            if narrative and used + len(narrative) + 5 <= char_budget:
                lines.append(narrative)
                used += len(narrative) + 1
        except Exception as _err:
            print(f"[context_injector.py] Silenced exception: {_err}")  # Narrative not available yet — graceful fallback

        # ── 2. Inject approved long-term memories ────────────────────────────────
        if long_term and used < char_budget:
            lt_header = "[Important Relational Memories]"
            if used + len(lt_header) + 1 <= char_budget:
                lines.append(lt_header)
                used += len(lt_header) + 1
                for lt in long_term:
                    line = f"• {lt}"
                    if used + len(line) + 1 > char_budget:
                        break
                    lines.append(line)
                    used += len(line) + 1

        # ── 3. Inject episodic scene summaries ───────────────────────────────────
        if episodes and used < char_budget:
            ep_header = "[Recent Scene Summary]"
            if used + len(ep_header) + 1 <= char_budget:
                lines.append(ep_header)
                used += len(ep_header) + 1
                for ep in reversed(episodes):
                    line = f"• {ep}"
                    if used + len(line) + 1 > char_budget:
                        break
                    lines.append(line)
                    used += len(line) + 1

        # ── 4. Inject rolling evicted summary ────────────────────────────────────
        if rolling_summary and used + len(rolling_summary) + 30 <= char_budget:
            rs_line = f"[Earlier activity summary] {rolling_summary}"
            lines.append(rs_line)
            used += len(rs_line) + 1

        # ── 5. Inject recent timeline observations ───────────────────────────────
        if filtered and used < char_budget:
            recent_header = "[Recent observations, newest first]"
            if used + len(recent_header) + 1 <= char_budget:
                lines.append(recent_header)
                used += len(recent_header) + 1

            for ev in reversed(filtered):  # newest first
                ts   = _fmt_ts(ev["timestamp"])
                src  = ev.get("source", "?")
                sem  = ev.get("semantic", "")
                line = f"[{ts}] ({src}) {sem}"
                if used + len(line) + 1 > char_budget:
                    break
                lines.append(line)
                used += len(line) + 1

        # ── Gap 4 fix: return any non-empty content ──────────────────────────────
        # Previously returned "" if len(lines) <= 2 — this caused empty context
        # even when real events existed. Now we return anything beyond the header.
        if len(lines) <= 1:
            # Only the header was added — no real content
            return ""

        return "\n".join(lines)

    except Exception as e:
        logger.debug(f"[ContextInjector] get_perception_context() failed: {e}")
        return ""


def build_prompt_section(perception_context: str) -> str:
    """
    Wrap the perception context in a prompt-ready section block.
    Called by conversation.build() when perception_context is non-empty.
    """
    if not perception_context:
        return ""
    return (
        "\n\n[PERCEPTION LOG — What Vivy is currently observing]\n"
        + perception_context
        + "\n[END PERCEPTION LOG]"
    )


def _get_semantic_scene_understanding(snap: dict) -> str:
    if not snap:
        return "I can't see your screen right now."
        
    app = snap.get("current_app_type", snap.get("app_type", "unknown"))
    win_title = snap.get("active_window_title", "")
    
    # Priority check: If a high-level VLM caption (e.g. Florence-2) exists for the screen, use it as the base
    vlm_caption = snap.get("screen_vlm_caption", "")
    if vlm_caption:
        return f"VLM Analysis: {vlm_caption}"

    ocr_text = snap.get("last_ocr_text", snap.get("ocr_text", "")).strip()
    ocr_lower = ocr_text.lower()
    ocr_conf = snap.get("ocr_confidence", 1.0)
    
    # Heuristics for visual cues from state
    brightness = snap.get("brightness", 50.0)
    is_dark = brightness < 40 or "dark" in app.lower() or "dark" in win_title.lower()
    mode = "dark theme" if is_dark else "light theme"
    
    # Try to extract sidebar details from scene_layout if available
    layout = snap.get("scene_layout", {})
    has_sidebar = False
    if layout and isinstance(layout, dict):
        has_sidebar = any(z.get("name") == "sidebar" or "sidebar" in z.get("name", "").lower() for z in layout.get("zones", []))
    
    # Fallback to general checks if no layout zone
    if not has_sidebar:
        has_sidebar = snap.get("has_sidebar", False) or "sidebar" in ocr_lower
        
    density = snap.get("content_density", "moderate content")
    if not density or density == "moderate content":
        # Guess based on OCR length
        if len(ocr_text) > 400:
            density = "dense layout with text"
        elif len(ocr_text) > 100:
            density = "moderate layout"
        else:
            density = "mostly visual or sparse content"

    layout_desc = f"a {mode}"
    if has_sidebar:
        layout_desc += " with a sidebar panel"
    if density:
        layout_desc += f", showing a {density}"

    # 1. YouTube
    if "youtube" in app.lower() or "youtube" in win_title.lower() or "youtube" in ocr_lower:
        video_title = ""
        if "playing '" in app:
            import re
            m = re.search(r"playing '([^']+)'", app)
            if m:
                video_title = m.group(1)
        if not video_title and " - " in win_title:
            candidate = win_title.split(" - ")[0].strip()
            if not any(x in candidate.lower() for x in ("vivy ai", "localhost", "127.0.0.1", "dashboard")):
                video_title = candidate
        if not video_title:
            for line in ocr_text.split("\n"):
                if any(k in line.lower() for k in ["nightcore", "official video", "music video", "lyrics", " - "]) and len(line) < 120:
                    video_title = line.strip()
                    break
        
        clarity_note = ""
        if ocr_conf < 0.70 and ocr_text:
            clarity_note = " (some details are a bit blurry)"
            
        if video_title:
            return f"a browser window playing a YouTube video titled \"{video_title}\" in {mode}. The interface shows the main video player and control bar, with recommendation columns and a sidebar of recommendations{clarity_note}."
        return f"a web browser window open to YouTube in {mode}, browsing videos{clarity_note}."

    # 2. Manga/Manhwa
    if any(k in ocr_lower for k in ["chapter", "manga", "manhwa", "webtoon", "scanlation", "comic"]) or any(k in win_title.lower() for k in ["manga", "manhwa", "webtoon", "chapter"]):
        chapter_title = ""
        for line in ocr_text.split("\n"):
            if "chapter" in line.lower() and len(line) < 100:
                chapter_title = line.strip()
                break
        if not chapter_title:
            for line in ocr_text.split("\n"):
                if any(k in line.lower() for k in ["max-level", "leveling", "reincarnation", "player", "returner", "hero", "sword"]) and len(line) < 100:
                    chapter_title = line.strip()
                    break
                    
        clarity_note = ""
        if ocr_conf < 0.70 and ocr_text:
            clarity_note = " (the text is small or slightly blurry)"
            
        if chapter_title:
            return f"a document or manga reader showing chapter \"{chapter_title}\" in {layout_desc}{clarity_note}."
        return f"an online manga or comic page in {layout_desc}{clarity_note}."

    # 3. Code Editor
    if "code" in app.lower() or "visual studio" in win_title.lower() or "vscode" in win_title.lower():
        file_name = ""
        if " - " in win_title:
            file_name = win_title.split(" - ")[0].strip()
        if file_name and "." in file_name:
            return f"Visual Studio Code open in {mode}, actively editing the file `{file_name}`. The workspace layout has a {density} editor area{', and the sidebar tree explorer is open on the left' if has_sidebar else ''}."
        return f"Visual Studio Code open in {mode}, editing code{' with the sidebar panel visible' if has_sidebar else ''}."

    # 4. Search Engines
    if "google search" in app.lower() or "google search" in win_title.lower():
        return f"Google Search results in {layout_desc}."

    # 5. Generic Browser
    if "browser" in app.lower() or "edge" in app.lower() or "chrome" in app.lower() or "firefox" in app.lower():
        page_title = win_title
        for suffix in [" - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox", " - Chrome", " - Edge"]:
            if page_title.endswith(suffix):
                page_title = page_title[:-len(suffix)]
                break
        
        clarity_note = ""
        if ocr_conf < 0.70 and ocr_text:
            clarity_note = " (some layout details are visible, though some text is too small or blurry to read in full detail)"
            
        if page_title and not any(x in page_title.lower() for x in ("vivy ai", "localhost", "127.0.0.1", "dashboard")):
            return f"a browser window in {mode} showing the page \"{page_title}\". The screen layout shows a {density} page{', with a sidebar panel' if has_sidebar else ''}{clarity_note}."
        return f"a browser window open in {mode} showing a {density} webpage{', with a sidebar panel' if has_sidebar else ''}{clarity_note}."

    # 6. Terminal/Console
    if "terminal" in app.lower() or "console" in snap.get("active_window_title", "").lower() or "cmd" in app.lower() or "powershell" in app.lower():
        return f"a terminal console or command-line interface in {layout_desc}."

    # 7. Fallback
    if app and app != "unknown":
        return f"{app} open in {layout_desc}."
    return f"your desktop screen showing {layout_desc}."


def _build_live_snapshot(wants_vision: bool = True, wants_audio: bool = True, has_screen_context: bool = False) -> str:
    """
    Build a labeled block of ACTUAL current perception content for LLM injection.
    This is the fine-grained answer source — distinct from the heuristic event timeline.

    Pulls from PerceptionManagerReader.get_live_perception_snapshot() which reads
    from perception_state.json (written by the web_server.py process).

    Returns a formatted string, or "" if no meaningful content is available.
    """
    try:
        from perception.perception_manager import get_reader
        snap = get_reader().get_live_perception_snapshot()

        screen_active = snap.get("screen_active") and wants_vision
        audio_active = snap.get("audio_active") and wants_audio
        camera_active = snap.get("camera_active", False)

        if not screen_active and not audio_active and not camera_active:
            return ""  # Nothing active — don't pollute the context

        parts = ["[Live Perception Snapshot — FACTUAL, quote directly to answer questions]"]

        # Camera & User Face/Gaze Observations
        if camera_active:
            presence_st = snap.get("presence_state", "User Present")
            face_cnt = snap.get("face_count", 0)
            face_det = snap.get("face_detected", False) or (face_cnt > 0)
            parts.append(f"  User Camera Status: Active (Camera ON, state: {presence_st}, {face_cnt} face(s) tracked)")
            if face_det:
                g_dir = snap.get("gaze_direction", "Looking At Vivy")
                e_score = snap.get("eye_contact_score", 0.0)
                h_orient = snap.get("head_orientation", "Head Facing Vivy")
                parts.append(f"  Eye Contact & Gaze: {g_dir} (eye contact score: {e_score:.2f}, head pose: {h_orient})")
                p_face = snap.get("primary_face")
                if isinstance(p_face, dict) and p_face.get("bbox"):
                    bbox = p_face["bbox"]
                    parts.append(f"  Primary Face Box: x={bbox.get('x',0)}, y={bbox.get('y',0)}, w={bbox.get('width',0)}, h={bbox.get('height',0)}, confidence={p_face.get('confidence', 0.85):.2f}")
            else:
                parts.append("  Face Detection Status: No faces currently detected in camera field of view")
            
            # Hand tracking & holding state
            hand_st = snap.get("hand_state", {})
            hands_tr = hand_st.get("hands_tracked", 0)
            holding_det = hand_st.get("holding_detected", False)

            if hands_tr > 0:
                hands_list = hand_st.get("hands", [])
                h_details = [f"{h.get('hand_label','Hand')}: {h.get('gesture','Active')} ({'holding item' if h.get('holding_item') else 'empty'})" for h in hands_list if isinstance(h, dict)]
                parts.append(f"  Hand Tracking Status: {hands_tr} hand(s) tracked [{'; '.join(h_details)}]")
            else:
                parts.append("  Hand Tracking Status: No hands currently in camera frame")

            held_objs = snap.get("held_objects", [])
            obj_cnt = snap.get("object_count", 0)
            objs = snap.get("detected_objects", [])

            if held_objs:
                h_names = ", ".join([f"{o.get('label','item')} ({int(o.get('confidence',0.8)*100)}% conf)" for o in held_objs if isinstance(o, dict)])
                parts.append(f"  Objects Held in Hand: {len(held_objs)} item(s) held [{h_names}]")

            if obj_cnt > 0 or objs:
                obj_details = []
                for o in objs:
                    if isinstance(o, dict):
                        lbl = o.get("label", "item")
                        conf = o.get("confidence", 0.8)
                        obj_details.append(f"{lbl} ({int(conf*100)}% conf)")
                obj_names = ", ".join(obj_details) if obj_details else "items in view"
                parts.append(f"  Detected Camera Objects (in view): {len(objs)} object(s) detected [{obj_names}]")
            else:
                parts.append("  Detected Camera Objects: No additional standalone objects detected in view")

            cam_vlm = snap.get("camera_vlm_caption", "")
            if cam_vlm:
                parts.append(f"  Camera Visual Scene Description (VLM): {cam_vlm}")
        else:
            parts.append("  User Camera Status: Inactive (Camera OFF)")

        # Vision content
        if screen_active:
            scene_summary = _get_semantic_scene_understanding(snap)
            parts.append(f"  High-level Screen Context: {scene_summary}")

            win_title = snap.get("active_window_title", "")
            if win_title:
                is_vivy = any(x in win_title.lower() for x in ("vivy ai", "neural interface", "127.0.0.1:8080", "localhost:8080"))
                if is_vivy:
                    parts.append(f"  Focused window title: \"{win_title}\" (Note: This is Vivy's own chat dashboard; the user is currently typing to Vivy)")
                else:
                    parts.append(f"  Focused window title: \"{win_title}\"")
                rect = snap.get("active_window_rect", [0, 0, 0, 0])
                if rect != [0, 0, 0, 0]:
                    parts.append(f"  Focused window bounds: left={rect[0]}, top={rect[1]}, right={rect[2]}, bottom={rect[3]}")

            cx = snap.get("cursor_x", 0)
            cy = snap.get("cursor_y", 0)
            cstate = snap.get("cursor_state", "arrow")
            click = snap.get("mouse_button_state", "none")
            parts.append(f"  Mouse cursor: position=({cx}, {cy}), shape/state={cstate}")
            if click != "none":
                parts.append(f"  Mouse click action: {click} active")
            if snap.get("cursor_hovering_active_window"):
                parts.append(f"  Mouse hover state: Cursor is hovering inside the focused window")
            else:
                parts.append(f"  Mouse hover state: Cursor is outside the focused window bounds")

            # ── Hierarchical Scene Graph (New) ──
            layout = snap.get("scene_layout", {})
            if layout and isinstance(layout, dict):
                parts.append("  [Hierarchical Scene Graph]:")
                res = layout.get("resolution", "unknown")
                parts.append(f"    - Global Screen Node: resolution={res}")
                
                win = layout.get("active_window", {})
                if win:
                    parts.append(f"      - Active Window: title=\"{win.get('title', '')}\", class=\"{win.get('class', '')}\", process=\"{win.get('process', '')}\", focus=\"{win.get('app_focus', '')}\"")
                
                ui = layout.get("ui_hierarchy", {})
                if ui and ui.get("panels"):
                    parts.append("      - UI Panel Layout Hierarchy:")
                    for panel in ui.get("panels", []):
                        p_name = panel.get("name", "panel")
                        p_role = panel.get("role", "")
                        p_bounds = panel.get("bounds", [])
                        parts.append(f"        * Panel [{p_name}] ({p_role}) bounds={p_bounds}")
                        if p_name == "main_content":
                            parts.append(f"          Detail: density={panel.get('density')}, brightness={panel.get('brightness')}%")
                            
                hl_node = layout.get("highlighted_text_node", {})
                if hl_node:
                    parts.append(f"      - User Selection Focus:")
                    parts.append(f"        * Highlighted Region: text=\"{hl_node.get('text', '')}\", context=\"{hl_node.get('context', '')}\"")

            # ── Screen Layout Zones (Legacy fallback/diagnostics) ──
            if layout and layout.get("zones"):
                parts.append("  [Screen Layout Zones]:")
                for zone in layout.get("zones", []):
                    z_name = zone.get("name", "zone")
                    z_role = zone.get("role", "content")
                    z_ocr = zone.get("ocr_text", "").strip()
                    if z_ocr:
                        z_excerpt = z_ocr[:300] + "..." if len(z_ocr) > 300 else z_ocr
                        parts.append(f"    - {z_name} ({z_role}): \"{z_excerpt.replace(chr(10), ' ')}\"")
                    else:
                        parts.append(f"    - {z_name} ({z_role}): [empty]")

            vlm = snap.get("vlm_caption", "")
            if vlm:
                parts.append(f"  VLM screen description: {vlm[:300]}")

            ocr = snap.get("ocr_text", "")
            highlighted = snap.get("highlighted_region_text", "")
            if highlighted:
                # Highest priority: the cursor-selected/highlighted text
                parts.append(f"  HIGHLIGHTED/SELECTED TEXT (cursor selection): \"{highlighted.strip()}\"")
                parts.append("  (To answer 'what word is highlighted?' — quote the text above directly.)")
            if ocr:
                if not has_screen_context:
                    # Show up to 6000 chars of OCR — enough for a full screen of code/text
                    ocr_excerpt = ocr[:6000].strip()
                    parts.append(f"  OCR text (what is visible on screen):\n    {ocr_excerpt.replace(chr(10), chr(10) + '    ')}")
                else:
                    parts.append("  OCR text: ✓ available (described in Screen Perception section)")
            else:
                parts.append("  OCR text: not available (OCR engine returned no text)")

            conf = snap.get("vision_confidence", 0.0)
            fps  = snap.get("fps", 0.0)
            parts.append(f"  Vision Status: Sharing screen ({int(conf * 100)}% confidence @ {fps} FPS)")

        # Audio content — clean natural observations instead of raw telemetry
        audio_type = snap.get("audio_type", "silence")
        audio_desc = snap.get("audio_description", "")
        audio_transcript = snap.get("screen_audio_transcript", "")
        audio_lang = snap.get("audio_language", "unknown")
        audio_speaker = snap.get("audio_speaker_id", "speaker_0")
        audio_music = snap.get("audio_music_title", "")
        audio_playback = snap.get("audio_playback_state", "stopped")
        audio_effects = snap.get("audio_sound_effects", [])

        if audio_active and audio_type != "silence":
            parts.append("  [Audio Observations]:")
            parts.append(f"    - Playback state: {audio_playback}")
            if audio_transcript:
                parts.append(f"    - Speech heard: \"{audio_transcript}\" ({audio_speaker} speaking in {audio_lang})")
            elif audio_music:
                parts.append(f"    - Music playing: \"{audio_music}\"")
            elif audio_desc:
                clean_desc = audio_desc.replace("System audio: ", "").replace("Ambient: ", "")
                parts.append(f"    - Sound: {clean_desc}")
            if audio_effects:
                parts.append(f"    - Audio effects: {', '.join(audio_effects)}")
        elif wants_audio:
            parts.append("  [Audio Observations]: Screen is currently silent")

        # Temporal History changes
        history = snap.get("temporal_history", [])
        if history:
            parts.append("  [Recent Timeline Changes (last minute)]:")
            for item in list(history)[-10:]:
                parts.append(f"    - [{item.get('time_str', '')}] {item.get('change', '')}")

        if len(parts) <= 1:
            return ""  # Only header, no content

        return "\n".join(parts)

    except Exception as e:
        logger.debug(f"[ContextInjector] _build_live_snapshot failed: {e}")
        return ""


def _fmt_ts(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def get_perception_diagnostic_block() -> str:
    """
    Return a formatted factual perception diagnostic block from the
    PerceptionManager reader.  This is the RUNTIME STATE — never LLM-generated.

    Used by run_vivy.py to build the perception_state dict that is passed
    to conversation.py.  Safe to call even if PerceptionManager is unavailable.
    """
    try:
        from perception.perception_manager import get_reader
        reader = get_reader()
        return reader.build_grounding_context()
    except Exception as e:
        logger.debug(f"[ContextInjector] get_perception_diagnostic_block() failed: {e}")
        return ""
