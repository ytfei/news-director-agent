"""选题 API。

★ docs/06 §1 R4/R8：选题聚合的是**素材**；点评不是写作前置条件。
写作权的判定统一走 `ProjectService.assess`，前端只消费结论。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, ensure_user, get_session
from app.models.agent import AgentRun
from app.models.enums import ProjectStatus, RunGraph, RunStatus
from app.repositories.project_repo import ProjectRepository, PromptRepository
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectIn(BaseModel):
    title: str = ""
    platform: str | None = None
    target_words: int | None = None
    require_note: str | None = None
    prompt_ids: list[uuid.UUID] = Field(default_factory=list)
    material_ids: list[uuid.UUID] = Field(default_factory=list)


class ProjectPatch(BaseModel):
    title: str | None = None
    platform: str | None = None
    target_words: int | None = None
    require_note: str | None = None
    prompt_ids: list[uuid.UUID] | None = None
    status: ProjectStatus | None = None


class MaterialIdsIn(BaseModel):
    material_ids: list[uuid.UUID] = Field(default_factory=list)


@router.get("")
async def list_projects(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    repo = ProjectRepository(session)
    projects = await repo.list_for_user(user_id)
    service = ProjectService(session)
    assess = await service.bulk_assess([p.id for p in projects])
    return [
        {
            "id": p.id,
            "title": p.title,
            "status": p.status.value,
            "platform": p.platform,
            "target_words": p.target_words,
            "updated_at": p.updated_at,
            "assessment": assess.get(p.id, {}),
        }
        for p in projects
    ]


@router.post("", status_code=201)
async def create_project(
    payload: ProjectIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    await ensure_user(session, user_id)
    project = await ProjectRepository(session).create(
        user_id,
        title=payload.title,
        platform=payload.platform,
        target_words=payload.target_words,
        require_note=payload.require_note,
        prompt_ids=[str(x) for x in payload.prompt_ids],
        material_ids=payload.material_ids,
    )
    await ProjectService(session).sync_status(project)
    await session.commit()
    return await ProjectService(session).detail(project)


@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    project = await ProjectRepository(session).get(project_id, user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return await ProjectService(session).detail(project)


@router.patch("/{project_id}")
async def patch_project(
    project_id: uuid.UUID,
    payload: ProjectPatch,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    repo = ProjectRepository(session)
    project = await repo.get(project_id, user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    fields = payload.model_dump(exclude_unset=True)
    if "prompt_ids" in fields and fields["prompt_ids"] is not None:
        fields["prompt_ids"] = [str(x) for x in fields["prompt_ids"]]
    await repo.update(project, fields)
    await session.commit()
    return await ProjectService(session).detail(project)


@router.post("/{project_id}/materials")
async def add_materials(
    project_id: uuid.UUID,
    payload: MaterialIdsIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    repo = ProjectRepository(session)
    project = await repo.get(project_id, user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    added = await repo.add_materials(project_id, payload.material_ids)
    service = ProjectService(session)
    await service.sync_status(project)
    await session.commit()
    detail = await service.detail(project)
    detail["added"] = added
    return detail


@router.delete("/{project_id}/materials/{material_id}", status_code=204)
async def remove_material(
    project_id: uuid.UUID,
    material_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> None:
    repo = ProjectRepository(session)
    project = await repo.get(project_id, user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    await repo.remove_material(project_id, material_id)
    await ProjectService(session).sync_status(project)
    await session.commit()


@router.post("/{project_id}/compose", status_code=202)
async def compose_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """触发写作。

    M2/M3 交界处：此处只做**准入校验**并创建 run（queued）。
    实际编排由 WriterAgent（LangGraph compose_graph）接管，SSE 推送进度。
    """
    repo = ProjectRepository(session)
    project = await repo.get(project_id, user_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")

    service = ProjectService(session)
    assessment = await service.assess(project.id)
    if not assessment["writable"]:
        raise HTTPException(status_code=409, detail="; ".join(assessment["blocking_reasons"]))

    # ★ JSONB 落库前必须 str()：UUID 不是 JSON 可序列化类型，
    #   否则会在 flush 时抛 StatementError（且只在真正触发写作时才暴露）
    material_ids = [
        str(m["id"]) for m in await service.materials_with_context(project.id)
    ]
    run = AgentRun(
        user_id=user_id,
        graph=RunGraph.compose,
        status=RunStatus.queued,
        thread_id=str(uuid.uuid4()),
        input={
            "project_id": str(project.id),
            "material_ids": material_ids,
            "mode": assessment["mode"],
            "prompt_ids": [str(x) for x in (project.prompt_ids or [])],
        },
    )
    session.add(run)
    await session.flush()
    project.compose_run_id = run.id
    project.status = ProjectStatus.composing
    await session.commit()

    return {
        "run_id": run.id,
        "status": run.status.value,
        "mode": assessment["mode"],
        "note": "compose_graph 尚未接入：当前只完成准入校验与 run 建档" if assessment["mode"] == "digest"
        else "已入队，等待 compose_graph 接管",
    }


# ---------------- 提示词 ----------------


prompts_router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptIn(BaseModel):
    name: str
    category: str
    body: str
    description: str | None = None
    variables: list[str] = Field(default_factory=list)


@prompts_router.get("")
async def list_prompts(
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> list[dict]:
    rows = await PromptRepository(session).list_for_user(user_id)
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category.value,
            "version_no": p.version_no,
            "description": p.description,
            "body": p.body,
            "variables": p.variables or [],
            "is_official": p.is_official,
        }
        for p in rows
    ]


@prompts_router.post("", status_code=201)
async def create_prompt(
    payload: PromptIn,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    await ensure_user(session, user_id)
    if payload.category not in {"style", "structure", "persona", "taboo"}:
        raise HTTPException(status_code=422, detail="category must be style/structure/persona/taboo")
    row = await PromptRepository(session).create(
        user_id,
        name=payload.name,
        category=payload.category,
        body=payload.body,
        description=payload.description,
        variables=payload.variables,
    )
    await session.commit()
    return {
        "id": row.id,
        "name": row.name,
        "category": row.category.value,
        "version_no": row.version_no,
        "is_official": row.is_official,
        "created_at": row.created_at or datetime.now(),
    }


__all__ = ["router", "prompts_router"]
