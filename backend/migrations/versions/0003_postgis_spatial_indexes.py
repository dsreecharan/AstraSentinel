"""Add generated and indexed world geometries in the optional PostGIS store."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("""
        ALTER TABLE incidents ADD COLUMN world_geom geometry(Point, 4326)
        GENERATED ALWAYS AS (
            CASE WHEN geo_status = 'calibrated' THEN ST_SetSRID(ST_GeomFromGeoJSON(location), 4326) END
        ) STORED
    """)
    op.execute("""
        ALTER TABLE geofences ADD COLUMN world_geom geometry(Polygon, 4326)
        GENERATED ALWAYS AS (
            CASE WHEN space_type = 'world' THEN ST_SetSRID(ST_GeomFromGeoJSON(geometry), 4326) END
        ) STORED
    """)
    for table in ("incidents", "geofences"):
        op.execute(f"CREATE INDEX ix_{table}_world_geom ON {table} USING gist (world_geom) WHERE world_geom IS NOT NULL")


def downgrade():
    if op.get_context().dialect.name == "postgresql":
        for table in ("incidents", "geofences"):
            op.drop_index(f"ix_{table}_world_geom", table_name=table)
            op.drop_column(table, "world_geom")
