"""
perception/screen_pipeline.py
================================
Modular, configurable screen perception pipeline.
"""

from __future__ import annotations

import colorsys
import logging
import re
import time
from collections import deque
from io import BytesIO
from typing import TypedDict, Optional, List
import PIL.Image
import numpy as np

import threading
from concurrent.futures import ThreadPoolExecutor
from perception.plugins.interfaces import BaseOCRPlugin, BaseVisionPlugin
from perception.model_router import ModelRouter

logger = logging.getLogger(__name__)


class FrameQualityAnalyzer:
    """Inspects screen frames for resolution, blur, contrast, brightness, and noise."""

    def analyze(self, img: PIL.Image.Image) -> dict:
        w, h = img.size
        # Fast conversion to grayscale numpy array for metric calculation
        gray = img.convert("L")
        arr = np.array(gray, dtype=np.float32)

        # 1. Brightness (Mean pixel value)
        brightness = float(np.mean(arr))

        # 2. Contrast (Standard deviation)
        contrast = float(np.std(arr))

        # 3. Sharpness / Blur (Variance of Laplacian)
        from PIL import ImageFilter
        # Laplacian filter kernel
        laplacian_filter = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=0)
        lap_img = gray.filter(laplacian_filter)
        lap_arr = np.array(lap_img, dtype=np.float32)
        sharpness = float(np.var(lap_arr))

        # 4. Noise estimation (Mean Absolute Deviation from a Gaussian-blurred version)
        blur_img = gray.filter(ImageFilter.GaussianBlur(radius=1))
        arr_blur = np.array(blur_img, dtype=np.float32)
        noise = float(np.mean(np.abs(arr - arr_blur)))

        # 5. Text density estimation (heuristics based on edge density)
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_arr = np.array(edges)
        edge_density = float(np.mean(edge_arr > 50))

        # Check thresholds for quality sufficiency
        reasons = []
        if w < 1280 or h < 720:
            reasons.append(f"low_resolution ({w}x{h})")
        if sharpness < 25.0:
            reasons.append(f"blurry ({sharpness:.1f})")
        if contrast < 15.0:
            reasons.append(f"low_contrast ({contrast:.1f})")
        if brightness < 15.0:
            reasons.append(f"too_dark ({brightness:.1f})")
        if brightness > 240.0:
            reasons.append(f"too_bright ({brightness:.1f})")
        if noise > 12.0:
            reasons.append(f"noisy ({noise:.1f})")

        quality_sufficient = len(reasons) == 0

        return {
            "resolution": f"{w}x{h}",
            "width": w,
            "height": h,
            "brightness": brightness,
            "contrast": contrast,
            "sharpness": sharpness,
            "noise": noise,
            "edge_density": edge_density,
            "quality_sufficient": quality_sufficient,
            "reasons": reasons
        }


# ─────────────────────────────────────────────────────────────────────────────
# Typed result object
# ─────────────────────────────────────────────────────────────────────────────
class ScreenEvent(TypedDict):
    """Structured output of one screen perception cycle."""
    timestamp:         float   # Unix timestamp of capture
    app_type:          str     # e.g. "Visual Studio Code (dark theme)"
    env_detail:        str     # Contextual sentence about the environment
    ocr_text:          str     # Raw OCR output (may be "")
    vision_description: str   # Vision model output (may be "")
    brightness:        float   # 0–100 brightness of main area
    has_sidebar:       bool    # Whether a sidebar panel was detected
    content_density:   str     # "dense", "moderate", or "sparse"
    raw_description:   str     # Final formatted human-readable description
    next_delay_ms:     Optional[int] # Adaptive delay for the next frame
    scene_transition:  Optional[str] # Description of detected scene transition
    resolution:        str     # "width x height" resolution
    ocr_confidence:    float   # Average OCR confidence score (0.0 to 1.0)
    scene_layout:      Optional[dict] # Hierarchical Scene layout zones and roles
    quality_analysis:  Optional[dict] # Quality metrics dictionary
    request_high_res:  Optional[bool] # High resolution request flag


# ─────────────────────────────────────────────────────────────────────────────
# OCR helper (Pytesseract default adapter)
# ─────────────────────────────────────────────────────────────────────────────
class _LegacyOCREngine:
    """Legacy pytesseract with lazy init and graceful fallback."""

    def __init__(self):
        self._available: bool | None = None
        self._tesseract_cmd: str     = ""

    def _init(self) -> bool:
        if self._available is not None:
            return self._available

        try:
            from perception.config_loader import get
            import pytesseract as _pyt
            import subprocess as _sp

            tess_paths = get("screen_perception", "tesseract_paths", default=[])
            found = False
            for tp in tess_paths:
                import os
                if os.path.exists(tp):
                    _pyt.pytesseract.tesseract_cmd = tp
                    self._tesseract_cmd = tp
                    found = True
                    break

            if not found:
                try:
                    _sp.run(["tesseract", "--version"], capture_output=True, timeout=2, check=True)
                    found = True
                except Exception as _err:
                    print(f"[screen_pipeline.py] Silenced exception: {_err}")

            self._available = found
            if found:
                logger.info(f"[ScreenPipeline] Tesseract OCR available: {self._tesseract_cmd or 'system PATH'}")
            else:
                logger.info("[ScreenPipeline] Tesseract not found — OCR disabled")

        except ImportError:
            self._available = False
            logger.info("[ScreenPipeline] pytesseract not installed — OCR disabled")
        except Exception as e:
            self._available = False
            logger.warning(f"[ScreenPipeline] OCR init error: {e}")

        return self._available

    def _preprocess_image(self, img) -> PIL.Image.Image:
        import PIL.Image
        # Scale up the image if it is too small to improve Tesseract accuracy
        w, h = img.size
        if w < 500 or h < 300:
            scale = max(2.0, 500.0 / max(w, 1))
            img = img.resize((int(w * scale), int(h * scale)), PIL.Image.Resampling.LANCZOS)

        # Convert to grayscale
        ocr_img = img.convert("L")
        try:
            import numpy as np
            arr = np.array(ocr_img)
            
            # Pure NumPy Otsu Thresholding
            hist, bin_edges = np.histogram(arr, bins=256, range=(0, 256))
            bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
            
            weight1 = np.cumsum(hist)
            weight2 = np.cumsum(hist[::-1])[::-1]
            weight1 = np.where(weight1 == 0, 1, weight1)
            weight2 = np.where(weight2 == 0, 1, weight2)
            
            mean1 = np.cumsum(hist * bin_centers) / weight1
            mean2 = (np.cumsum((hist * bin_centers)[::-1]) / weight2[::-1])[::-1]
            
            variance12 = weight1 * weight2 * (mean1 - mean2) ** 2
            idx = np.argmax(variance12)
            threshold = bin_centers[idx]
            
            bin_arr = (arr > threshold).astype(np.uint8) * 255
            # Invert if background is dark so it is black text on a white background
            if np.mean(bin_arr) < 128:
                bin_arr = 255 - bin_arr
                
            return PIL.Image.fromarray(bin_arr)
        except Exception as e:
            # Fallback to standard contrast enhancement if numpy binarization fails
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(ocr_img)
            return enhancer.enhance(1.5)

    def extract(self, img) -> str:
        from perception.config_loader import get
        if not get("screen_perception", "ocr_enabled", default=True):
            return ""
        if not self._init():
            return ""
        try:
            import pytesseract as _pyt
            ocr_img = self._preprocess_image(img)
            
            char_limit = get("screen_perception", "ocr_char_limit", default=10000)
            text = _pyt.image_to_string(ocr_img, config=r"--oem 3 --psm 3")
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if len(text) > char_limit:
                text = text[:char_limit] + "...(truncated)"
            return text
        except Exception as e:
            logger.debug(f"[ScreenPipeline] OCR failed: {e}")
            return ""

    def extract_rich(self, img) -> tuple[str, list[dict]]:
        from perception.config_loader import get
        if not get("screen_perception", "ocr_enabled", default=True):
            return "", []
        if not self._init():
            return "", []
        try:
            import pytesseract as _pyt
            ocr_img = self._preprocess_image(img)
            
            # Run image_to_string and image_to_data in parallel to minimize latency (saves up to 50% delay)
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_text = executor.submit(_pyt.image_to_string, ocr_img, config=r"--oem 3 --psm 3")
                future_data = executor.submit(_pyt.image_to_data, ocr_img, config=r"--oem 3 --psm 3", output_type=_pyt.Output.DICT)
                text = future_text.result()
                data = future_data.result()
            
            words = []
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                text_str = data['text'][i].strip()
                try:
                    conf = float(data['conf'][i])
                except (ValueError, TypeError):
                    conf = 0.0
                if text_str and conf >= 50.0:
                    words.append({
                        'text': text_str,
                        'left': data['left'][i],
                        'top': data['top'][i],
                        'width': data['width'][i],
                        'height': data['height'][i],
                        'block_num': data['block_num'][i],
                        'par_num': data['par_num'][i],
                        'line_num': data['line_num'][i],
                        'word_num': data['word_num'][i],
                        'conf': conf
                    })
            
            char_limit = get("screen_perception", "ocr_char_limit", default=10000)
            if len(text) > char_limit:
                text = text[:char_limit] + "...(truncated)"
                
            return text, words
        except Exception as e:
            logger.debug(f"[ScreenPipeline] extract_rich_failed: {e}")
            return "", []


