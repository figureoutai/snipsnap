from alembic import op
import sqlalchemy as sa
from sqlalchemy import Index

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'  # Update this to your previous migration ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    
    # Create score_metadata table
    op.create_table(
        'score_metadata',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('stream_id', sa.String(length=255), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('saliency_score', sa.Float(), nullable=True),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('highlight_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_stream_id', 'score_metadata', ['stream_id'])
    op.create_index('idx_stream_time', 'score_metadata', ['stream_id', 'start_time', 'end_time'])
    op.create_index('idx_stream_highlight_score', 'score_metadata', ['stream_id', 'highlight_score'])
    op.create_index('idx_highlight_score', 'score_metadata', ['highlight_score'])
    op.create_index('idx_saliency_score', 'score_metadata', ['saliency_score'])


def downgrade() -> None:
    op.drop_table('score_metadata')