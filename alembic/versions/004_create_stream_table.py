from alembic import op
import sqlalchemy as sa
from sqlalchemy import Index

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'  # Update this to your previous migration ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    
    # Create score_metadata table
    op.create_table(
        'stream_metadata',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('stream_id', sa.String(length=255), nullable=False),
        sa.Column('stream_url', sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column('highlights', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    # Create indexes
    op.create_index('idx_stream_id', 'stream_metadata', ['stream_id'])
    op.create_index('idx_stream_url', 'stream_metadata', ['stream_url'])
    

def downgrade() -> None:
    op.drop_table('stream_metadata', if_exists=True)