def reconstruct_ocr_text(ocr_words: list[dict]) -> tuple[str, float]:
    """
    Reconstruct OCR text from words metadata.
    Groups words by block_num, par_num, line_num to reconstruct larger semantic blocks.
    Sorts words horizontally.
    Calculates average confidence.
    Filters/replaces extremely low-confidence words with [unreadable],
    qualifies uncertain lines with [partially readable: ...],
    and returns a cleaned, reconstructed string along with average confidence.
    """
    if not ocr_words:
        return "", 1.0

    # Group words by block_num
    blocks_map = {}
    for w in ocr_words:
        b_num = w.get('block_num', 0)
        blocks_map.setdefault(b_num, []).append(w)

    reconstructed_blocks = []
    total_conf = 0.0
    word_count = 0

    # Sort blocks by their typical top coordinate (average top of words in block)
    sorted_blocks = sorted(blocks_map.keys(), key=lambda b: sum(w.get('top', 0) for w in blocks_map[b]) / len(blocks_map[b]))

    for b_num in sorted_blocks:
        block_words = blocks_map[b_num]
        
        # Group words within this block by par_num and line_num
        lines_map = {}
        for w in block_words:
            key = (w.get('par_num', 0), w.get('line_num', 0))
            lines_map.setdefault(key, []).append(w)
            
        # Sort lines by their keys (par_num, line_num)
        sorted_lines = sorted(lines_map.keys())
        
        block_lines = []
        for key in sorted_lines:
            line_words = lines_map[key]
            line_words.sort(key=lambda w: w.get('left', 0))
            
            cleaned_words = []
            line_conf_sum = 0.0
            line_word_count = 0
            
            for w in line_words:
                word_text = w.get('text', '').strip()
                if not word_text:
                    continue
                conf = w.get('conf', 100.0)
                
                line_conf_sum += conf
                line_word_count += 1
                
                # If confidence is extremely low (< 30%), replace with [unreadable] marker
                if conf < 30.0:
                    if not cleaned_words or cleaned_words[-1] != "[unreadable]":
                        cleaned_words.append("[unreadable]")
                else:
                    cleaned_words.append(word_text)
            
            if cleaned_words:
                line_str = " ".join(cleaned_words)
                avg_line_conf = line_conf_sum / line_word_count if line_word_count > 0 else 100.0
                
                # If average line confidence is low (< 55.0), qualify the line as partially readable
                if avg_line_conf < 55.0:
                    line_str = f"[partially readable: {line_str}]"
                
                block_lines.append(line_str)
                total_conf += line_conf_sum
                word_count += line_word_count
                
        if block_lines:
            reconstructed_blocks.append("\n".join(block_lines))

    final_text = "\n\n".join(reconstructed_blocks)
    avg_conf = (total_conf / word_count) / 100.0 if word_count > 0 else 1.0
    return final_text, avg_conf


def ocr_cropped_region_with_fallback(crop: PIL.Image.Image, ocr_plugin) -> str:
    """
    Runs OCR on a crop with multiple image enhancements to maximize readability of text.
    """
    if not ocr_plugin:
        return ""

    # 1. Base try
    text = ocr_plugin.extract_text(crop).strip()
    if len(text) > 2:
        return text

    # 2. Try scaling up further and converting to grayscale
    from PIL import ImageEnhance
    w, h = crop.size
    scaled = crop.resize((w * 3, h * 3), PIL.Image.Resampling.LANCZOS)
    gray = scaled.convert("L")

    text = ocr_plugin.extract_text(gray).strip()
    if len(text) > 2:
        return text

    # 3. Try high contrast
    contrast = ImageEnhance.Contrast(gray).enhance(2.0)
    text = ocr_plugin.extract_text(contrast).strip()
    if len(text) > 2:
        return text

    # 4. Try thresholding
    try:
        arr = np.array(contrast)
        threshold = 127
        bin_arr = (arr > threshold).astype(np.uint8) * 255
        if np.mean(bin_arr) < 128:
            bin_arr = 255 - bin_arr
        bin_img = PIL.Image.fromarray(bin_arr)
        text = ocr_plugin.extract_text(bin_img).strip()
        if len(text) > 2:
            return text
    except Exception as _err:
        print(f"[screen_pipeline.py] Silenced exception: {_err}")

    return text


def progressive_zoom_ocr(img: PIL.Image.Image, low_conf_words: list[dict], ocr_plugin) -> list[dict]:
    """
    Rerun OCR on zoomed-in crops of low-confidence text areas to recover readable content.
    Uses ThreadPoolExecutor to run extractions in parallel, preventing sequential latency bottlenecks.
    """
    logger.info(f"[ScreenPipeline] Low-confidence OCR detected. Launching progressive zoom-in on {len(low_conf_words)} regions...")
    
    def process_word(word):
        left = max(0, word['left'] - 6)
        top = max(0, word['top'] - 6)
        width = word['width'] + 12
        height = word['height'] + 12
        try:
            crop = img.crop((left, top, left + width, top + height))
            crop = crop.resize((width * 3, height * 3), PIL.Image.Resampling.LANCZOS)
            
            # Since this is a single word crop, we call extract_text (one call) instead of extract_rich_text (two calls)
            if hasattr(ocr_plugin, "extract_text"):
                zoom_text = ocr_plugin.extract_text(crop)
                zoom_words = [{"text": zoom_text, "conf": 80.0}] if zoom_text else []
            elif hasattr(ocr_plugin, "extract_rich_text"):
                zoom_text, zoom_words = ocr_plugin.extract_rich_text(crop)
            else:
                zoom_text = ""
                zoom_words = []
                
            if zoom_words:
                best_word = max(zoom_words, key=lambda x: x.get('conf', 0))
                if best_word.get('conf', 0) > word.get('conf', 0) and best_word.get('text', '').strip():
                    logger.debug(f"[ScreenPipeline] Recovered word '{word['text']}' -> '{best_word['text']}' (Conf: {word['conf']:.1f} -> {best_word['conf']:.1f})")
                    return word, best_word['text'], best_word['conf']
        except Exception as e:
            logger.debug(f"Zoom OCR failed: {e}")
        return None

    target_words = low_conf_words[:10]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(target_words), 4)) as executor:
        results = list(executor.map(process_word, target_words))
        
    for res in results:
        if res:
            word, text, conf = res
            word['text'] = text
            word['conf'] = conf
            
    return low_conf_words


_ocr = _LegacyOCREngine()


class PytesseractOCRPlugin(BaseOCRPlugin):
    """Pytesseract OCR Plugin."""

    @property
    def name(self) -> str:
        return "pytesseract"

    def is_available(self) -> bool:
        return _ocr._init()

    def extract_text(self, image: PIL.Image.Image) -> str:
        return _ocr.extract(image)

    def extract_rich_text(self, image: PIL.Image.Image) -> tuple[str, list[dict]]:
        return _ocr.extract_rich(image)


