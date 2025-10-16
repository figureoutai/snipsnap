import os
import json
import asyncio
import aiofiles

from asyncio import Event
from utils.helpers import ERROR_STRING, retry_with_backoff
from utils.logger import app_logger as logger
from amazon_transcribe.model import TranscriptEvent
from repositories.aurora_service import AuroraService
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from config import AWS_REGION, LANGUAGE_CODE, AUDIO_METADATA_TABLE_NAME


class TranscriptEventHandler(TranscriptResultStreamHandler):
    def __init__(self, stream_id, filename, output_stream):
        super().__init__(output_stream)
        self.transcript_data = []
    
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            if result.alternatives and not result.is_partial:
                for item in result.alternatives[0].items:
                    item_data = {
                        "start_time": item.start_time,
                        "end_time": item.end_time,
                        "content": item.content,
                        "type": item.item_type,
                    }
                    self.transcript_data.append(item_data)


class AudioTranscriber:
    def __init__(self, audio_chunk_dir: str):
        self.chunk_dir = audio_chunk_dir
        self.is_db_service_initialized = False
        self.db_service = AuroraService(pool_size=10)

    async def intialize_db_service(self):
        if not self.is_db_service_initialized:
            logger.info("[AudioTranscriber] Initializing DB Connection")
            await self.db_service.initialize()
            self.is_db_service_initialized = True
    
    @retry_with_backoff(retries=3, backoff_in_seconds=2)
    async def transcribe_audio_stream(self, stream_id, filename, sample_rate):
        logger.info(f"[AudioTranscriber] Starting transcription for {filename}, rate={sample_rate}")
        transcribe_client = TranscribeStreamingClient(region=AWS_REGION)
        transcription_stream = await transcribe_client.start_stream_transcription(
            language_code=LANGUAGE_CODE,
            media_sample_rate_hz=sample_rate,
            media_encoding="pcm",
        )
        filepath = os.path.join(self.chunk_dir, filename)
        
        async def send_audio_chunks():
            if not os.path.exists(filepath):
                logger.error(f"[AudioTranscriber] File not found: {filepath}")
                return
            try:
                async with aiofiles.open(filepath, 'rb') as audio_file:
                    chunk_size = 1024 * 16
                    while True:
                        chunk = await audio_file.read(chunk_size)
                        if not chunk:
                            logger.info(f"[AudioTranscriber] no chunk read from file")
                            break
                        await transcription_stream.input_stream.send_audio_event(audio_chunk=chunk)
                await transcription_stream.input_stream.end_stream()
            except Exception as e:
                logger.exception(f"[AudioTranscriber] Error reading/sending {filepath}: {e}")

        event_handler = TranscriptEventHandler(stream_id, filename, transcription_stream.output_stream)
        await asyncio.gather(send_audio_chunks(), event_handler.handle_events())

        await self.db_service.update_dict(
            table_name=AUDIO_METADATA_TABLE_NAME,
            data={"transcript": json.dumps(event_handler.transcript_data)},
            where_clause="stream_id=%s AND filename=%s",
            where_params=(stream_id, filename)
        )
        logger.info(f"[TranscriptEventHandler] pushed transcript for {filename} to audio metadata table.")


    async def transcribe_audio(self, stream_id, audio_processor_event: Event):
        await self.intialize_db_service()
        start_chunk = 0
        
        while True:
            audio_chunks = await self.db_service.get_audios_by_stream(
                stream_id=stream_id, start_chunk=start_chunk, limit=10
            )

            if len(audio_chunks) == 0:
                if audio_processor_event.is_set():
                    break
                logger.info("[AudioTranscriber] waiting for audio chunks")
                await asyncio.sleep(0.2)
                continue

            for chunk in audio_chunks:
                filename = chunk["filename"]
                logger.info(f"[AudioTranscriber] trancribing {filename}...")
                sample_rate = chunk["sample_rate"]
                stream_id = chunk["stream_id"]
                try:
                    await self.transcribe_audio_stream(stream_id, filename, sample_rate)
                except Exception as e:
                    logger.error(f"[AudioTranscriber] encountered error while transcribing audio {filename}: {str(e)}")
                    await self.db_service.update_dict(
                        table_name=AUDIO_METADATA_TABLE_NAME,
                        data={"transcript": ERROR_STRING},
                        where_clause="stream_id=%s AND filename=%s",
                        where_params=(stream_id, filename)
                    )
                    logger.info(f"[TranscriptEventHandler] transcription errored pushed error string for {filename} to audio metadata table.")
                logger.info(f"[AudioTranscriber] {filename} transcribed.")

            start_chunk = audio_chunks[-1]["chunk_index"] + 1

            await asyncio.sleep(2)

        logger.info("[AudioTranscriber] exiting audio transcriber service")
