import os
import asyncio
import threading

from PIL import Image
from av import VideoFrame
from utils.logger import app_logger as logger
from utils.helpers import get_video_frame_filename
from utils.unique_async_queue import UniqueAsyncQueue
from repositories.aurora_service import AuroraService
from repositories.s3_service import S3Service
from config import AUDIO_BUCKET_PREFIX, IMAGE_BUCKET_PREFIX, S3_BUCKET_NAME, S3_REGION, VIDEO_METADATA_TABLE_NAME

class VideoProcessor:
    def __init__(
        self,
        output_dir: str,
        video_frame_q: UniqueAsyncQueue,
        video_frame_sample_rate: int = 2,
    ):
        self.sample_rate = video_frame_sample_rate
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.frames_q = video_frame_q
        self.frame_index = 0
        self.last_saved_pts = None
        
        self.is_db_writer_initialized = False
        
        self.db_writer = AuroraService(pool_size=10)

        self.s3_writer = S3Service(
            bucket_name=S3_BUCKET_NAME,
            region_name=S3_REGION,
            audio_prefix=AUDIO_BUCKET_PREFIX,
            image_prefix=IMAGE_BUCKET_PREFIX,
        )
        
        
    async def intialize_db_writer(self):

        if not self.is_db_writer_initialized:
            logger.info("Initializing DB Connection in VideoProcessor")
            await self.db_writer.initialize()
            self.is_db_writer_initialized = True
                
    async def process_frames(self, stream_id: str, video_processor_event: asyncio.Event, stream_processor_event: threading.Event):
        logger.info("[VideoProcessor] started to sample the video frames")
        
        logger.info("Initializing DB Connection in VideoProcessor")
        await self.intialize_db_writer()
        
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

            if self.last_saved_pts is not None and ts - self.last_saved_pts < (
                1 / self.sample_rate
            ):
                # logger.debug("[VideoProcessor] skipping the frame")
                continue

            # logger.debug(f"[VideoProcessor] captured the frame at {ts}")           
            filename = get_video_frame_filename(self.frame_index)
            filepath = os.path.join(self.output_dir, filename)

            try:              
                
                img: Image = frame.to_image()
                                            
                # upload image to S3
                self.s3_writer.upload_image_nowait(
                    stream_id = stream_id,
                    file_data = img.tobytes(),
                    filename = filename
                )
                
                if not os.path.exists(filepath):
                    img.save(filepath, format="JPEG")
                del img
            except Exception as e:
                print("Error saving video frame:", e)
                return

            metadata = {
                "stream_id": stream_id,
                "filename": filename,
                "frame_index": self.frame_index,
                "timestamp": ts,
                "pts": frame.pts,
                "width": getattr(frame, "width", None),
                "height": getattr(frame, "height", None),
            }
            
            await self.db_writer.insert_dict(VIDEO_METADATA_TABLE_NAME, metadata)
        
            self.frame_index += 1
            self.last_saved_pts = ts
        
        video_processor_event.set()