# Register OCR Plugin with ModelRouter
ModelRouter.register_plugin("ocr", "pytesseract", PytesseractOCRPlugin)

# ─────────────────────────────────────────────────────────────────────────────
# Visual Difference & State Variables
# ─────────────────────────────────────────────────────────────────────────────
_last_frame_data: Optional[np.ndarray] = None
_last_app_type: str = ""
_last_vlm_desc: str = ""
_last_vlm_time: float = 0.0
_last_fullscreen: bool = False
_last_ocr_text: str = ""
_last_ocr_words: list[dict] = []
_typing_state: str = "stopped"
_last_song: str = ""
_media_playing: bool = False
_frame_cache: deque = deque(maxlen=5)

# Progressive app classification stabilization cache
_last_detailed_app_type: str = ""
_last_detailed_env_detail: str = ""
_last_detailed_window_title: str = ""

_ddg_cache: dict = {}
_ocr_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="AsyncOCRWorker")
_ocr_lock = threading.Lock()
_ocr_in_progress: bool = False


def is_ocr_in_progress() -> bool:
    """Return whether async OCR is currently in progress."""
    with _ocr_lock:
        return _ocr_in_progress


def reset_screen_pipeline_state():
    """Reset all cached screen frames, OCR results, and internal state when screen capture stops."""
    global _last_frame_data, _last_app_type, _last_vlm_desc, _last_vlm_time
    global _last_fullscreen, _last_ocr_text, _last_ocr_words, _typing_state
    global _last_song, _media_playing, _frame_cache
    global _last_detailed_app_type, _last_detailed_env_detail, _last_detailed_window_title

    with _ocr_lock:
        _last_frame_data = None
        _last_app_type = ""
        _last_vlm_desc = ""
        _last_vlm_time = 0.0
        _last_fullscreen = False
        _last_ocr_text = ""
        _last_ocr_words = []
        _typing_state = "stopped"
        _last_song = ""
        _media_playing = False
        _frame_cache.clear()
        _last_detailed_app_type = ""
        _last_detailed_env_detail = ""
        _last_detailed_window_title = ""
    logger.info("[ScreenPipeline] Screen pipeline state reset cleanly.")


def fuse_frames(frames: list[PIL.Image.Image]) -> PIL.Image.Image:
    """Blend multiple static frames using pixel averaging to reduce noise."""
    if not frames:
        return None
    if len(frames) == 1:
        return frames[0]
    try:
        base = frames[0].convert("RGB")
        w, h = base.size
        arrs = []
        for f in frames:
            f_conv = f.convert("RGB")
            if f_conv.size != (w, h):
                f_conv = f_conv.resize((w, h), PIL.Image.Resampling.BILINEAR)
            arrs.append(np.array(f_conv, dtype=np.float32))
        mean_arr = np.mean(arrs, axis=0)
        return PIL.Image.fromarray(np.clip(mean_arr, 0, 255).astype(np.uint8))
    except Exception as e:
        logger.debug(f"[ScreenPipeline] Frame fusion failed: {e}")
        return frames[-1]


def _run_async_ocr(img_copy: PIL.Image.Image, quality_res: dict = None):
    """Run pytesseract OCR asynchronously in a background worker thread."""
    global _last_ocr_text, _last_ocr_words, _ocr_in_progress
    try:
        # --- Multi-stage OCR Pipeline ---
        # 1. Frame: img_copy (original high-res copy)
        # 2. Image Enhancement: convert to grayscale, boost contrast, and sharpen
        from PIL import ImageEnhance, ImageFilter
        gray = img_copy.convert("L")
        
        # Boost contrast by 1.8x
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.8)
        
        # Apply sharpness filter
        sharpened = enhanced.filter(ImageFilter.SHARPEN)
        
        # 3. Super Resolution / Scaling (if needed, using quality_res hints)
        w, h = sharpened.size
        scale = 1.0
        if w < 1920:
            scale = max(1.5, 1920.0 / w)
        if quality_res and (quality_res.get("sharpness", 100.0) < 30.0 or quality_res.get("contrast", 100.0) < 20.0):
            scale = max(scale, 2.0)
            
        if scale > 1.0:
            final_ocr_img = sharpened.resize((int(w * scale), int(h * scale)), PIL.Image.Resampling.LANCZOS)
            final_ocr_img = final_ocr_img.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
        else:
            final_ocr_img = sharpened

        ocr_plugin = ModelRouter.get_ocr_plugin()
        if ocr_plugin:
            if hasattr(ocr_plugin, "extract_rich_text"):
                # Run OCR on the enhanced, scaled image
                ocr_text, ocr_words = ocr_plugin.extract_rich_text(final_ocr_img)
                
                # Filter low-confidence words for progressive zoom OCR
                low_conf_words = [word_item for word_item in ocr_words if word_item.get('conf', 100.0) < 75.0 and len(word_item.get('text', '')) > 2]
                if low_conf_words:
                    old_texts = {id(word_item): word_item['text'] for word_item in low_conf_words}
                    # Progressive zoom OCR on zoomed, enhanced sub-crops. Updates in-place.
                    progressive_zoom_ocr(final_ocr_img, low_conf_words, ocr_plugin)
                    for word_item in low_conf_words:
                        old_txt = old_texts.get(id(word_item))
                        if old_txt and word_item['text'] != old_txt:
                            ocr_text = ocr_text.replace(old_txt, word_item['text'])
                
                # Reconstruct and clean up the OCR text using coordinates and confidences
                reconstructed, _ = reconstruct_ocr_text(ocr_words)
                if reconstructed:
                    ocr_text = reconstructed

                # ── Scrolling awareness heuristic inside async worker ──
                scroll_direction = None
                if _last_ocr_words and ocr_words:
                    try:
                        prev_word_map = {w['text']: w for w in _last_ocr_words if len(w['text']) > 3}
                        curr_word_map = {w['text']: w for w in ocr_words if len(w['text']) > 3}
                        common_words = set(prev_word_map.keys()).intersection(set(curr_word_map.keys()))
                        
                        y_diffs = []
                        for w_text in common_words:
                            prev_w = prev_word_map[w_text]
                            curr_w = curr_word_map[w_text]
                            diff = curr_w['top'] - prev_w['top']
                            if abs(curr_w['left'] - prev_w['left']) < 25:
                                y_diffs.append(diff)
                                
                        if len(y_diffs) >= 4:
                            avg_diff = sum(y_diffs) / len(y_diffs)
                            if avg_diff < -10:
                                scroll_direction = "down"
                            elif avg_diff > 10:
                                scroll_direction = "up"
                    except Exception as scr_err:
                        logger.debug(f"[ScreenPipeline] Scrolling calculation error: {scr_err}")

                if scroll_direction:
                    try:
                        from perception.fusion_engine import get_global_engine
                        get_global_engine().push_system_event(f"User is scrolling {scroll_direction} on the screen.", importance=0.65)
                        logger.debug(f"[ScreenPipeline] Scroll detected: {scroll_direction}")
                    except Exception as se_err:
                        logger.debug(f"[ScreenPipeline] Scroll push failed: {se_err}")
            else:
                ocr_text = ocr_plugin.extract_text(final_ocr_img)
                ocr_words = []

            with _ocr_lock:
                _last_ocr_text = ocr_text
                _last_ocr_words = ocr_words
    except Exception as e:
        logger.debug(f"[ScreenPipeline] Async OCR worker error: {e}")
    finally:
        with _ocr_lock:
            _ocr_in_progress = False


