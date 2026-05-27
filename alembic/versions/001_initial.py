"""Initial migration - create jobs, scenes, and scene_variants tables.

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('telegram_user_id', sa.Integer(), nullable=False),
        sa.Column('telegram_chat_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, default='briefing_received'),
        sa.Column('mode', sa.String(20), nullable=False, default='brief'),
        sa.Column('briefing', sa.Text(), nullable=False, default=''),
        sa.Column('title', sa.String(255), nullable=True),
        sa.Column('total_duration_sec', sa.Float(), nullable=False, default=0.0),
        sa.Column('aspect_ratio', sa.String(10), nullable=False, default='9:16'),
        sa.Column('character_key', sa.String(100), nullable=False, default='markus_industrial'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
    )

    op.create_table(
        'scenes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order', sa.Integer(), nullable=False),
        sa.Column('duration_sec', sa.Float(), nullable=False, default=5.0),
        sa.Column('location_key', sa.String(100), nullable=False),
        sa.Column('location_prompt', sa.Text(), nullable=False, default=''),
        sa.Column('camera_key', sa.String(100), nullable=False),
        sa.Column('action_key', sa.String(100), nullable=False),
        sa.Column('still_image_source', sa.String(20), nullable=False, default='library'),
        sa.Column('still_image_path', sa.String(500), nullable=True),
        sa.Column('voiceover_de', sa.Text(), nullable=False, default=''),
        sa.Column('needs_lipsync', sa.Boolean(), nullable=False, default=True),
        sa.Column('caption_overlay', sa.String(255), nullable=True),
        sa.Column('caption_position', sa.String(20), nullable=False, default='top'),
        sa.Column('variant_count', sa.Integer(), nullable=False, default=3),
        sa.Column('seed', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, default='pending'),
        sa.Column('selected_variant_idx', sa.Integer(), nullable=True),
    )

    op.create_table(
        'scene_variants',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('scene_id', sa.Integer(), sa.ForeignKey('scenes.id', ondelete='CASCADE'), nullable=False),
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('video_path', sa.String(500), nullable=False),
        sa.Column('thumbnail_path', sa.String(500), nullable=True),
        sa.Column('seed', sa.Integer(), nullable=False),
        sa.Column('duration_sec', sa.Float(), nullable=False),
    )

    # Create indexes
    op.create_index('ix_jobs_telegram_user_id', 'jobs', ['telegram_user_id'])
    op.create_index('ix_jobs_status', 'jobs', ['status'])
    op.create_index('ix_scenes_job_id', 'scenes', ['job_id'])
    op.create_index('ix_scene_variants_scene_id', 'scene_variants', ['scene_id'])


def downgrade() -> None:
    op.drop_index('ix_scene_variants_scene_id', 'scene_variants')
    op.drop_index('ix_scenes_job_id', 'scenes')
    op.drop_index('ix_jobs_status', 'jobs')
    op.drop_index('ix_jobs_telegram_user_id', 'jobs')
    op.drop_table('scene_variants')
    op.drop_table('scenes')
    op.drop_table('jobs')
