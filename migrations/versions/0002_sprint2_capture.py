"""sprint2_capture

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enums
    payload_type_enum = sa.Enum('text', 'voice', 'photo', 'document', 'multimodal', name='payload_type_enum')
    payload_type_enum.create(op.get_bind())

    # PostgreSQL enum alter for processing_status
    op.execute("ALTER TYPE event_status_enum RENAME TO processing_status_enum")
    op.execute("ALTER TYPE processing_status_enum ADD VALUE IF NOT EXISTS 'pending'")
    op.execute("ALTER TYPE processing_status_enum ADD VALUE IF NOT EXISTS 'failed'")

    # 2. Alter events table
    op.add_column('events', sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('events', sa.Column('payload_type', postgresql.ENUM('text', 'voice', 'photo', 'document', 'multimodal', name='payload_type_enum', create_type=False), server_default='text', nullable=False))
    op.add_column('events', sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False))
    op.create_index(op.f('ix_events_event_date'), 'events', ['event_date'], unique=False)

    # 3. Alter attachments table
    op.add_column('attachments', sa.Column('original_filename', sa.String(length=512), nullable=True))
    op.add_column('attachments', sa.Column('mime_type', sa.String(length=255), nullable=True))
    op.add_column('attachments', sa.Column('file_size', sa.BigInteger(), nullable=True))
    op.add_column('attachments', sa.Column('duration_seconds', sa.Integer(), nullable=True))
    op.add_column('attachments', sa.Column('width', sa.Integer(), nullable=True))
    op.add_column('attachments', sa.Column('height', sa.Integer(), nullable=True))
    op.add_column('attachments', sa.Column('checksum', sa.String(length=64), nullable=True))
    op.add_column('attachments', sa.Column('downloaded_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('attachments', 'downloaded_at')
    op.drop_column('attachments', 'checksum')
    op.drop_column('attachments', 'height')
    op.drop_column('attachments', 'width')
    op.drop_column('attachments', 'duration_seconds')
    op.drop_column('attachments', 'file_size')
    op.drop_column('attachments', 'mime_type')
    op.drop_column('attachments', 'original_filename')

    op.drop_index(op.f('ix_events_event_date'), table_name='events')
    op.drop_column('events', 'is_deleted')
    op.drop_column('events', 'payload_type')
    op.drop_column('events', 'captured_at')

    sa.Enum(name='payload_type_enum').drop(op.get_bind())
    op.execute("ALTER TYPE processing_status_enum RENAME TO event_status_enum")
