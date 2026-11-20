"""Store optional bounded incident thumbnails."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("evidence_jpeg", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("incidents", "evidence_jpeg")
