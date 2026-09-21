"""模型汇总导入。

Alembic 的 `target_metadata` 依赖这些导入；新增模型文件时在这里登记，
否则 `alembic revision --autogenerate` 会漏表。
"""

from app.models.agent import AgentRun, AgentStep, Notification, UsageRecord
from app.models.base import Base
from app.models.ingest import RawDocument, SourceConnector, SyncRun
from app.models.market import MarketFact
from app.models.material import Annotation, AnnotationVersion, Material, MaterialTopic, Topic
from app.models.news import (
    NewsCluster,
    NewsItem,
    NewsItemRelation,
    NewsItemSymbol,
    NewsItemTag,
    Tag,
)
from app.models.project import (
    Article,
    ArticleVersion,
    Project,
    ProjectMaterial,
    PromptTemplate,
)
from app.models.review import FactCard, FactCardClaim, ReviewFinding, ReviewReport
from app.models.user import User, UserInterest, UserNewsAction

__all__ = [
    "Base",
    "User",
    "UserInterest",
    "UserNewsAction",
    "SourceConnector",
    "SyncRun",
    "RawDocument",
    "Tag",
    "NewsCluster",
    "NewsItem",
    "NewsItemTag",
    "NewsItemSymbol",
    "NewsItemRelation",
    "AgentRun",
    "AgentStep",
    "UsageRecord",
    "Notification",
    "MarketFact",
    "Topic",
    "Material",
    "MaterialTopic",
    "Annotation",
    "AnnotationVersion",
    "FactCard",
    "FactCardClaim",
    "ReviewReport",
    "ReviewFinding",
    "Project",
    "ProjectMaterial",
    "PromptTemplate",
    "Article",
    "ArticleVersion",
]
