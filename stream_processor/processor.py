import av
import asyncio

from threading import Event
from av.stream import Disposition
from config import MAX_STREAM_DURATION
from utils.logger import app_logger as logger
from utils.unique_async_queue import UniqueAsyncQueue


class StreamProcessor:
    def __init__(self, url: str, audio_frame_q: UniqueAsyncQueue, video_frame_q: UniqueAsyncQueue):
        if not audio_frame_q or not video_frame_q:
            raise Exception("Stream processor resquires audio and video frame queues")
        self.audio_frame_q = audio_frame_q
        self.video_frame_q = video_frame_q
        self.stream_url = url
        self.max_seconds = MAX_STREAM_DURATION

    def start_stream(self, loop, stream_processor_event: Event):
        logger.info(f"[Stream Proceesor] Starting to read the stream {self.stream_url}")
        try:
            with av.open(self.stream_url) as container:
                video_stream = container.streams.video[0] if container.streams.video else None
                audio_stream = None
                for stream in container.streams.audio:
                    if stream.disposition & Disposition.default:
                        audio_stream = stream
                        break
                if audio_stream is None and container.streams.audio:
                    audio_stream = container.streams.audio[0]

                if not video_stream:
                    raise Exception("Stream does not have video stream")
                if not audio_stream:
                    raise Exception("Stream does not have audio stream")
                
                for packet in container.demux(audio_stream, video_stream):
                    if stream_processor_event.is_set():
                        break
                    try:
                        for frame in packet.decode():
                            if frame is None:
                                continue
                            if self.max_seconds is not None and frame.pts:
                                media_time = float(frame.pts * frame.time_base)
                                if media_time > self.max_seconds:
                                    stream_processor_event.set()
                                    return
                            if packet.stream.type == "video":
                                loop.call_soon_threadsafe(self.video_frame_q.put_nowait, frame)
                            elif packet.stream.type == "audio":
                                loop.call_soon_threadsafe(self.audio_frame_q.put_nowait, frame)
                    except Exception as e:
                        logger.error(f"[Stream Processor] Error decoding packet: {e}")
                        continue
        except Exception as e:
            logger.error(f"[Stream Processor] encountered error: {e}")
        finally:
            logger.info("[Stream Processor] Ending the stream, exiting.")
            stream_processor_event.set()