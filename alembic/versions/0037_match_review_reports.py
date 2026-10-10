"""Private videos, versioned match reports and export jobs."""
import sqlalchemy as sa
from alembic import op

revision = "0037_match_review_reports"
down_revision = "0036_substitution_reason"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "review_videos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_videos_tenant_id", "review_videos", ["tenant_id"])
    op.create_table(
        "match_review_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("video_id", sa.String(36), sa.ForeignKey("review_videos.id"), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("document_json", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reviewed_by", sa.String(36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_match_review_reports_tenant_id", "match_review_reports", ["tenant_id"])
    op.create_table(
        "review_exports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("match_review_reports.id"), nullable=False),
        sa.Column("report_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_exports_tenant_id", "review_exports", ["tenant_id"])
    op.create_index("uq_review_exports_active_tenant", "review_exports", ["tenant_id"], unique=True,
                    sqlite_where=sa.text("state IN ('queued', 'running')"),
                    postgresql_where=sa.text("state IN ('queued', 'running')"))


def downgrade():
    op.drop_table("review_exports")
    op.drop_table("match_review_reports")
    op.drop_table("review_videos")
