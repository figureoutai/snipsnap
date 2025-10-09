from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add transcript column to audio_metadata table."""
    
    # Add transcript column
    op.add_column(
        'audio_metadata',
        sa.Column('transcript', sa.Text(), nullable=True)
    )
    
    # Optional: Add index on transcript for full-text search (MySQL)
    # Uncomment if you need full-text search capabilities
    # op.create_index(
    #     'idx_transcript_fulltext',
    #     'audio_metadata',
    #     ['transcript'],
    #     mysql_prefix='FULLTEXT'
    # )


def downgrade() -> None:
    """Remove transcript column from audio_metadata table."""
    
    # Drop index if it was created
    # op.drop_index('idx_transcript_fulltext', 'audio_metadata')
    
    # Drop column
    op.drop_column('audio_metadata', 'transcript')