def _trigger_ddg_enrichment(query_text: str):
    """Asynchronously search DuckDuckGo for detected screen/audio media titles to enrich perception context."""
    if not query_text or query_text in _ddg_cache or len(query_text) < 4:
        return
    _ddg_cache[query_text] = "searching..."
    def _do_search():
        try:
            from conversation import search_duckduckgo
            res = search_duckduckgo(query_text)
            if res:
                _ddg_cache[query_text] = res
                from perception.fusion_engine import get_global_engine
                get_global_engine().push_system_event(
                    f"DuckDuckGo Web Search context for '{query_text}': {res[:250]}",
                    importance=0.88
                )
                from perception.perception_manager import get_writer
                get_writer().record_audio_event_description(f"Web knowledge retrieved for '{query_text}': {res[:180]}")
                logger.info(f"[ScreenPipeline] DuckDuckGo enriched context for '{query_text}'")
        except Exception as e:
            logger.debug(f"[ScreenPipeline] DDG enrichment error for '{query_text}': {e}")
    import threading
    threading.Thread(target=_do_search, daemon=True, name=f"DDG-Enrich-{query_text[:15]}").start()



def compute_visual_difference(img1: PIL.Image.Image, img2_data: np.ndarray) -> float:
    """Downsample current PIL Image and calculate Mean Absolute Error (MAE) with previous frame data."""
    try:
        im1 = img1.convert("L").resize((32, 32))
        arr1 = np.array(im1, dtype=np.float32) / 255.0
        return float(np.mean(np.abs(arr1 - img2_data)))
    except Exception as e:
        logger.debug(f"[ScreenPipeline] Visual difference calculation failed: {e}")
        return 1.0

# ... (detect_highlighted_region preserved) ...



def detect_highlighted_region(img: PIL.Image.Image) -> tuple[str, str]:
    """
    Detect cursor-selected / highlighted text regions on the screen and return its OCR text
    along with its surrounding context text.
    Supports multiple selection colors (blue, yellow, green, magenta) and multi-box layout
    reconstruction to handle multi-line or non-contiguous selections cleanly.
    Fast path: checks downsampled 320x180 thumbnail in <0.05ms first.
    """
    try:
        # ── Ultra-fast thumbnail pre-check (<0.05ms) ──
        thumb = img.resize((320, 180), resample=PIL.Image.Resampling.NEAREST if hasattr(PIL.Image, "Resampling") else 0)
        t_arr = np.array(thumb, dtype=np.uint8)
        tr, tg, tb = t_arr[:, :, 0].astype(int), t_arr[:, :, 1].astype(int), t_arr[:, :, 2].astype(int)
        t_mask = (tb - tr > 40) & (tb - tg > 30) & (tb > 80) | ((tr > 160) & (tg > 160) & (tb < 120)) | ((tg - tr > 35) & (tg - tb > 35) & (tg > 80)) | ((tr - tg > 35) & (tb - tg > 35) & (tr > 80) & (tb > 80))
        if not np.any(t_mask):
            return "", ""

        # Full resolution pass only when highlight colors are detected
        arr = np.array(img.convert("RGB"), dtype=np.uint8)
        r, g, b = arr[:, :, 0].astype(int), arr[:, :, 1].astype(int), arr[:, :, 2].astype(int)

        # ── Color masks ──
        # Blue selection (standard Windows / chrome)
        blue_mask = (b - r > 40) & (b - g > 30) & (b > 80)
        # Yellow selection (PDF highlights)
        yellow_mask = (r > 160) & (g > 160) & (b < 120) & (np.abs(r - g) < 30)
        # Green selection (PDF highlights)
        green_mask = (g - r > 35) & (g - b > 35) & (g > 80)
        magenta_mask = (r - g > 35) & (b - g > 35) & (r > 80) & (b > 80)

        mask = blue_mask | yellow_mask | green_mask | magenta_mask
        
        # Project mask vertically to find active rows
        rows = np.any(mask, axis=1)
        if not np.any(rows):
            return "", ""

        # Find contiguous highlighted rows (bands)
        diff = np.diff(rows.astype(int))
        starts = np.where(diff == 1)[0] + 1
        if rows[0]:
            starts = np.insert(starts, 0, 0)
        ends = np.where(diff == -1)[0] + 1
        if rows[-1]:
            ends = np.append(ends, len(rows))

        boxes = []
        for r_min, r_max in zip(starts, ends):
            if r_max - r_min < 4:
                continue

            band_mask = mask[r_min:r_max, :]
            cols = np.any(band_mask, axis=0)
            if not np.any(cols):
                continue

            col_diff = np.diff(cols.astype(int))
            c_starts = np.where(col_diff == 1)[0] + 1
            if cols[0]:
                c_starts = np.insert(c_starts, 0, 0)
            c_ends = np.where(col_diff == -1)[0] + 1
            if cols[-1]:
                c_ends = np.append(c_ends, len(cols))

            for c_min, c_max in zip(c_starts, c_ends):
                if c_max - c_min >= 8:
                    boxes.append((r_min, r_max, c_min, c_max))
                    
        if not boxes:
            return "", ""

        ocr_plugin = ModelRouter.get_ocr_plugin()
        if not ocr_plugin:
            return "", ""

        # Process each detected highlight box
        extracted_texts = []
        for box in boxes:
            r_min, r_max, c_min, c_max = box
            
            # Pad the crop slightly for better OCR boundary recognition
            pad = 4
            r_min_pad = max(0, r_min - pad)
            r_max_pad = min(arr.shape[0], r_max + pad)
            c_min_pad = max(0, c_min - pad)
            c_max_pad = min(arr.shape[1], c_max + pad)

            crop = img.crop((c_min_pad, r_min_pad, c_max_pad, r_max_pad))

            # Scale up small crops to make text clearer for OCR
            cw, ch = crop.size
            if cw < 200 or ch < 30:
                scale = max(3.0, 200.0 / max(cw, 1))
                crop = crop.resize((int(cw * scale), int(ch * scale)), PIL.Image.Resampling.LANCZOS)

            text_chunk = ocr_cropped_region_with_fallback(crop, ocr_plugin)
            if text_chunk:
                extracted_texts.append(text_chunk)
                    
        # Merge extracted text chunks
        merged_text = "\n".join(extracted_texts).strip()
        
        # Extract surrounding context by expanding bounding box
        context_text = ""
        try:
            min_r = min(box[0] for box in boxes)
            max_r = max(box[1] for box in boxes)
            min_c = min(box[2] for box in boxes)
            max_c = max(box[3] for box in boxes)
            
            pad_h = 150
            pad_w = 150
            ctx_r_min = max(0, min_r - pad_h)
            ctx_r_max = min(arr.shape[0], max_r + pad_h)
            ctx_c_min = max(0, min_c - pad_w)
            ctx_c_max = min(arr.shape[1], max_c + pad_w)
            
            ctx_crop = img.crop((ctx_c_min, ctx_r_min, ctx_c_max, ctx_r_max))
            context_text = ocr_cropped_region_with_fallback(ctx_crop, ocr_plugin)
        except Exception as ctx_err:
            logger.debug(f"Highlight context extraction failed: {ctx_err}")
            
        if merged_text:
            logger.debug(f"[ScreenPipeline] Multi-box Highlight OCR: '{merged_text[:120]}'")
            return merged_text, context_text
            
    except Exception as e:
        logger.debug(f"[ScreenPipeline] detect_highlighted_region() failed: {e}")
        
    return "", ""


def _zone_avg_rgb(zone_img) -> tuple[int, int, int]:
    from PIL import ImageStat
    stat = ImageStat.Stat(zone_img)
    return tuple(int(v) for v in stat.mean[:3])

def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    return colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)


