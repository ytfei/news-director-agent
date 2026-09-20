"""PG ENUM 对应的 Python 枚举。名称必须与 05-database-schema.md §3.0 一致。"""

from __future__ import annotations

import enum


class ConnectorType(str, enum.Enum):
    tushare = "tushare"
    rss = "rss"
    wechat_mp = "wechat_mp"
    weibo = "weibo"
    xueqiu = "xueqiu"
    exchange = "exchange"
    news_site = "news_site"
    custom_api = "custom_api"
    manual = "manual"


class ConnectorStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    error = "error"
    disabled = "disabled"


class SyncStatus(str, enum.Enum):
    running = "running"
    success = "success"
    partial = "partial"
    failed = "failed"


class ContentType(str, enum.Enum):
    flash = "flash"
    article = "article"
    announcement = "announcement"
    policy = "policy"
    research_report = "research_report"
    interactive_qa = "interactive_qa"
    social_post = "social_post"
    market_data = "market_data"


class ClusterStatus(str, enum.Enum):
    open = "open"
    merged = "merged"
    closed = "closed"


class ActionType(str, enum.Enum):
    read = "read"
    star = "star"
    unstar = "unstar"
    rate = "rate"
    hide = "hide"
    block_source = "block_source"


class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    waiting_human = "waiting_human"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class RunGraph(str, enum.Enum):
    ingest = "ingest"
    review = "review"
    compose = "compose"
    research = "research"
    enrich = "enrich"


class EnrichStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


# ---------- 以下为「素材 / 批注 / 体检 / 选题」链路（docs/06） ----------


class MaterialStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class AnnotationStatus(str, enum.Enum):
    draft = "draft"
    checking = "checking"
    needs_revision = "needs_revision"
    passed = "passed"
    blocked = "blocked"
    locked = "locked"


class AnnotationVersionSource(str, enum.Enum):
    manual = "manual"
    ai_adopt = "ai_adopt"
    import_ = "import"


class FactStatus(str, enum.Enum):
    verified = "verified"
    contradicted = "contradicted"
    unverifiable = "unverifiable"
    outdated = "outdated"


class ReportVerdict(str, enum.Enum):
    passed = "passed"
    needs_revision = "needs_revision"
    blocked = "blocked"


class FindingTrack(str, enum.Enum):
    fact = "fact"
    logic = "logic"
    compliance = "compliance"
    tone = "tone"
    uniqueness = "uniqueness"


class FindingSeverity(str, enum.Enum):
    blocker = "blocker"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class FindingStatus(str, enum.Enum):
    open = "open"
    accepted = "accepted"
    dismissed = "dismissed"
    ignored = "ignored"


class ProjectStatus(str, enum.Enum):
    collecting = "collecting"
    reviewing = "reviewing"
    ready = "ready"
    composing = "composing"
    drafting = "drafting"
    completed = "completed"
    archived = "archived"
    cancelled = "cancelled"


class ProjectMaterialRole(str, enum.Enum):
    primary = "primary"
    background = "background"


class PromptCategory(str, enum.Enum):
    style = "style"
    structure = "structure"
    persona = "persona"
    taboo = "taboo"


class ArticleStatus(str, enum.Enum):
    draft = "draft"
    final = "final"
    published = "published"
    archived = "archived"


class ArticleVersionSource(str, enum.Enum):
    ai = "ai"
    human = "human"


def sa_enum(py_enum: type[enum.Enum], name: str):
    """创建指向 PG 原生 ENUM 类型的 SQLAlchemy Enum。"""
    from sqlalchemy import Enum

    return Enum(
        py_enum,
        name=name,
        native_enum=True,
        values_callable=lambda e: [m.value for m in e],
    )
