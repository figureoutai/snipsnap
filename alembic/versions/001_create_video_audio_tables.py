from alembic import op
import sqlalchemy as sa
from sqlalchemy import Index

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create video_metadata table
    op.create_table(
        'video_metadata',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('stream_id', sa.String(length=255), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('frame_index', sa.BigInteger(), nullable=False),
        sa.Column('timestamp', sa.Float(), nullable=True),
        sa.Column('pts', sa.BigInteger(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for video_metadata
    op.create_index('idx_stream_id', 'video_metadata', ['stream_id'])
    op.create_index('idx_stream_frame', 'video_metadata', ['stream_id', 'frame_index'])
    op.create_index('idx_stream_timestamp', 'video_metadata', ['stream_id', 'timestamp'])
    op.create_index('idx_filename', 'video_metadata', ['filename'])
    
    # Create audio_metadata table
    op.create_table(
        'audio_metadata',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('stream_id', sa.String(length=255), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=False),
        sa.Column('chunk_index', sa.BigInteger(), nullable=False),
        sa.Column('start_timestamp', sa.Float(), nullable=True),
        sa.Column('end_timestamp', sa.Float(), nullable=True),
        sa.Column('sample_rate', sa.Integer(), nullable=True),
        sa.Column('captured_at', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for audio_metadata
    op.create_index('idx_stream_id', 'audio_metadata', ['stream_id'])
    op.create_index('idx_stream_chunk', 'audio_metadata', ['stream_id', 'chunk_index'])
    op.create_index('idx_stream_timestamps', 'audio_metadata', ['stream_id', 'start_timestamp', 'end_timestamp'])
    op.create_index('idx_filename', 'audio_metadata', ['filename'])


def downgrade() -> None:
    # Drop tables
    op.drop_table('audio_metadata')
    op.drop_table('video_metadata')