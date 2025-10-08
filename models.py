from sqlalchemy import Column, String, Integer, BigInteger, Float, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class VideoMetadata(Base):
    __tablename__ = 'video_metadata'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stream_id = Column(String(255), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    frame_index = Column(BigInteger, nullable=False)
    timestamp = Column(Float, nullable=True)
    pts = Column(BigInteger, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_stream_frame', 'stream_id', 'frame_index'),
        Index('idx_stream_timestamp', 'stream_id', 'timestamp'),
        Index('idx_filename', 'filename'),
    )


class AudioMetadata(Base):
    __tablename__ = 'audio_metadata'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    stream_id = Column(String(255), nullable=False, index=True)
    filename = Column(String(512), nullable=False)
    chunk_index = Column(BigInteger, nullable=False)
    start_timestamp = Column(Float, nullable=True)
    end_timestamp = Column(Float, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    captured_at = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_stream_chunk', 'stream_id', 'chunk_index'),
        Index('idx_stream_timestamps', 'stream_id', 'start_timestamp', 'end_timestamp'),
        Index('idx_filename', 'filename'),
    )