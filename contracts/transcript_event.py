from dataclasses import dataclass
from contracts.pipeline_event import PipelineEvent

@dataclass
class TranscriptEvent(PipelineEvent):
    text: str = ""
    is_final: bool = False
