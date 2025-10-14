import av
import os
import cv2
import json
import numpy as np

from config import VIDEO_FRAME_SAMPLE_RATE
from utils.logger import app_logger as logger
from utils.helpers import get_audio_filename, get_video_frame_filename

class CandidateClip:
    def __init__(self, base_path, start_time, end_time):
        self.start_time = start_time
        self.end_time = end_time
        self.base_path = base_path

    def get_audio_chunk_indexes(self, chunk_duration):
        start_chunk = int(self.start_time // chunk_duration)
        end_chunk = int(self.end_time // chunk_duration)

        # If end_time is exactly on a boundary, no segment lies in the prvious chunk
        if self.end_time % chunk_duration == 0 and self.end_time != 0:
            end_chunk -= 1

        return list(range(start_chunk, end_chunk + 1))

    def load_audio_segment(self, chunk_duration):
        chunks = self.get_audio_chunk_indexes(chunk_duration)
        sr = 0
        audios = []
        for c in chunks:
            filepath = f"{self.base_path}/audio_chunks/{get_audio_filename(c)}"
            if not os.path.exists():
                logger.warning(f"[SaliencyScorerService] audio chunk does not exist {os.path.basename(filepath)}")
                continue
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
        start_offset = int((self.start_time - chunks[0] * chunk_duration) * sr * 2)
        end_offset = int(start_offset + (self.end_time - self.start_time) * sr * 2)
        return full_audio[:, start_offset:end_offset]
    
    def load_images(self):
        images = []
        for i in range(self.start_time, self.end_time * VIDEO_FRAME_SAMPLE_RATE):
            filepath = f"{self.base_path}/frames/{get_video_frame_filename(i)}"
            if not os.path.exists():
                logger.warning(f"[SaliencyScorerService] video frame does not exist {os.path.basename(filepath)}")
                continue
            images.append(cv2.imread(filename=filepath))
        
        return images
    
    def get_transcript(self, audio_metadata):
        words = []
        for meta in audio_metadata:
            start_timestamp = 0 if not meta["start_timestamp"] else meta["start_timestamp"]
            for item in json.loads(meta["transcript"]):
                if self.start_time <= item["start_time"] + start_timestamp and self.end_time >= item["end_time"]:
                    if item['type'] != 'pronunciation':
                        continue
                    words.append(item['content'])
        
        return ' '.join(words) 
