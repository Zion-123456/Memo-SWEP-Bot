"""initial

Revision ID: 0001
Revises:
Create Date: 2026-08-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums ---
    source_type_enum = sa.Enum('telegram', 'api', name='source_type_enum')
    source_type_enum.create(op.get_bind())

    event_status_enum = sa.Enum('draft', 'processed', 'exported', name='event_status_enum')
    event_status_enum.create(op.get_bind())

    file_type_enum = sa.Enum('photo', 'document', 'audio', 'video', 'voice', name='file_type_enum')
    file_type_enum.create(op.get_bind())

    # --- Users ---
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('first_name', sa.String(length=255), nullable=False),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('university', sa.String(length=500), nullable=False),
        sa.Column('department', sa.String(length=500), nullable=False),
        sa.Column('programme', sa.String(length=500), nullable=False),
        sa.Column('company', sa.String(length=500), nullable=False),
        sa.Column('supervisor', sa.String(length=500), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('telegram_id', name='uq_users_telegram_id')
    )
    op.create_index(op.f('ix_users_telegram_id'), 'users', ['telegram_id'], unique=False)

    # --- Conversations ---
    op.create_table(
        'conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('state', sa.String(length=100), nullable=False, comment='Current ConversationHandler state name for observability.'),
        sa.Column('last_message_id', sa.Integer(), nullable=True, comment='Telegram message_id of the most recent bot reply.'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_conversations_user_id')
    )

    # --- Events ---
    op.create_table(
        'events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('source_type', postgresql.ENUM('telegram', 'api', name='source_type_enum', create_type=False), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('status', postgresql.ENUM('draft', 'processed', 'exported', name='event_status_enum', create_type=False), server_default='draft', nullable=False),
        sa.Column('payload_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Schema-less metadata for AI-extracted fields (Sprint 2+).'),

        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_events_user_id'), 'events', ['user_id'], unique=False)

    # --- Attachments ---
    op.create_table(
        'attachments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_type', postgresql.ENUM('photo', 'document', 'audio', 'video', 'voice', name='file_type_enum', create_type=False), nullable=False),
        sa.Column('telegram_file_id', sa.String(length=512), nullable=False),
        sa.Column('storage_url', sa.Text(), nullable=True, comment='Cloud storage URL, populated by Sprint 2 upload pipeline.'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_attachments_event_id'), 'attachments', ['event_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_attachments_event_id'), table_name='attachments')
    op.drop_table('attachments')
    op.drop_index(op.f('ix_events_user_id'), table_name='events')
    op.drop_table('events')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_users_telegram_id'), table_name='users')
    op.drop_table('users')

    sa.Enum(name='file_type_enum').drop(op.get_bind())
    sa.Enum(name='event_status_enum').drop(op.get_bind())
    sa.Enum(name='source_type_enum').drop(op.get_bind())
