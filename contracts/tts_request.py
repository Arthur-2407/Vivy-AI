from dataclasses import dataclass
from contracts.pipeline_event import PipelineEvent

@dataclass
class TTSRequest(PipelineEvent):
    chunk_id: int = 0
    sequence_number: int = 0
    text: str = ""
    is_final_chunk: bool = False
