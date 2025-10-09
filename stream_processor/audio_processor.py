import os
import av
import time
import asyncio
import threading

from typing import List
from av import AudioFrame
from av.audio.resampler import AudioResampler
from repositories.s3_service import S3Service
from utils.logger import app_logger as logger
from repositories.aurora_service import AuroraService
from utils.unique_async_queue import UniqueAsyncQueue
from utils.helpers import get_audio_filename, EMPTY_STRING
from config import (
    AUDIO_BUCKET_PREFIX,
    IMAGE_BUCKET_PREFIX,
    S3_BUCKET_NAME,
    S3_REGION,
    TARGET_SAMPLE_RATE,
    AUDIO_METADATA_TABLE_NAME,
)


class AudioChunker:
    def __init__(self, audio_chunk_dir, chunk_duration):
        self.chunk_duration = chunk_duration
        self.buffer: List[AudioFrame] = []
        self.start_pts = None
        self.chunk_index = 0
        self.output_dir = audio_chunk_dir
        self.is_db_writer_initialized = False

        self.db_writer = AuroraService(pool_size=10)

        self.s3_writer = S3Service(
            bucket_name=S3_BUCKET_NAME,
            region_name=S3_REGION,
            audio_prefix=AUDIO_BUCKET_PREFIX,
            image_prefix=IMAGE_BUCKET_PREFIX,
        )

        os.makedirs(self.output_dir, exist_ok=True)

    async def intialize_db_writer(self):
        if not self.is_db_writer_initialized:
            logger.info("Initializing DB Connection in AudioChunker")
            await self.db_writer.initialize()
            self.is_db_writer_initialized = True

    async def handle_frame(self, stream_id, frame: AudioFrame):
        ts = float(frame.pts * frame.time_base) if getattr(frame, "pts", None) else None
        if self.start_pts is None and ts is not None:
            self.start_pts = ts
        self.buffer.append(frame)
        if (
            self.start_pts is not None
            and ts is not None
            and ts - self.start_pts >= self.chunk_duration
        ):
            await self.flush_chunk(stream_id)

    async def flush_chunk(self, stream_id):
        if not self.buffer:
            return

        filename = get_audio_filename(self.chunk_index)
        filepath = os.path.join(self.output_dir, filename)

        await self.intialize_db_writer()

        try:
            output_container = av.open(filepath, mode="w")
            sample_rate = self.buffer[0].sample_rate
            layout = self.buffer[0].layout
            out_stream = output_container.add_stream(
                "pcm_s16le", rate=TARGET_SAMPLE_RATE, layout=layout
            )
            resampler = AudioResampler(
                format="s16", layout=layout, rate=TARGET_SAMPLE_RATE
            )

            for f in self.buffer:
                resampled_frames = resampler.resample(f)
                for new_frame in resampled_frames:
                    packets = out_stream.encode(new_frame)
                    output_container.mux(packets)
            output_container.close()

            last = self.buffer[-1]
            end_ts = float(last.pts * last.time_base) if last.pts else None

            metadata = {
                "stream_id": stream_id,
                "filename": filename,
                "chunk_index": self.chunk_index,
                "start_timestamp": round(self.start_pts, 3) if self.start_pts else None,
                "end_timestamp": round(end_ts, 3) if end_ts else None,
                "sample_rate": sample_rate,
                "captured_at": round(time.time()),
                "transcript": EMPTY_STRING, 
            }
                        
            # upload audio clip to S3 bucket
            self.s3_writer.upload_audio_nowait(stream_id, file_path=filepath)

            # store metadata into Aurora SQL DB
            self.db_writer.insert_dict_nowait(AUDIO_METADATA_TABLE_NAME, metadata)

            logger.info(f"[AudioChunker] Wrote chunk {os.path.basename(filepath)}")
        except Exception as e:
            logger.error(f"[AudioChunker] Error writing chunk {e}")
        finally:
            self.chunk_index += 1
            self.buffer = []
            self.start_pts = None


class AudioProcessor:
    def __init__(
        self,
        audio_chunk_dir,
        audio_frame_q: UniqueAsyncQueue,
        audio_chunk_duration_in_secs=5,
    ):
        self.chunker = AudioChunker(audio_chunk_dir, audio_chunk_duration_in_secs)
        self.frames_q = audio_frame_q

    async def process_frames(self, stream_id: str, audio_processor_event: asyncio.Event, stream_processor_event: threading.Event):
        logger.info("[AudioProcessor] started to sample the video frames")

        while True:
            if audio_processor_event.is_set() or (stream_processor_event.is_set() and self.frames_q.empty()):
                logger.info("[AudioProcessor] stop event was set")
                break

            if self.frames_q.empty():
                await asyncio.sleep(0.2)
                continue

            frame: AudioFrame = await self.frames_q.get()
            try:
                asyncio.create_task(self.chunker.handle_frame(stream_id, frame))
            except Exception as e:
                logger.error(f"[AudioProcessor] Audio worker error: {e}")

        # Flush chunker for any leftover chunks
        try:
            asyncio.create_task(self.chunker.flush_chunk(stream_id))
        except Exception as e:
            logger.error(f"[AudioProcessor] Error flushing chunk on shutdown: {e}")

        logger.info("[AudioProcessor] Audio worker exiting.")
        audio_processor_event.set()
