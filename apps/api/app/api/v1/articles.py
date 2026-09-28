"""稿件库（M3）。

M3 的交付不只是"能写出来"，还要能**回看与追溯** —— 这是这个产品与
普通 AI 写作工具的核心区别：用户要能回答"这句话的依据是什么"。

`citation_map` 承载「段落 → 素材/证据」映射，`article_versions` 保留每次改动。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, get_session
from app.models.project import Article, ArticleVersion

router = APIRouter(prefix="/articles", tags=["articles"])


async def _version_of(session: AsyncSession, article: Article) -> ArticleVersion | None:
    return (
        await session.execute(
            select(ArticleVersion)
            .where(ArticleVersion.article_id == article.id)
            .order_by(ArticleVersion.version_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


@router.get("")
async def list_articles(
    project_id: uuid.UUID | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    """稿件列表。可按选题过滤。"""
    stmt = (
        select(Article)
        .where(Article.user_id == user_id, Article.deleted_at.is_(None))
        .order_by(Article.created_at.desc())
        .limit(limit)
    )
    if project_id is not None:
        stmt = stmt.where(Article.project_id == project_id)
    articles = list((await session.execute(stmt)).scalars().all())

    out: list[dict] = []
    for a in articles:
        v = await _version_of(session, a)
        out.append(
            {
                "id": a.id,
                "title": a.title,
                "status": a.status.value,
                "project_id": a.project_id,
                "platform": a.platform,
                "current_version_no": a.current_version_no,
                "word_count": v.word_count if v else 0,
                "created_at": a.created_at,
                "updated_at": a.updated_at,
            }
        )
    return out


@router.get("/{article_id}")
async def get_article(
    article_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """稿件详情：正文 + 可追溯映射 + 版本列表。"""
    article = await session.get(Article, article_id)
    if article is None or article.user_id != user_id or article.deleted_at is not None:
        raise HTTPException(status_code=404, detail="article not found")

    version = await _version_of(session, article)
    versions = list(
        (
            await session.execute(
                select(ArticleVersion)
                .where(ArticleVersion.article_id == article.id)
                .order_by(ArticleVersion.version_no.desc())
            )
        ).scalars().all()
    )

    return {
        "id": article.id,
        "title": article.title,
        "status": article.status.value,
        "project_id": article.project_id,
        "platform": article.platform,
        "content": version.content if version else "",
        "word_count": version.word_count if version else 0,
        # ★ 段落 → 素材/证据 的映射，前端据此做「这句话的依据」追溯
        "citation_map": version.citation_map if version else {},
        "versions": [
            {
                "version_no": v.version_no,
                "title": v.title,
                "word_count": v.word_count,
                "source": v.source.value,
                "created_at": v.created_at,
            }
            for v in versions
        ],
    }


@router.get("/{article_id}/versions/{version_no}")
async def get_article_version(
    article_id: uuid.UUID,
    version_no: int,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """取指定版本（用于版本对比 / 回滚预览）。"""
    article = await session.get(Article, article_id)
    if article is None or article.user_id != user_id:
        raise HTTPException(status_code=404, detail="article not found")
    v = (
        await session.execute(
            select(ArticleVersion).where(
                ArticleVersion.article_id == article_id,
                ArticleVersion.version_no == version_no,
            )
        )
    ).scalar_one_or_none()
    if v is None:
        raise HTTPException(status_code=404, detail="version not found")
    return {
        "version_no": v.version_no,
        "title": v.title,
        "content": v.content,
        "citation_map": v.citation_map,
        "word_count": v.word_count,
        "source": v.source.value,
        "created_at": v.created_at,
    }


__all__ = ["router"]