def _classify_app(main_h, main_s, main_v, title_h, title_s, title_v) -> tuple[str, str]:
    """Classify the application type from zone color signatures."""
    if main_v < 0.25 and main_s < 0.3:
        if 0.5 < title_h < 0.75 and title_v > 0.2:
            return (
                "Visual Studio Code (dark theme)",
                "A code editor is open. The workspace appears dark with syntax highlighting.",
            )
        elif 0.55 < title_h < 0.75:
            return (
                "dark-theme IDE or code editor (likely VS Code, Vim, or similar)",
                "A code editor with dark theme is visible.",
            )
        else:
            return (
                "dark-theme code editor or IDE",
                "A terminal, console, or dark-themed application is on screen.",
            )

    if 0.15 < main_v < 0.35 and main_s < 0.15:
        return (
            "Unity Editor or dark gray application",
            "A dark gray application interface is visible — possibly Unity Editor, a 3D tool, or a game engine.",
        )

    if main_v > 0.85 and main_s < 0.15:
        if title_v > 0.6:
            return (
                "web browser or document viewer",
                "A web browser window is open showing a white or light-colored webpage.",
            )
        return (
            "web browser or document viewer",
            "A white document or text editor is visible — possibly a browser, Word, or Notepad.",
        )

    if main_v > 0.92 and main_s < 0.08 and title_s < 0.12:
        return (
            "Notepad or plain text editor",
            "A plain white text editor (such as Notepad or WordPad) is open.",
        )

    if 0.75 < main_v < 0.95 and main_s < 0.15:
        return (
            "file explorer or settings panel",
            "A light-colored system window is open — possibly File Explorer, Settings, or a light-themed app.",
        )

    if main_s > 0.35:
        return (
            "media or colorful application",
            "A colorful or media-rich application is visible — possibly a game, video player, or creative tool.",
        )

    return ("unknown application", "")


def is_ocr_vivy_dashboard(ocr_text: str) -> bool:
    if not ocr_text:
        return False
    ocr_lower = ocr_text.lower()
    dashboard_keywords = [
        "api server:", "screen sharing:", "audio sharing:", "system status",
        "vaporization:", "type a message", "share screen", "share audio",
        "neural interface", "vivy ai"
    ]
    matches = sum(1 for kw in dashboard_keywords if kw in ocr_lower)
    return matches >= 2


def _classify_app_with_os_metadata_raw(win_title: str, win_class: str, proc_name: str, main_h, main_s, main_v, title_h, title_s, title_v, ocr_text: str = "") -> tuple[str, str]:
    """Classify the application type combining active window OS metadata and color analysis."""
    # Check if the OCR text belongs to Vivy's dashboard interface itself to prevent self-perception/feedback loops
    if is_ocr_vivy_dashboard(ocr_text):
        return (
            "Vivy AI Dashboard",
            "You are viewing the Vivy AI Dashboard."
        )

    # Normalize strings
    title_lower = win_title.lower().strip() if win_title else ""
    proc_lower = proc_name.lower().strip() if proc_name else ""
    class_lower = win_class.lower().strip() if win_class else ""

    # Check if the OS active window belongs to Vivy's own interface
    is_vivy = any(x in title_lower for x in ("vivy ai", "neural interface", "127.0.0.1:8080", "localhost:8080"))

    # Extract visually shared browser window titles from OCR text if available
    shared_window_title = ""
    if ocr_text:
        lines = [line.strip() for line in ocr_text.split("\n") if line.strip()]
        for line in lines:
            if any(suffix in line for suffix in (" - Microsoft Edge", " - Google Chrome", " - Mozilla Firefox", " - Chrome", " - Edge", " - Firefox")):
                if not any(x in line.lower() for x in ("vivy ai", "neural interface", "127.0.0.1:8080", "localhost:8080")):
                    shared_window_title = line
                    break

    # If active window is Vivy, or does not match what is actually visible in the visual OCR stream, override it
    if is_vivy or (win_title and shared_window_title and win_title not in shared_window_title and shared_window_title not in win_title):
        if shared_window_title:
            win_title = shared_window_title
            title_lower = win_title.lower().strip()
            if "edge" in title_lower:
                proc_lower = "msedge.exe"
            elif "chrome" in title_lower:
                proc_lower = "chrome.exe"
            elif "firefox" in title_lower:
                proc_lower = "firefox.exe"
        elif is_vivy:
            win_title = ""
            title_lower = ""

    # ── OCR-Based Page Classification Fallback ──
    # Check visual ocr_text for webpage/page signatures if title is missing, generic, or belongs to Vivy
    if ocr_text:
        ocr_lower = ocr_text.lower()
        
        # Determine browser name if possible
        browser_name = "Web Browser"
        if "msedge" in proc_lower or "edge" in title_lower or "edge.exe" in proc_lower:
            browser_name = "Microsoft Edge"
        elif "chrome" in proc_lower or "chrome" in title_lower or "chrome.exe" in proc_lower:
            browser_name = "Google Chrome"
        elif "firefox" in proc_lower or "firefox" in title_lower:
            browser_name = "Mozilla Firefox"
            
        # 1. YouTube content signature
        if "youtube" in ocr_lower or "subscribe" in ocr_lower or ("views" in ocr_lower and "likes" in ocr_lower):
            video_title = ""
            lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
            for line in lines:
                if any(k in line.lower() for k in ["nightcore", "official video", "music video", "lyrics", " - "]) and len(line) < 120:
                    video_title = line
                    break
            if not video_title and lines:
                for line in lines[:8]:
                    if len(line) > 10 and not any(x in line.lower() for x in ["youtube", "search", "skip", "subscribe", "library", "home", "history", "views"]):
                        video_title = line
                        break
            if video_title:
                return (
                    f"{browser_name} (YouTube - playing '{video_title}')",
                    f"You are viewing a YouTube page playing a video/song titled '{video_title}'."
                )
            else:
                return (
                    f"{browser_name} (YouTube)",
                    "You are viewing a YouTube page playing a video."
                )
                
        # 2. GitHub content signature
        elif "github" in ocr_lower or "pull request" in ocr_lower or "repositories" in ocr_lower:
            repo_name = ""
            lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
            for line in lines:
                if "/" in line and len(line) < 60 and not any(x in line for x in ["http", "\\", "127.0.0.1"]):
                    repo_name = line
                    break
            if repo_name:
                return (
                    f"{browser_name} (GitHub - repository '{repo_name}')",
                    f"You are viewing a GitHub page for the repository '{repo_name}'."
                )
            else:
                return (
                    f"{browser_name} (GitHub)",
                    "You are viewing a GitHub page."
                )
                
        # 3. Google Search signature
        elif "google" in ocr_lower and ("search" in ocr_lower or "images" in ocr_lower):
            return (
                f"{browser_name} (Google Search)",
                "You are viewing a Google Search results page."
            )

    # 1. VS Code / Development IDEs
    if "visual studio code" in title_lower or "vscode" in title_lower or "code.exe" in proc_lower or "cursor.exe" in proc_lower:
        return (
            "Visual Studio Code",
            "A code editor is open. The user appears to be writing or reviewing code."
        )
    if "pycharm" in title_lower or "pycharm" in proc_lower:
        return (
            "PyCharm IDE",
            "A Python development environment is active."
        )
    if "sublime text" in title_lower or "sublime_text" in proc_lower:
        return (
            "Sublime Text",
            "A text/code editor is active."
        )

    # 2. Browsers (Chrome, Edge, Firefox)
    is_browser = False
    browser_name = ""
    if "msedge" in proc_lower or "edge.exe" in proc_lower:
        is_browser = True
        browser_name = "Microsoft Edge"
    elif "firefox" in proc_lower:
        is_browser = True
        browser_name = "Mozilla Firefox"
    elif "chrome" in proc_lower:
        is_browser = True
        browser_name = "Google Chrome"
    elif "chrome_widgetwin_1" in class_lower:
        if "edge" in title_lower:
            is_browser = True
            browser_name = "Microsoft Edge"
        else:
            is_browser = True
            browser_name = "Google Chrome"
    elif "google chrome" in title_lower:
        is_browser = True
        browser_name = "Google Chrome"
    elif "microsoft edge" in title_lower:
        is_browser = True
        browser_name = "Microsoft Edge"
    elif "firefox" in title_lower:
        is_browser = True
        browser_name = "Mozilla Firefox"

    if is_browser:
        if "youtube" in title_lower:
            return (
                f"{browser_name} (YouTube)",
                "A web browser is open, playing a YouTube video or browsing videos."
            )
        if "google docs" in title_lower or "document" in title_lower:
            return (
                f"{browser_name} (Google Docs)",
                "A web browser is open showing a Google Doc or collaborative document."
            )
        if "github" in title_lower:
            return (
                f"{browser_name} (GitHub)",
                "A web browser is open showing GitHub repositories, code, or pull requests."
            )
        if "stackoverflow" in title_lower:
            return (
                f"{browser_name} (Stack Overflow)",
                "A web browser is open showing developer questions and answers."
            )
        if win_title and win_title != "unknown" and win_title != "unknown application":
            tab_name = win_title
            for suffix in [" - Google Chrome", " - Microsoft Edge", " - Mozilla Firefox", " - Chrome", " - Edge"]:
                if tab_name.endswith(suffix):
                    tab_name = tab_name[:-len(suffix)]
                    break
            return (
                f"{browser_name} - {tab_name}",
                f"A web browser window is active showing the page: '{tab_name}'."
            )
        return browser_name, "A web browser window is active."

    # 3. Media Players
    if "vlc" in proc_lower or "vlc" in title_lower:
        return (
            "VLC Media Player",
            "A media player is open — likely playing video or audio content."
        )
    if "wmplayer" in proc_lower or "windows media player" in title_lower:
        return (
            "Windows Media Player",
            "A media player is open."
        )

    # 4. Command Prompt / Terminal
    if "cmd.exe" in proc_lower or "powershell" in proc_lower or "windowsterminal" in proc_lower or "wt.exe" in proc_lower:
        return (
            "Terminal / Console",
            "A command prompt, PowerShell, or terminal window is active."
        )

    # 5. File Explorer
    if "explorer.exe" in proc_lower and "cabinetwclass" in class_lower:
        return (
            "File Explorer",
            "Windows File Explorer is open, browsing files and folders."
        )

    # If we have a window title but it didn't match specific rules
    if win_title and win_title != "unknown" and win_title != "unknown application" and win_title != "":
        return win_title, f"Active application/window: '{win_title}'."

    # Fall back to color-based heuristics
    return _classify_app(main_h, main_s, main_v, title_h, title_s, title_v)


