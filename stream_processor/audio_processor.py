from av import AudioFrame

class AudioProcessor:
    def __init__(self, audio_chunk_dir, audio_chunk_rate_in_secs=5):
        self.audio_chunk_dir = audio_chunk_dir
        self.chunk_rate = audio_chunk_rate_in_secs

    def handle_frame(self, frame: AudioFrame):
        pass