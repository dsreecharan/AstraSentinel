"""initial SQLite schema

Revision ID: 0001
"""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sources',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('video_path', sa.Text(), nullable=False),
        sa.Column('video_sha256', sa.String(), nullable=False),
        sa.Column('rights_note', sa.Text(), nullable=False),
        sa.Column('attribution', sa.Text(), nullable=False),
        sa.Column('license_url', sa.Text(), nullable=True),
        sa.Column('geo_mode', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('video_sha256'),
    )
    op.create_table(
        'calibrations',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False),
        sa.Column('method', sa.String(), nullable=False),
        sa.Column('frame_size_px', sa.JSON(), nullable=False),
        sa.Column('pixel_points', sa.JSON(), nullable=False),
        sa.Column('geo_points', sa.JSON(), nullable=False),
        sa.Column('reprojection_error_px', sa.Float(), nullable=False),
        sa.Column('valid_for_frame_range', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_calibrations_source_id', 'calibrations', ['source_id'], unique=False)

    op.create_table(
        'geofences',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('space_type', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('geometry', sa.JSON(), nullable=False),
        sa.Column('frame_size_px', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("space_type IN ('world', 'image')", name='ck_geofences_space'),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_geofences_source_id', 'geofences', ['source_id'], unique=False)

    op.create_table(
        'runs',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False),
        sa.Column('mode', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('stopped_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('model', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id', 'source_id', name='uq_runs_id_source'),
    )
    op.create_index('ix_runs_source_created', 'runs', ['source_id', 'created_at'], unique=False)

    op.create_table(
        'incidents',
        sa.Column('id', sa.Text(), nullable=False),
        sa.Column('idempotency_key', sa.Text(), nullable=False),
        sa.Column('run_id', sa.Text(), nullable=False),
        sa.Column('source_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('rule_name', sa.String(), nullable=False),
        sa.Column('rule_details', sa.JSON(), nullable=False),
        sa.Column('video_time_ms', sa.Integer(), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=True),
        sa.Column('location', sa.JSON(none_as_null=True), nullable=True),
        sa.Column('geo_status', sa.String(), nullable=False),
        sa.Column('horizontal_error_m', sa.Float(), nullable=True),
        sa.Column('evidence_path', sa.Text(), nullable=True),
        sa.Column('review_status', sa.String(), nullable=False),
        sa.Column('reviewer', sa.String(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("(review_status = 'pending' AND reviewer IS NULL AND reviewed_at IS NULL) OR (review_status IN ('acknowledged', 'dismissed') AND reviewer IS NOT NULL AND reviewed_at IS NOT NULL)", name='ck_incidents_review'),
        sa.CheckConstraint('video_time_ms >= 0', name='ck_incidents_video_time'),
        sa.ForeignKeyConstraint(['run_id', 'source_id'], ['runs.id', 'runs.source_id'], name='fk_incidents_run_source'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index('ix_incidents_created_id', 'incidents', ['created_at', 'id'], unique=False)
    op.create_index('ix_incidents_review_created_id', 'incidents', ['review_status', 'created_at', 'id'], unique=False)
    op.create_index('ix_incidents_run_created_id', 'incidents', ['run_id', 'created_at', 'id'], unique=False)

    op.create_table(
        'audit_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Text(), nullable=False),
        sa.Column('actor', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.CheckConstraint("(action = 'created' AND actor = 'system' AND reason IS NULL) OR (action IN ('acknowledged', 'dismissed') AND length(coalesce(reason, '')) BETWEEN 1 AND 500)", name='ck_audit_entries_action'),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id', 'action', name='uq_audit_entries_incident_action'),
    )
    op.create_index('ix_audit_entries_incident_id', 'audit_entries', ['incident_id', 'id'], unique=False)
    op.create_index(
        'uq_audit_entries_review', 'audit_entries', ['incident_id'], unique=True,
        sqlite_where=sa.text("action <> 'created'"), postgresql_where=sa.text("action <> 'created'"),
    )
    if op.get_context().dialect.name == "postgresql":
        op.execute("""
            CREATE FUNCTION astra_reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'audit entries are append-only' USING ERRCODE = '23000';
            END;
            $$
        """)
        op.execute("""
            CREATE TRIGGER audit_entries_no_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_entries
            FOR EACH STATEMENT EXECUTE FUNCTION astra_reject_audit_mutation()
        """)
        return
    for action in ("UPDATE", "DELETE"):
        op.execute(f'''
            CREATE TRIGGER audit_entries_no_{action.lower()}
            BEFORE {action} ON audit_entries
            BEGIN
                SELECT RAISE(ABORT, 'audit entries are append-only');
            END
        ''')


def downgrade():
    op.drop_table("audit_entries")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP FUNCTION astra_reject_audit_mutation()")
    op.drop_table("incidents")
    op.drop_table("runs")
    op.drop_table("geofences")
    op.drop_table("calibrations")
    op.drop_table("sources")