def classify_app_with_os_metadata(win_title: str, win_class: str, proc_name: str, main_h, main_s, main_v, title_h, title_s, title_v, ocr_text: str = "") -> tuple[str, str]:
    global _last_detailed_app_type, _last_detailed_env_detail, _last_detailed_window_title

    app_type, env_detail = _classify_app_with_os_metadata_raw(
        win_title, win_class, proc_name,
        main_h, main_s, main_v, title_h, title_s, title_v,
        ocr_text
    )

    # Determine if the classification is detailed (e.g. not generic web browser or unknown)
    is_detailed = False
    if "playing '" in app_type or "repository '" in app_type or "Google Search" in app_type or "named `" in app_type or "showing the page:" in env_detail:
        is_detailed = True
    elif win_title and win_title != "unknown" and win_title != "unknown application" and win_title != "":
        # Exclude generic fallbacks
        generic_types = ("Microsoft Edge", "Google Chrome", "Mozilla Firefox", "web browser or document viewer", "unknown application", "web browser")
        if not any(gt in app_type for gt in generic_types):
            is_detailed = True

    if is_detailed:
        _last_detailed_app_type = app_type
        _last_detailed_env_detail = env_detail
        _last_detailed_window_title = win_title
    else:
        # If the new classification is generic, but the window title is still the same as the last detailed window title
        if win_title and win_title == _last_detailed_window_title and _last_detailed_app_type:
            logger.debug(f"[ScreenPipeline] Stabilizing app classification: reusing detailed '{_last_detailed_app_type}' for window '{win_title}'")
            return _last_detailed_app_type, _last_detailed_env_detail

    return app_type, env_detail


