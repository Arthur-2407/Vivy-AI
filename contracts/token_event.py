from dataclasses import dataclass
from contracts.pipeline_event import PipelineEvent

@dataclass
class TokenEvent(PipelineEvent):
    text: str = ""
    is_final_state: bool = False
    history: list = None
    reply: str = None
