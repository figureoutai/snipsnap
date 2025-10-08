import av
import cv2
import librosa
import numpy as np

from config import VIDEO_FRAME_SAMPLE_RATE, BASE_DIR
from utils.helpers import get_audio_filename, get_video_frame_filename

class SaliencyScorer:
    def __init__(self, alpha_motion=0.7, alpha_audio=0.3):
        self.alpha_motion = alpha_motion
        self.alpha_audio = alpha_audio

    # ---------- AUDIO ----------
    def compute_audio_rms(self, y: np.ndarray):
        if np.issubdtype(y.dtype, np.integer):
            max_val = np.iinfo(y.dtype).max
            y = y / max_val
        return np.mean(librosa.feature.rms(y=y)[0])

    # ---------- VIDEO (OPTICAL FLOW) ----------
    def compute_motion_score(self, frames: list[np.ndarray]):
        if len(frames) < 2:
            return 0.0
        gray_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
        magnitudes = []
        for i in range(len(gray_frames) - 1):
            flow = cv2.calcOpticalFlowFarneback(
                gray_frames[i], gray_frames[i + 1], None,
                0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            magnitudes.append(np.mean(mag))
        return float(np.mean(magnitudes))

    # ---------- FINAL SCORE ----------
    def compute_saliency(self, frames, audio):
        motion = self.compute_motion_score(frames)
        audio_rms = self.compute_audio_rms(audio)

        # Normalize each (soft)
        motion_n = np.tanh(motion)
        audio_n = np.tanh(audio_rms)

        saliency = (
            self.alpha_motion * motion_n +
            self.alpha_audio * audio_n 
        )
        return float(saliency)


class SaliencyScorerService:
    def __init__(self):
        self.scorer = SaliencyScorer()

    def get_audio_chunk_indexes(self, start_time, end_time, chunk_duration):
        start_chunk = int(start_time // chunk_duration)
        end_chunk = int(end_time // chunk_duration)

        # If end_time is exactly on a boundary, no segment lies in the prvious chunk
        if end_time % chunk_duration == 0 and end_time != 0:
            end_chunk -= 1

        return list(range(start_chunk, end_chunk + 1))
    
    def load_audio_segment(self, start_time, end_time, chunk_duration=5, base_path="audio_chunks"):
        chunks = self.get_audio_chunk_indexes(start_time, end_time, chunk_duration)
        sr = 0
        audios = []
        for c in chunks:
            filepath = f"{base_path}/{get_audio_filename(c)}"
            container = av.open(filepath)
            audio_stream = container.streams.audio[0]
            sr = audio_stream.rate
            frames = []
            for frame in container.decode(audio_stream):
                nd_array = frame.to_ndarray()
                frames.append(nd_array)
            audio = np.concatenate(frames, axis=1)
            audios.append(audio)

        # concatenate and crop to exact time window
        full_audio = np.concatenate(audios, axis=1)
        start_offset = int((start_time - chunks[0] * chunk_duration) * sr * 2)
        end_offset = int(start_offset + (end_time - start_time) * sr * 2)
        return full_audio[:, start_offset:end_offset]
    
    def load_images(self, start_time, end_time, base_path):
        images = []
        for i in range(start_time, end_time * VIDEO_FRAME_SAMPLE_RATE):
            filepath = f"{base_path}/{get_video_frame_filename(i)}"
            images.append(cv2.imread(filename=filepath))
        
        return images

    def score_saliency(self, start_time, end_time, stream_id):
        base_path= f"{BASE_DIR}/{stream_id}"
        audio = self.load_audio_segment(start_time, end_time, base_path=f"{base_path}/audio_chunks")
        frames = self.load_images(start_time, end_time, base_path=f"{base_path}/frames")
        return self.scorer.compute_saliency(frames, audio)
    
    

if __name__ == "__main__":
    scorer = SaliencyScorerService()
    for i in range(0, 25):
        start = i * 5
        end = start + 5
        if start > 0:
            scorer.score_saliency(start-2, end-2)
        else:
            scorer.score_saliency(0, 5)