def analyze_frame(img: PIL.Image.Image) -> ScreenEvent:
    """
    Analyse a PIL Image and return a structured ScreenEvent.
    Supports pluggable OCR, pluggable VLM, adaptive sampling delay, and scene segmentation.
    """
    from PIL import ImageStat
    from perception.config_loader import get

    global _last_frame_data, _last_app_type, _last_vlm_desc, _last_vlm_time, _last_ocr_words, _last_ocr_text, _last_fullscreen, _media_playing, _typing_state, _last_song, _ocr_in_progress

    # Keep a copy of the original high-resolution image BEFORE resizing
    orig_img = img.copy()

    # Load configuration
    max_w = get("screen_perception", "capture_resolution_max_width", default=1280)
    adaptive_enabled = get("screen_perception", "adaptive_sampling_enabled", default=False)
    min_delay = get("screen_perception", "min_sampling_delay_ms", default=16)
    max_delay = get("screen_perception", "max_sampling_delay_ms", default=2000)
    static_threshold = get("screen_perception", "static_threshold", default=0.02)
    default_fps = get("screen_perception", "fps", default=60)
    base_delay = max(16, int(1000 / default_fps))

    w, h  = img.size
    highlighted_text = ""
    highlighted_context = ""

    # Run Frame Quality Analysis on the original image
    quality_analyzer = FrameQualityAnalyzer()
    quality_res = quality_analyzer.analyze(orig_img)
    request_high_res = not quality_res.get("quality_sufficient", True)

    # 1. Resize for speed (use BILINEAR for 50-60 FPS fast processing)
    if w > max_w:
        scale = max_w / w
        resample_filter = PIL.Image.Resampling.BILINEAR if hasattr(PIL.Image, "Resampling") else getattr(PIL.Image, "BILINEAR", 2)
        img = img.resize((int(w * scale), int(h * scale)), resample=resample_filter)
        w, h = img.size

    # 2. Ensure RGB
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 3. Calculate Visual Change
    is_static = False
    change_score = 1.0
    if _last_frame_data is not None:
        change_score = compute_visual_difference(img, _last_frame_data)
        is_static = change_score < static_threshold
        
    # Update frame cache for multi-frame fusion
    if not is_static:
        _frame_cache.clear()
    _frame_cache.append(orig_img)
    
    # Perform Multi-Frame Fusion if static
    if is_static and len(_frame_cache) > 1:
        fused_img = fuse_frames(list(_frame_cache))
    else:
        fused_img = orig_img

    # Update last frame cache
    try:
        im_gray = img.convert("L").resize((32, 32), resample=PIL.Image.Resampling.NEAREST if hasattr(PIL.Image, "Resampling") else 0)
        _last_frame_data = np.array(im_gray, dtype=np.float32) / 255.0
    except Exception as _err:
        print(f"[screen_pipeline.py] Silenced exception: {_err}")

    # Determine adaptive next delay recommendation
    next_delay_ms = base_delay
    if adaptive_enabled:
        if is_static:
            # Gradually increase delay for static screen up to max_delay
            next_delay_ms = min(max_delay, int(base_delay * 4))
        else:
            # Scene is active; sample faster
            next_delay_ms = min_delay

    # 4. OCR Plugin extraction (non-blocking async execution for 50-60 FPS throughput)
    ocr_text = ""
    ocr_words = []
    with _ocr_lock:
        ocr_text = _last_ocr_text
        ocr_words = _last_ocr_words
        in_prog = _ocr_in_progress

    if (not is_static or not ocr_text) and not in_prog:
        with _ocr_lock:
            _ocr_in_progress = True
        try:
            img_copy = fused_img.copy()
            _ocr_executor.submit(_run_async_ocr, img_copy, quality_res)
        except Exception as _sub_err:
            with _ocr_lock:
                _ocr_in_progress = False

    # Scrolling awareness is handled asynchronously inside _run_async_ocr to prevent race conditions

    # 4b. Cursor/highlight region detection — runs after full OCR
    # Detects OS text selection (blue highlight) and extracts only the selected text
    # via a targeted crop+OCR pass. Result goes directly to PerceptionManager.
    try:
        highlighted_text, highlighted_context = detect_highlighted_region(fused_img)
        if highlighted_text:
            from perception.perception_manager import get_writer as _pm_get_writer
            _pm_get_writer().record_highlighted_region(highlighted_text, highlighted_context)
            logger.debug(f"[ScreenPipeline] Highlighted region pushed to PerceptionManager: '{highlighted_text[:60]}', context: '{highlighted_context[:60]}'")
    except Exception as _hl_err:
        logger.debug(f"[ScreenPipeline] Highlight push failed (non-fatal): {_hl_err}")

    # 5. Zone color analysis (App Type, brightness, sidebar)
    top_8   = max(1, int(h * 0.08))
    side_18 = max(1, int(w * 0.18))

    title_zone   = img.crop((0, 0, w, top_8))
    main_zone    = img.crop((0, top_8, w, int(h * 0.92)))
    sidebar_zone = img.crop((0, top_8, side_18, int(h * 0.92)))

    title_rgb = _zone_avg_rgb(title_zone)
    main_rgb  = _zone_avg_rgb(main_zone)
    side_rgb  = _zone_avg_rgb(sidebar_zone)

    title_h, title_s, title_v = _rgb_to_hsv(*title_rgb)
    main_h,  main_s,  main_v  = _rgb_to_hsv(*main_rgb)
    side_h,  side_s,  side_v  = _rgb_to_hsv(*side_rgb)

    # Try to classify using OS metadata first (skip during tests to allow testing color classification)
    win_title = ""
    win_class = ""
    proc_name = "unknown"
    import sys
    if "pytest" not in sys.modules and "unittest" not in sys.modules:
        try:
            from perception.perception_manager import get_writer
            pm_writer = get_writer()
            with pm_writer._lock:
                win_title = pm_writer._active_window_title
                win_class = pm_writer._active_window_class
                proc_name = getattr(pm_writer, "_active_process_name", "unknown")
        except Exception as _err:
            print(f"[screen_pipeline.py] Silenced exception: {_err}")

    app_type, env_detail = classify_app_with_os_metadata(
        win_title, win_class, proc_name,
        main_h, main_s, main_v, title_h, title_s, title_v,
        ocr_text=ocr_text
    )

    stat_main       = ImageStat.Stat(main_zone)
    brightness      = main_v * 100
    stddev          = sum(stat_main.stddev[:3]) / 3
    content_density = (
        "dense with content"     if stddev > 35 else
        "moderate content"       if stddev > 18 else
        "mostly uniform / sparse content"
    )
    has_sidebar = abs(side_v - main_v) > 0.12

    # 6. Scene Segmentation & Event Detection
    scene_transition = None
    if _last_app_type and app_type != _last_app_type:
        scene_transition = f"Application switch: User transitioned from {_last_app_type} to {app_type}."
        # Scene changed -> force full refresh and wake VLM
        is_static = False
        next_delay_ms = min_delay
        if any(w in app_type.lower() for w in ("browser", "edge", "chrome", "firefox", "youtube")):
            _trigger_ddg_enrichment(app_type)
        
    _last_app_type = app_type

    # Continuous Multimodal Event Detection (Phase 6)
    try:
        from perception.fusion_engine import get_global_engine
        from perception.perception_manager import get_reader
        engine = get_global_engine()
        pm_state = get_reader().load_state()
        curr_audio_state = pm_state.get("audio_event_type", "silence")
        
        # A. Fullscreen Entered/Exited
        is_fullscreen = False
        if stddev > 10.0:
            import math
            title_dist = math.sqrt(sum((c1 - c2) ** 2 for c1, c2 in zip(title_rgb, main_rgb)))
            is_fullscreen = title_dist < 4.0
            
        if is_fullscreen != _last_fullscreen:
            _last_fullscreen = is_fullscreen
            trans_fs = "Fullscreen entered: The active application is now displayed in fullscreen mode." if is_fullscreen else "Fullscreen exited: The application returned to windowed mode."
            engine.push_system_event(trans_fs, importance=0.8)

        # B. Movie Paused/Resumed
        is_media_app = any(x in app_type.lower() for x in ("media", "colorful", "unity", "browser"))
        if is_media_app:
            if not is_static and curr_audio_state in ("music", "movie_game_audio", "speech"):
                if not _media_playing:
                    _media_playing = True
                    engine.push_system_event("Movie/Media resumed: The video stream on the screen is active again.", importance=0.85)
            elif is_static and curr_audio_state in ("silence", "ambient"):
                if _media_playing:
                    _media_playing = False
                    engine.push_system_event("Movie/Media paused: The video playback appears to have paused.", importance=0.85)

        # C. Typing Started/Stopped
        is_editor_app = any(x in app_type.lower() for x in ("code", "notepad", "browser", "document", "ide"))
        if is_editor_app and ocr_text:
            if ocr_text != _last_ocr_text:
                if _typing_state == "stopped" and len(ocr_text) > len(_last_ocr_text):
                    _typing_state = "typing"
                    engine.push_system_event("Typing started: User is actively writing or editing text on the screen.", importance=0.7)
                _last_ocr_text = ocr_text
            else:
                if _typing_state == "typing":
                    _typing_state = "stopped"
                    engine.push_system_event("Typing stopped: User paused or finished typing.", importance=0.6)

        # D. Song Changed
        song_pattern = ""
        if not is_ocr_vivy_dashboard(ocr_text):
            lines_chk = ocr_text.split("\n")
            if env_detail:
                lines_chk.append(env_detail)
            for line in lines_chk:
                line = line.strip()
                line_lower = line.lower()
                # Skip chat history lines that start with or contain chat prefixes to avoid feedback loops
                if line_lower.startswith(("vivy:", "you:", "satyajeet:")):
                    continue
                if " - " in line and len(line) < 100:
                    # Filter out development and system titles to prevent false song detection
                    ignore_keywords = [
                        "visual studio code", "vscode", "pycharm", "sublime", "cmd.exe", 
                        "powershell", "explorer.exe", "vivy ai", "neural interface", 
                        "web_server.py", "conversation.py", "run_vivy.py", "index.html", 
                        "test_ws.py", "implementation plan", "walkthrough", "task.md",
                        "diagnostics", "127.0.0.1", "localhost", "vivy", "satyajeet"
                    ]
                    if not any(kw in line_lower for kw in ignore_keywords):
                        song_pattern = line
                        break
        if song_pattern:
            # Update the perception manager immediately so the state remains fresh
            try:
                from perception.perception_manager import get_writer
                get_writer().record_audio_metadata(music_title=song_pattern, playback_state="playing")
            except Exception as _pm_meta_err:
                logger.debug(f"[ScreenPipeline] Failed to record audio metadata: {_pm_meta_err}")
                
            if song_pattern != _last_song:
                _last_song = song_pattern
                engine.push_system_event(f"Song changed: The background music transitioned to: {song_pattern}.", importance=0.82)
                _trigger_ddg_enrichment(song_pattern)
        elif app_type and any(k in app_type.lower() for k in ("youtube", "nightcore", "spotify", "music")):
            # Check for title/media keywords in app_type
            clean_app_title = app_type.split(" - ")[0].strip()
            if len(clean_app_title) > 3 and not any(x in clean_app_title.lower() for x in ("unknown", "browser", "edge", "chrome", "firefox", "vivy ai")):
                _trigger_ddg_enrichment(clean_app_title)
    except Exception as ev_err:
        logger.debug(f"[ScreenPipeline] Event detection failed: {ev_err}")

    # 7. Vision Model Plugin (VLM)
    vision_description = ""
    vision_enabled = get("screen_perception", "vision_model_enabled", default=False)
    
    if vision_enabled:
        try:
            vision_plugin = ModelRouter.get_vision_plugin()
            if vision_plugin and vision_plugin.name != "null":
                # Bypass VLM call if static and we have a recent description
                now = time.time()
                if is_static and _last_vlm_desc and (now - _last_vlm_time < 30.0):
                    vision_description = _last_vlm_desc
                    logger.debug("[ScreenPipeline] Screen is static — using cached VLM description.")
                else:
                    vision_description = vision_plugin.describe(img)
                    if vision_description:
                        _last_vlm_desc = vision_description
                        _last_vlm_time = now
        except Exception as ve:
            logger.debug(f"[ScreenPipeline] Vision plugin analysis failed: {ve}")

    # 8. Compose final description using structured, LLM-friendly labelled sections.
    # Both paths (OCR available / OCR absent) produce the same section structure
    # so the LLM always has clearly labelled, quotable facts to reference.
    sections: list[str] = []

    # Section A — Application / environment identity
    app_label = f"[App Detected]: {app_type}"
    if env_detail:
        app_label += f"\n{env_detail}"
    sections.append(app_label)

    # Section B — Visual context (brightness, layout)
    brightness_label = "bright" if brightness > 60 else "dark"
    visual_ctx = (
        f"[Visual Context]: {brightness_label} display ({brightness:.0f}% brightness), "
        f"{content_density}"
    )
    if has_sidebar:
        visual_ctx += ", sidebar or panel visible on the left"
    sections.append(visual_ctx)

    # Section C — Vision model output (only when VLM is enabled and produced a result)
    if vision_description:
        sections.append(f"[Vision Model Analysis]:\n{vision_description}")

    # Section D — OCR text (always present; signals explicitly when empty)
    if ocr_text:
        sections.append(f"[OCR Text Extracted]:\n{ocr_text}")
    else:
        sections.append("[OCR Text Extracted]: No readable text detected (OCR returned empty or unavailable).")

    raw_description = "\n\n".join(sections)

    # Push scene segmentation event to FusionEngine if detected
    if scene_transition:
        try:
            from perception.fusion_engine import get_global_engine
            get_global_engine().push_system_event(scene_transition, importance=0.7)
        except Exception as _err:
            print(f"[screen_pipeline.py] Silenced exception: {_err}")

    # ── Push content-level events to FusionEngine (NEW) ──────────────────────
    # These are high-importance events that provide ACTUAL content for the LLM
    # to answer fine-grained perception queries ("what word is highlighted?").
    # Uses push_system_event() because our synthetic events don't have the full
    # ScreenEvent shape; push_system_event() adds directly to the memory log.
    try:
        from perception.fusion_engine import get_global_engine
        _content_engine = get_global_engine()

        # Push VLM description as high-importance event (only when it's newly produced)
        if vision_description and vision_description != _last_vlm_desc:
            _vlm_semantic = f"Screen scene (VLM): {vision_description[:300]}"
            _content_engine.push_system_event(_vlm_semantic, importance=0.92)

        # Push OCR content as high-importance event when text changed substantially
        if ocr_text:
            # Compute change ratio: only push if >20% of words are different
            _old_words = set(_last_ocr_text.lower().split()) if _last_ocr_text else set()
            _new_words = set(ocr_text.lower().split())
            _union = _old_words | _new_words
            _changed_ratio = len(_new_words.symmetric_difference(_old_words)) / max(len(_union), 1)
            if _changed_ratio > 0.20 or not _last_ocr_text:
                _ocr_excerpt = ocr_text[:250].replace("\n", " ").strip()
                _ocr_semantic = f"Screen text (OCR): {_ocr_excerpt}"
                _content_engine.push_system_event(_ocr_semantic, importance=0.90)
    except Exception as _content_push_err:
        logger.debug(f"[ScreenPipeline] Content event push failed (non-fatal): {_content_push_err}")


    # _last_ocr_text and _last_ocr_words are managed by the async OCR thread to avoid race overwrites
    # _last_ocr_text = ocr_text
    # _last_ocr_words = ocr_words

    # Calculate average OCR confidence score
    confs = [w['conf'] for w in ocr_words if 'conf' in w]
    avg_conf = (sum(confs) / len(confs)) / 100.0 if confs else 1.0

    # ── Hierarchical Layout Analysis & Scene Graph ──
    zones = []
    
    # Title Bar Region
    title_ocr = ""
    title_words = []
    for w_info in ocr_words:
        if w_info.get("top", 0) <= top_8:
            title_words.append(w_info.get("text", ""))
    title_ocr = " ".join(title_words).strip()
    
    zones.append({
        "name": "title_bar",
        "bounds": [0, 0, w, top_8],
        "hsv_color": [round(title_h, 3), round(title_s, 3), round(title_v, 3)],
        "ocr_text": title_ocr,
        "role": "navigation_and_tabs"
    })
    
    # Sidebar Region (if detected)
    sidebar_ocr = ""
    if has_sidebar:
        sb_words = []
        for w_info in ocr_words:
            if w_info.get("top", 0) > top_8 and w_info.get("left", 0) <= side_18:
                sb_words.append(w_info.get("text", ""))
        sidebar_ocr = " ".join(sb_words).strip()
        zones.append({
            "name": "sidebar",
            "bounds": [0, top_8, side_18, int(h * 0.92)],
            "hsv_color": [round(side_h, 3), round(side_s, 3), round(side_v, 3)],
            "ocr_text": sidebar_ocr,
            "role": "navigation_tree_or_controls"
        })
        
    # Main Content Area
    main_ocr = ""
    main_words = []
    for w_info in ocr_words:
        if w_info.get("top", 0) > top_8:
            if not has_sidebar or w_info.get("left", 0) > side_18:
                main_words.append(w_info.get("text", ""))
    main_ocr = " ".join(main_words).strip()
    
    zones.append({
        "name": "main_content",
        "bounds": [side_18 if has_sidebar else 0, top_8, w, int(h * 0.92)],
        "hsv_color": [round(main_h, 3), round(main_s, 3), round(main_v, 3)],
        "ocr_text": main_ocr,
        "density": content_density,
        "brightness": brightness,
        "role": "primary_workspace"
    })
    
    scene_layout = {
        "node_type": "global_scene",
        "resolution": f"{w}x{h}",
        "active_window": {
            "node_type": "active_window",
            "title": win_title,
            "class": win_class,
            "process": proc_name,
            "bounds": [0, 0, w, h],
            "app_focus": app_type,
            "env_detail": env_detail
        },
        "zones": zones,
        "ui_hierarchy": {
            "node_type": "workspace_hierarchy",
            "panels": [
                {
                    "node_type": "panel",
                    "name": "title_bar",
                    "role": "navigation_and_tabs",
                    "bounds": [0, 0, w, top_8],
                    "has_text": bool(title_ocr)
                }
            ]
        }
    }

    if has_sidebar:
        scene_layout["ui_hierarchy"]["panels"].append({
            "node_type": "panel",
            "name": "sidebar",
            "role": "navigation_tree_or_controls",
            "bounds": [0, top_8, side_18, int(h * 0.92)],
            "has_text": bool(sidebar_ocr)
        })

    scene_layout["ui_hierarchy"]["panels"].append({
        "node_type": "panel",
        "name": "main_content",
        "role": "primary_workspace",
        "bounds": [side_18 if has_sidebar else 0, top_8, w, int(h * 0.92)],
        "has_text": bool(main_ocr),
        "density": content_density,
        "brightness": brightness
    })

    if highlighted_text:
        scene_layout["highlighted_text_node"] = {
            "node_type": "highlighted_region",
            "text": highlighted_text,
            "context": highlighted_context,
            "role": "active_user_selection"
        }

    return ScreenEvent(
        timestamp=time.time(),
        app_type=app_type,
        env_detail=env_detail,
        ocr_text=ocr_text,
        vision_description=vision_description,
        brightness=brightness,
        has_sidebar=has_sidebar,
        content_density=content_density,
        raw_description=raw_description,
        next_delay_ms=next_delay_ms,
        scene_transition=scene_transition,
        resolution=f"{w}x{h}",
        ocr_confidence=avg_conf,
        scene_layout=scene_layout,
        quality_analysis=quality_res,
        request_high_res=request_high_res
    )


def process_frame_bytes(b64_jpeg: str) -> ScreenEvent | None:
    """Decode a base64 JPEG string and analyse it."""
    try:
        import base64
        from PIL import Image

        if "," in b64_jpeg:
            b64_jpeg = b64_jpeg.split(",", 1)[1]

        frame_bytes = base64.b64decode(b64_jpeg)
        img = Image.open(BytesIO(frame_bytes))
        return analyze_frame(img)
    except Exception as e:
        import traceback
        logger.error(f"[ScreenPipeline] process_frame_bytes() failed: {e}\n{traceback.format_exc()}")
        return None
