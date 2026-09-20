"""0003 · 素材 / 批注 / 体检 / 选题（M2 中枢）

docs/06-prototype-to-impl.md §5：新增 14 张表 + 13 个枚举。

Revision ID: 0003_materials
Revises: 0002_triggers
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_materials"
down_revision: str | None = "0002_triggers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
NOW = sa.text("now()")


def _e(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


MATERIAL_STATUS = _e("material_status", "active", "archived")
ANNOTATION_STATUS = _e(
    "annotation_status", "draft", "checking", "needs_revision", "passed", "blocked", "locked"
)
ANNOTATION_VERSION_SOURCE = _e("annotation_version_source", "manual", "ai_adopt", "import")
FACT_STATUS = _e("fact_status", "verified", "contradicted", "unverifiable", "outdated")
REPORT_VERDICT = _e("report_verdict", "passed", "needs_revision", "blocked")
FINDING_TRACK = _e("finding_track", "fact", "logic", "compliance", "tone", "uniqueness")
FINDING_SEVERITY = _e("finding_severity", "blocker", "high", "medium", "low", "info")
FINDING_STATUS = _e("finding_status", "open", "accepted", "dismissed", "ignored")
PROJECT_STATUS = _e(
    "project_status",
    "collecting",
    "reviewing",
    "ready",
    "composing",
    "drafting",
    "completed",
    "archived",
    "cancelled",
)
PROJECT_MATERIAL_ROLE = _e("project_material_role", "primary", "background")
PROMPT_CATEGORY = _e("prompt_category", "style", "structure", "persona", "taboo")
ARTICLE_STATUS = _e("article_status", "draft", "final", "published", "archived")
ARTICLE_VERSION_SOURCE = _e("article_version_source", "ai", "human")

ALL_ENUMS = [
    MATERIAL_STATUS,
    ANNOTATION_STATUS,
    ANNOTATION_VERSION_SOURCE,
    FACT_STATUS,
    REPORT_VERDICT,
    FINDING_TRACK,
    FINDING_SEVERITY,
    FINDING_STATUS,
    PROJECT_STATUS,
    PROJECT_MATERIAL_ROLE,
    PROMPT_CATEGORY,
    ARTICLE_STATUS,
    ARTICLE_VERSION_SOURCE,
]

TABLES_WITH_UPDATED_AT = [
    "topics",
    "materials",
    "annotations",
    "fact_cards",
    "review_reports",
    "review_findings",
    "projects",
    "prompt_templates",
    "articles",
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    # ---------------- 主题 ----------------
    op.create_table(
        "topics",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_topics_user_slug",
        "topics",
        ["user_id", "slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_topics_system_slug",
        "topics",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NULL"),
    )
    op.create_index("ix_topics_user", "topics", ["user_id"])

    # ---------------- 素材 ----------------
    op.create_table(
        "materials",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "news_item_id",
            UUID,
            sa.ForeignKey("news_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_date", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")
        ),
        sa.Column("score", sa.SmallInteger(), nullable=False, server_default="5"),
        sa.Column("status", MATERIAL_STATUS, nullable=False, server_default="active"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("score BETWEEN 1 AND 10", name="ck_materials_score_range"),
    )
    op.create_index(
        "uq_materials_user_news",
        "materials",
        ["user_id", "news_item_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_materials_user_date", "materials", ["user_id", "material_date"])
    op.create_index("ix_materials_user_score", "materials", ["user_id", "score"])
    op.create_index("ix_materials_news", "materials", ["news_item_id"])

    op.create_table(
        "material_topics",
        sa.Column(
            "material_id",
            UUID,
            sa.ForeignKey("materials.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "topic_id", UUID, sa.ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_material_topics_topic", "material_topics", ["topic_id", "created_at"])

    # ---------------- 点评 ----------------
    op.create_table(
        "annotations",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "material_id",
            UUID,
            sa.ForeignKey("materials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "news_item_id",
            UUID,
            sa.ForeignKey("news_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", ANNOTATION_STATUS, nullable=False, server_default="draft"),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("current_version_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_annotations_material",
        "annotations",
        ["material_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_annotations_user_status", "annotations", ["user_id", "status"])
    op.create_index("ix_annotations_news", "annotations", ["news_item_id"])

    op.create_table(
        "annotation_versions",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "annotation_id",
            UUID,
            sa.ForeignKey("annotations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("source", ANNOTATION_VERSION_SOURCE, nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("annotation_id", "version_no", name="uq_annotation_versions"),
    )
    op.create_index(
        "ix_annotation_versions_annotation", "annotation_versions", ["annotation_id", "version_no"]
    )

    # ---------------- 事实基线 ----------------
    op.create_table(
        "fact_cards",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "news_item_id",
            UUID,
            sa.ForeignKey("news_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("context_notes", sa.Text(), nullable=True),
        sa.Column(
            "related_symbols", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("open_questions", JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.Text(), nullable=False, server_default="ready"),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_fact_cards_news", "fact_cards", ["news_item_id"], unique=True)

    op.create_table(
        "fact_card_claims",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "card_id", UUID, sa.ForeignKey("fact_cards.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("status", FACT_STATUS, nullable=False, server_default="unverifiable"),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False, server_default="0.50"),
        sa.Column("evidence", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("card_id", "seq", name="uq_fact_card_claims"),
    )
    op.create_index("ix_fact_card_claims_card", "fact_card_claims", ["card_id", "seq"])

    # ---------------- 体检报告 ----------------
    op.create_table(
        "review_reports",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "annotation_id",
            UUID,
            sa.ForeignKey("annotations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("annotation_version_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "run_id", UUID, sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("verdict", REPORT_VERDICT, nullable=False, server_default="passed"),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("findings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_review_reports_annotation", "review_reports", ["annotation_id", "created_at"])
    op.create_index("ix_review_reports_user", "review_reports", ["user_id", "created_at"])

    op.create_table(
        "review_findings",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "report_id",
            UUID,
            sa.ForeignKey("review_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("track", FINDING_TRACK, nullable=False),
        sa.Column("severity", FINDING_SEVERITY, nullable=False),
        sa.Column("status", FINDING_STATUS, nullable=False, server_default="open"),
        sa.Column("span_start", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("span_end", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("evidence", JSONB, nullable=False, server_default="[]"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_review_findings_report", "review_findings", ["report_id", "severity"])
    op.create_index(
        "ix_review_findings_open",
        "review_findings",
        ["status"],
        postgresql_where=sa.text("status = 'open'"),
    )

    # ---------------- 选题 / 提示词 / 稿件 ----------------
    op.create_table(
        "projects",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", PROJECT_STATUS, nullable=False, server_default="collecting"),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("target_words", sa.Integer(), nullable=True),
        sa.Column("require_note", sa.Text(), nullable=True),
        sa.Column("prompt_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "compose_run_id", UUID, sa.ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_projects_user_status", "projects", ["user_id", "status"])
    op.create_index("ix_projects_user_updated", "projects", ["user_id", "updated_at"])

    op.create_table(
        "project_materials",
        sa.Column(
            "project_id", UUID, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "material_id", UUID, sa.ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("role", PROJECT_MATERIAL_ROLE, nullable=False, server_default="primary"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_project_materials_material", "project_materials", ["material_id"])

    op.create_table(
        "prompt_templates",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", PROMPT_CATEGORY, nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "variables", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("is_official", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_prompt_templates_user_name_ver",
        "prompt_templates",
        ["user_id", "name", "version_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_prompt_templates_system_name_ver",
        "prompt_templates",
        ["name", "version_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND user_id IS NULL"),
    )
    op.create_index("ix_prompt_templates_category", "prompt_templates", ["category"])

    op.create_table(
        "articles",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "project_id", UUID, sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", ARTICLE_STATUS, nullable=False, server_default="draft"),
        sa.Column("current_version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_articles_user_status", "articles", ["user_id", "status"])

    op.create_table(
        "article_versions",
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "article_id", UUID, sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("citation_map", JSONB, nullable=False, server_default="{}"),
        sa.Column("source", ARTICLE_VERSION_SOURCE, nullable=False, server_default="ai"),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("article_id", "version_no", name="uq_article_versions"),
    )
    op.create_index("ix_article_versions_article", "article_versions", ["article_id", "version_no"])

    # ---------------- updated_at 触发器（续 0002 的清单） ----------------
    for table in TABLES_WITH_UPDATED_AT:
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};
            CREATE TRIGGER trg_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at();
            """
        )

    # ---------------- 官方提示词种子（原型「官方模板库」） ----------------
    op.execute(
        """
        INSERT INTO prompt_templates (user_id, name, category, version_no, description, body,
                                      variables, is_official)
        VALUES
          (NULL, '公众号深度复盘体', 'style', 4, '长句 + 数据锚 + 段落推进，结尾给观察指标。',
           '你是{作者名}的主笔。要求：1) 每段以可验证事实开头，再接观点；2) 禁止套话；3) 结尾给 2-3 个可跟踪指标。',
           ARRAY['作者名','字数','读者对象'], true),
          (NULL, '雪球短评体', 'style', 2, '短段落、口语化、强调「我的分歧点」。',
           '用{作者名}在雪球的口吻写短评：1) 开篇一句话给结论；2) 每段不超过 120 字；3) 写出与市场的分歧。',
           ARRAY['作者名'], true),
          (NULL, '观点先行结构', 'structure', 3, '结论 → 论据 → 反方 → 回应 → 边界条件。',
           '结构固定为：① 结论（一句话）② 关键论据（2-3 条，带事实）③ 反方观点 ④ 对反方的回应 ⑤ 结论成立的边界条件。',
           ARRAY[]::text[], true),
          (NULL, '合规禁忌清单', 'taboo', 5, '红线词与表述约束，写作前强制加载。',
           '禁止输出：任何买卖建议/目标价/收益承诺；未证实的指控；绝对化断言（必然、一定、唯一、所有）；对他方的贬损性定性。',
           ARRAY[]::text[], true)
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    for table in reversed(TABLES_WITH_UPDATED_AT):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")

    op.drop_table("article_versions")
    op.drop_table("articles")
    op.drop_table("prompt_templates")
    op.drop_table("project_materials")
    op.drop_table("projects")
    op.drop_table("review_findings")
    op.drop_table("review_reports")
    op.drop_table("fact_card_claims")
    op.drop_table("fact_cards")
    op.drop_table("annotation_versions")
    op.drop_table("annotations")
    op.drop_table("material_topics")
    op.drop_table("materials")
    op.drop_table("topics")

    bind = op.get_bind()
    for enum in reversed(ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
