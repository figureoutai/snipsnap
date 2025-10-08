from typing import List
from llm.claude import Claude
from candidate_clip import CandidateClip
from utils.helpers import numpy_to_base64

class CaptionService:
    def __init__(self):
        self.llm = Claude()

    async def generate_clip_caption(self, candidate_clip: CandidateClip, audio_metadata: List):
        transcript = candidate_clip.get_transcript(audio_metadata)
        images = [numpy_to_base64(img) for img in candidate_clip.load_images()]
        response = self.llm.invoke(prompt="", response_type="json", query=transcript, images=images, max_tokens=500)
        return response["highlight_score"], response["caption"]
