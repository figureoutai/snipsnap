import os
import asyncio
import threading

from PIL import Image
from av import VideoFrame
from utils.logger import app_logger as logger
from utils.helpers import get_video_frame_filename
from utils.unique_async_queue import UniqueAsyncQueue

class VideoProcessor:
    def __init__(self,  output_dir: str, video_frame_q: UniqueAsyncQueue, video_frame_sample_rate: int = 2):
        self.sample_rate = video_frame_sample_rate
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)   
        self.frames_q = video_frame_q
        self.frame_index = 0
        self.last_saved_pts = None

    async def process_frames(self, stream_id: str, video_processor_event: asyncio.Event, stream_processor_event: threading.Event):
        logger.info("[VideoProcessor] started to sample the video frames")
        while True:
            if video_processor_event.is_set() or (stream_processor_event.is_set() and self.frames_q.empty()):
                logger.info("[VideoProcessor] stop event was set")
                break
            
            if self.frames_q.empty():
                await asyncio.sleep(0.2)
                continue

            frame: VideoFrame = await self.frames_q.get()

            ts = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
            ts = round(ts, 3)
            
            if self.last_saved_pts is not None and ts - self.last_saved_pts < (1/self.sample_rate):
                # logger.debug("[VideoProcessor] skipping the frame")
                continue

            # logger.debug(f"[VideoProcessor] captured the frame at {ts}")           
            filename = get_video_frame_filename(self.frame_index)
            filepath = os.path.join(self.output_dir, filename)

            try:
                # TODO: Need to save this to S3 bucket as well
                img: Image = frame.to_image()
                if not os.path.exists(filepath):
                    img.save(filepath, format="JPEG")
            except Exception as e:
                print("Error saving video frame:", e)
                return

            # TODO: Push this to aurora db, use async functions
            metadata = {
                "stream_id": stream_id,
                "filename": filename,
                "frame_index": self.frame_index,
                "timestamp": ts,
                "pts": frame.pts,
                "width": getattr(frame, "width", None),
                "height": getattr(frame, "height", None)
            }
            self.frame_index += 1
            self.last_saved_pts = ts
        
        video_processor_event.set()
