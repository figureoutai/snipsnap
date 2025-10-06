import os

from PIL import Image
from av import VideoFrame
from utils.unique_async_queue import UniqueAsyncQueue
from utils.logger import app_logger as logger

class VideoProcessor:
    def __init__(self,  output_dir: str, video_frame_q: UniqueAsyncQueue, video_frame_sample_rate: int = 2):
        self.sample_rate = video_frame_sample_rate
        self.output_dir = output_dir
        self.frames_q = video_frame_q
        self.frame_index = 0
        self.last_saved_pts = None

    async def sample_frames(self):
        logger.info("[Video Processor] started to sample the video frames")
        while True:
            frame: VideoFrame = await self.frames_q.get()

            ts = float(frame.pts * frame.time_base) if frame.pts is not None else 0.0
            ts = round(ts, 3)
            if self.last_saved_pts is not None and ts - self.last_saved_pts < self.sample_rate:
                return

            filename = f"frame_{self.frame_index:09d}.jpg"
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
                "filename": filename,
                "frame_index": self.frame_index,
                "timestamp": ts,
                "pts": frame.pts,
                "width": getattr(frame, "width", None),
                "height": getattr(frame, "height", None)
            }
            self.frame_index += 1
            self.last_saved_pts = ts

