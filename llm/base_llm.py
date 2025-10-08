from typing import List
class LLM():
    def __init__(self):
        self.llm = None

    def invoke(self, prompt: str, response_type: str, query: str="", images: List[str]=[], max_tokens=300):
        pass