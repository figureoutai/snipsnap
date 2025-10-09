import os
import json
import asyncio
import aiofiles

from asyncio import Event
from utils.logger import app_logger as logger
from repositories.aurora_service import AuroraService
from config import AWS_REGION, LANGUAGE_CODE, AUDIO_METADATA_TABLE_NAME
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent, StartStreamTranscriptionEventStream


class TranscriptEventHandler(TranscriptResultStreamHandler):
    def __init__(self, stream_id, filename, output_stream):
        super().__init__(output_stream)
        self.transcript_data = []
        self.filename = filename
        self.stream_id = stream_id
        self.is_db_writer_initialized = False
        self.db_writer = AuroraService(pool_size=10)
    
    async def intialize_db_writer(self):
        if not self.is_db_writer_initialized:
            logger.info("[TranscriptEventHandler] Initializing DB Connection")
            await self.db_writer.initialize()
            self.is_db_writer_initialized = True

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        await self.intialize_db_writer()
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
        
        await self.db_writer.update_dict(
            table_name=AUDIO_METADATA_TABLE_NAME,
            data={"transcript": json.dumps(self.transcript_data)},
            where_clause="stream_id=%s AND filename=%s",
            where_params=(self.stream_id, self.filename)
        )


class AudioTranscriber:
    def __init__(self, audio_chunk_dir: str):
        self.client = TranscribeStreamingClient(region=AWS_REGION)
        self.chunk_dir = audio_chunk_dir
        self.is_db_reader_initialized = False
        self.db_reader = AuroraService(pool_size=10)

    async def intialize_db_reader(self):
        if not self.is_db_reader_initialized:
            logger.info("[AudioTranscriber] Initializing DB Connection")
            await self.db_reader.initialize()
            self.is_db_reader_initialized = True

    async def transcribe_audio(self, stream_id, audio_processor_event: Event):
        await self.intialize_db_reader()
        start_chunk = 0
        
        while True:
            audio_chunks = await self.db_reader.get_audios_by_stream(
                stream_id=stream_id, start_chunk=start_chunk, limit=10
            )

            if len(audio_chunks) == 0 and audio_processor_event.is_set():
                break

            for chunk in audio_chunks:
                filepath = os.path.join(self.chunk_dir, chunk["filename"])
                sample_rate = chunk["sample_rate"]
                stream_id = chunk["stream_id"]
                transcription_stream = await self.client.start_stream_transcription(
                    language_code=LANGUAGE_CODE,
                    media_sample_rate_hz=sample_rate,
                    media_encoding="pcm",
                )

                filename = os.path.basename(filepath)
                event_handler = TranscriptEventHandler(stream_id, filename, transcription_stream.output_stream)
                await asyncio.gather(self.send_audio_chunks(filepath, transcription_stream), event_handler.handle_events())

            start_chunk = chunk["chunk_index"] + 1

            await asyncio.sleep(2)

    async def send_audio_chunks(filepath: str, transcription_stream: StartStreamTranscriptionEventStream):
        async with aiofiles.open(filepath, 'rb') as audio_file:
            chunk_size = 1024 * 16
            while True:
                chunk = await audio_file.read(chunk_size)
                if not chunk:
                    break
                await transcription_stream.input_stream.send_audio_event(audio_chunk=chunk)
        await transcription_stream.input_stream.end_stream()
