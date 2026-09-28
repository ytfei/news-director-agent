"""Agent run 通用接口：查状态 + 恢复断点（HITL）。

★ 为什么单独一个模块：`AgentRun` 同时被 review 与 compose 两种 graph 使用，
放在哪一边都不合适。

恢复语义（docs/04 §5.4）：
    interrupt = job 结束 → run 停在 `waiting_human`
    resume    = **新 job**（绝不让 job 挂着等用户，否则 20 个并发就耗尽 worker 槽位）
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user_id, get_session
from app.models.agent import AgentRun
from app.models.enums import RunGraph, RunStatus
from app.services.queue import enqueue_job

router = APIRouter(prefix="/runs", tags=["runs"])

NON_RESUMABLE = {RunStatus.queued, RunStatus.running, RunStatus.succeeded, RunStatus.failed,
                 RunStatus.cancelled}


@router.get("/{run_id}")
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """查询任意 run 的状态（检查与写作共用）。前端轮询这一个接口即可。"""
    run = await session.get(AgentRun, run_id)
    if run is None or run.user_id != user_id:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "run_id": str(run.id),
        "graph": run.graph.value,
        "status": run.status.value,
        "model": run.model,
        "token_input": run.token_input,
        "token_output": run.token_output,
        "input": run.input,
        "output": run.output,
        "interrupt_payload": run.interrupt_payload,
        "error_message": run.error_message,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


@router.post("/{run_id}/resume", status_code=202)
async def resume_run(
    run_id: uuid.UUID,
    sync: bool = False,
    session: AsyncSession = Depends(get_session),
    user_id: uuid.UUID = Depends(current_user_id),
) -> dict:
    """恢复一个等待人工确认的 run（当前只有 compose 的大纲确认会中断）。

    Redis 不可用时（`?sync=true` 或入队失败）就地执行，保证开发机也能跑通。
    """
    run = await session.get(AgentRun, run_id)
    if run is None or run.user_id != user_id:
        raise HTTPException(status_code=404, detail="run not found")

    if run.status in NON_RESUMABLE:
        raise HTTPException(
            status_code=409, detail=f"run 状态为 {run.status.value}，不可恢复"
        )
    if run.status != RunStatus.waiting_human:
        raise HTTPException(status_code=409, detail=f"run 状态为 {run.status.value}，不是等待人工")

    job_id = await enqueue_job("compose_resume", str(user_id), str(run_id))

    if job_id is None or sync:
        from app.services.compose_service import resume_phase

        result = await resume_phase(user_id, run_id)
        return {**result, "async": False}

    return {
        "run_id": str(run.id),
        "job_id": job_id,
        "status": RunStatus.queued.value,
        "async": True,
    }


__all__ = ["router", "RunGraph"]
