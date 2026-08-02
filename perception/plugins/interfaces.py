"""
perception/plugins/interfaces.py
================================
Abstract base classes (interfaces) for pluggable perception models.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from PIL import Image
import numpy as np

class BasePlugin(ABC):
    """Base interface for all plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the plugin."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the plugin is configured and its dependencies are loaded."""
        pass

class BaseVisionPlugin(BasePlugin):
    """Interface for pluggable Vision-Language Models (VLM)."""

    @abstractmethod
    def describe(self, image: Image.Image, prompt: str = "") -> str:
        """
        Analyze an image and return a description.
        
        Parameters
        ----------
        image : PIL.Image.Image
            The image frame to analyze.
        prompt : str, optional
            Guidance prompt for the vision model.
            
        Returns
        -------
        str
            Textual description of the image contents.
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> List[str]:
        """
        Return the list of capabilities supported by this model.
        Capabilities might include: 'scene_understanding', 'object_recognition',
        'facial_expressions', 'gestures', 'ui_interpretation', etc.
        """
        pass

class BaseSpeechPlugin(BasePlugin):
    """Interface for pluggable speech transcription engines."""

    @abstractmethod
    def transcribe(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcribe an audio file.
        
        Parameters
        ----------
        audio_path : str
            Path to the WAV audio file to transcribe.
            
        Returns
        -------
        dict
            Dict containing:
              - "text": str (the full transcription)
              - "confidence": float (0.0 to 1.0 confidence score)
              - "timestamps": List[Dict[str, Any]] (segment level timings, if supported)
              - "speaker_id": str (speaker classification if diarized, otherwise 'speaker_0')
        """
        pass

class BaseOCRPlugin(BasePlugin):
    """Interface for pluggable Optical Character Recognition (OCR) engines."""

    @abstractmethod
    def extract_text(self, image: Image.Image) -> str:
        """
        Run OCR on an image and extract visible text.
        
        Parameters
        ----------
        image : PIL.Image.Image
            The image frame to run OCR on.
            
        Returns
        -------
        str
            Extracted text.
        """
        pass

class BaseAudioAnalysisPlugin(BasePlugin):
    """Interface for pluggable semantic audio classification engines."""

    @abstractmethod
    def analyze(self, audio_data: np.ndarray, sample_rate: int = 16000) -> List[Dict[str, Any]]:
        """
        Analyze an audio chunk to identify events like music, laughter, silence, alarms.
        
        Parameters
        ----------
        audio_data : np.ndarray
            1D float32 numpy array representing the audio samples.
        sample_rate : int
            Audio sample rate.
            
        Returns
        -------
        list of dict
            List of detected events. Each event dict contains:
              - "event_type": str ('music', 'applause', 'laughter', 'crying', 'explosion', 'alarm', 'silence', 'ambient')
              - "description": str (human-readable explanation)
              - "confidence": float (0.0 to 1.0)
              - "duration_seconds": float (chunk duration)
        """
        pass
