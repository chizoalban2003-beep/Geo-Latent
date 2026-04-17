"""
alembic/versions/001_baseline.py
Baseline migration — all tables from persistence_db.py captured here.

Usage:
    alembic upgrade head      # create all tables
    alembic downgrade base    # drop all tables
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id",         sa.Text,            primary_key=True),
        sa.Column("name",       sa.Text,            nullable=False),
        sa.Column("created_at", sa.Float,           nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
    )
    op.create_table(
        "principals",
        sa.Column("id",         sa.Text,            primary_key=True),
        sa.Column("tenant_id",  sa.Text,            sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email",      sa.Text,            nullable=False),
        sa.Column("role",       sa.Text,            nullable=False, server_default="viewer"),
        sa.Column("pw_hash",    sa.Text),
        sa.Column("created_at", sa.Float,           nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
        sa.UniqueConstraint("tenant_id", "email"),
    )
    op.create_table(
        "invitations",
        sa.Column("token",      sa.Text,            primary_key=True),
        sa.Column("tenant_id",  sa.Text,            nullable=False),
        sa.Column("email",      sa.Text,            nullable=False),
        sa.Column("role",       sa.Text,            nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.Float,           nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
        sa.Column("accepted",   sa.Boolean,         nullable=False, server_default="false"),
    )
    op.create_table(
        "projects",
        sa.Column("id",          sa.Text,           primary_key=True),
        sa.Column("tenant_id",   sa.Text,           nullable=False),
        sa.Column("name",        sa.Text,           nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("shared_with", postgresql.JSONB,  nullable=False, server_default="[]"),
        sa.Column("created_at",  sa.Float,          nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
    )
    op.create_table(
        "datasets",
        sa.Column("id",         sa.Text,            primary_key=True),
        sa.Column("tenant_id",  sa.Text,            nullable=False),
        sa.Column("filename",   sa.Text,            nullable=False),
        sa.Column("size_bytes", sa.Integer,         nullable=False),
        sa.Column("sha256",     sa.Text,            nullable=False),
        sa.Column("created_at", sa.Float,           nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
    )
    op.create_table(
        "runs",
        sa.Column("id",          sa.Text,           primary_key=True),
        sa.Column("tenant_id",   sa.Text,           nullable=False),
        sa.Column("project_id",  sa.Text),
        sa.Column("scenario",    sa.Text),
        sa.Column("dataset_id",  sa.Text),
        sa.Column("steps",       sa.Integer),
        sa.Column("status",      sa.Text,           nullable=False, server_default="pending"),
        sa.Column("result",      postgresql.JSONB),
        sa.Column("created_at",  sa.Float,          nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
        sa.Column("finished_at", sa.Float),
    )
    op.create_table(
        "simulation_frames",
        sa.Column("id",        sa.BigInteger,       primary_key=True, autoincrement=True),
        sa.Column("run_id",    sa.Text,             nullable=False),
        sa.Column("tenant_id", sa.Text,             nullable=False),
        sa.Column("step",      sa.Integer,          nullable=False),
        sa.Column("frame",     postgresql.JSONB,    nullable=False),
        sa.Column("ts",        sa.Float,            nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
    )
    op.create_index("idx_frames_run",    "simulation_frames", ["run_id", "step"])
    op.create_table(
        "audit_log",
        sa.Column("id",        sa.BigInteger,       primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Text,             nullable=False),
        sa.Column("actor_id",  sa.Text),
        sa.Column("action",    sa.Text,             nullable=False),
        sa.Column("resource",  sa.Text),
        sa.Column("detail",    postgresql.JSONB),
        sa.Column("ts",        sa.Float,            nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
    )
    op.create_index("idx_audit_tenant", "audit_log", ["tenant_id", sa.text("ts DESC")])
    op.create_table(
        "immortal_cells",
        sa.Column("id",          sa.Text,           primary_key=True),
        sa.Column("tenant_id",   sa.Text,           nullable=False),
        sa.Column("run_id",      sa.Text,           nullable=False),
        sa.Column("grid_x",      sa.Integer,        nullable=False),
        sa.Column("grid_y",      sa.Integer,        nullable=False),
        sa.Column("first_seen",  sa.Integer,        nullable=False),
        sa.Column("tick_count",  sa.Integer,        nullable=False, server_default="1"),
        sa.Column("density",     sa.Float),
        sa.Column("biome_label", sa.Text),
        sa.Column("etched_at",   sa.Float,          nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
    )
    op.create_index("idx_cells_tenant", "immortal_cells", ["tenant_id", "run_id"])
    op.create_table(
        "billing_usage",
        sa.Column("id",        sa.BigInteger,       primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Text,             nullable=False),
        sa.Column("metric",    sa.Text,             nullable=False),
        sa.Column("quantity",  sa.Float,            nullable=False),
        sa.Column("ts",        sa.Float,            nullable=False, server_default=sa.text("EXTRACT(EPOCH FROM NOW())")),
    )
    op.create_index("idx_billing_t", "billing_usage", ["tenant_id", sa.text("ts DESC")])


def downgrade() -> None:
    for tbl in [
        "billing_usage", "immortal_cells", "audit_log",
        "simulation_frames", "runs", "datasets",
        "projects", "invitations", "principals", "tenants",
    ]:
        op.drop_table(tbl)
