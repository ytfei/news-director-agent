"""M3 自动写作：brief 编译 → 大纲（HITL 中断）→ 分段写作 → 稿件落库。

★ 为什么这里没有用 LangGraph / deepagents（docs/04 §5.3 的原选型）：

1. deepagents 的 `skills` 参数形态是**未验证项**（Spike #6），可能直接阻塞 M3；
2. 本项目的 HITL 只需要「中断一次等确认大纲，然后恢复」——
   用 `AgentRun` 的状态机 + `interrupt_payload` 就够表达，
   而且**正是 docs/04 §5.4 定的规则**：interrupt = job 结束，resume = 新 job。
   （若 job 挂着等用户，20 个并发用户就能耗尽 worker 槽位。）
3. 等 Spike #6 验证完再决定是否迁到 `compose_graph`，那时数据结构不用改。

★ 成本与延迟：一篇文章 = 1 次大纲（pro，慢）+ N 次段落（turbo）。
  实测单段 10~30s → 全程 1~3 分钟，**必须异步**，绝不能同步等在请求里。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.models.agent import AgentRun, UsageRecord
from app.models.enums import (
    ArticleVersionSource,
    RunStatus,
)
from app.models.project import Article, ArticleVersion, Project
from app.services.model_provider import ModelError, Task, TokenUsage, get_model_provider
from app.services.project_service import ProjectService

log = structlog.get_logger()

MAX_SECTIONS = 8
MAX_MATERIALS_IN_BRIEF = 12


# ---------------- prompt ----------------

OUTLINE_SYSTEM = """你是财经内容主编，负责为「主理人」规划一篇稿子的结构。

硬约束：
1. **观点必须由主理人自己的点评驱动** —— 素材只是论据，不是结论。
   点评里没说的观点，不要在文章里替他下结论（那是 AI 味，是这个产品最忌讳的）；
2. 只使用「事实与素材」部分给出的材料，**不要引入外部事实或编造数据**；
3. 每个 section 的 key_points 要能对应到具体素材（写清楚用哪条），
   这是下游做「段落 → 出处」可追溯映射的依据；
4. digest 模式（没有点评）时写客观综述，**不要伪装成有观点**；
5. 标题给 3 个候选，风格要有差异（一个克制、一个有信息量、一个有钩子）。"""

OUTLINE_USER = """写作模式：{mode}
目标字数：{target_words}    平台：{platform}
项目标题：{title}

主理人的点评（★ 文章的观点来源，优先级最高）：
{annotations}

事实与素材（可用的论据，不要超出这个范围）：
{materials}

风格/结构提示词：
{prompts}

请输出 JSON：
{{"title_candidates": ["标题1", "标题2", "标题3"],
  "sections": [
    {{"heading": "小标题", "key_points": ["要点1", "要点2"],
      "material_refs": [1], "target_words": 300}}
  ]}}"""

SECTION_SYSTEM = """你按给定的小标题与要点写一段正文。

硬约束（违反会让这篇稿子不可用）：
1. **只使用「可用素材」里的事实** —— 不编造数字、不引入素材外的信息；
   需要引用时写清出处主体（如"据 XX 报道"）；
2. 观点来自主理人点评，**不要凭空升华或给出投资建议**；
3. 不写"综上所述""值得注意的是"这类 AI 套话；
4. 直接输出正文段落本身，不要重复小标题，不要用 Markdown 标题符号。"""

SECTION_USER = """文章语境：{context}

可用素材：
{materials}

请写这一段：
- 小标题：{heading}
- 要点：{key_points}
- 目标字数：约 {target_words} 字

直接输出该段正文。"""


# ---------------- 数据结构 ----------------


@dataclass
class Brief:
    """写作简报：一次写作的完整输入，也是可复现的最小单元。"""

    project_id: uuid.UUID
    title: str = "未命名选题"
    mode: str = "digest"
    platform: str | None = None
    target_words: int = 1200
    annotations: list[dict] = field(default_factory=list)
    materials: list[dict] = field(default_factory=list)
    prompts: list[dict] = field(default_factory=list)


@dataclass
class Section:
    heading: str
    key_points: list[str]
    material_refs: list[int]
    target_words: int
    content: str = ""


@dataclass
class Outline:
    title_candidates: list[str]
    sections: list[Section]


# ---------------- brief 编译 ----------------


def _fmt_annotations(brief: Brief) -> str:
    if not brief.annotations:
        return "（无点评：走 digest 综述模式，不要伪装成有观点）"
    return "\n".join(
        f"[{i}] 素材：{a.get('news_title') or ''}\n    点评：{a.get('body') or ''}"
        for i, a in enumerate(brief.annotations, start=1)
    )


def _fmt_materials(brief: Brief) -> str:
    return "\n".join(
        f"[{i}] {m.get('title') or ''}（{m.get('source_name') or '未知来源'}）\n"
        f"    {m.get('summary') or (m.get('content') or '')[:200]}"
        for i, m in enumerate(brief.materials, start=1)
    )


def _fmt_prompts(brief: Brief) -> str:
    if not brief.prompts:
        return "（无自定义提示词，用默认财经评论风格）"
    return "\n".join(f"- [{p['name']}] {p.get('description') or ''}" for p in brief.prompts)


async def build_brief(session: AsyncSession, project: Project) -> Brief:
    """把「选题 + 素材 + 点评 + 事实基线 + 提示词」编译成一份写作简报。

    ★ 这是 WriterAgent 的真实输入，前端写作台展示的就是它 ——
    不画假界面（docs/03 §4），用户能看见 AI 究竟拿了什么去写。
    """
    service = ProjectService(session)
    materials = await service.materials_with_context(project.id)
    prompts = await service.prompts.by_ids(
        [uuid.UUID(str(x)) for x in (project.prompt_ids or [])]
    )

    annotations: list[dict] = []
    usable: list[dict] = []
    for m in materials[:MAX_MATERIALS_IN_BRIEF]:
        ann = m.get("annotation") or {}
        if ann.get("body"):
            annotations.append({"news_title": m.get("title"), "body": ann.get("body")})
        usable.append(
            {
                "id": str(m.get("id")),
                "title": m.get("title"),
                "source_name": m.get("source_name"),
                "summary": m.get("summary"),
                "content": m.get("content"),
            }
        )

    mode = "opinion" if annotations else "digest"
    return Brief(
        project_id=project.id,
        title=project.title or "未命名选题",
        mode=mode,
        platform=project.platform,
        target_words=project.target_words or 1200,
        annotations=annotations,
        materials=usable,
        prompts=[
            {"name": p.name, "description": p.description, "category": p.category.value}
            for p in prompts
        ],
    )


def brief_to_dict(brief: Brief) -> dict:
    return {
        "project_id": str(brief.project_id),
        "title": brief.title,
        "mode": brief.mode,
        "platform": brief.platform,
        "target_words": brief.target_words,
        "annotations": brief.annotations,
        "materials": brief.materials,
        "prompts": brief.prompts,
    }


# ---------------- 大纲（HITL 中断点）----------------


def _parse_outline(payload: dict | list | None) -> Outline | None:
    if not isinstance(payload, dict):
        return None
    titles = [str(t)[:100] for t in (payload.get("title_candidates") or []) if t][:3]
    sections: list[Section] = []
    for s in (payload.get("sections") or [])[:MAX_SECTIONS]:
        if not isinstance(s, dict):
            continue
        heading = (s.get("heading") or "").strip()
        if not heading:
            continue
        try:
            words = int(s.get("target_words") or 300)
        except (TypeError, ValueError):
            words = 300
        sections.append(
            Section(
                heading=heading[:100],
                key_points=[str(k)[:200] for k in (s.get("key_points") or []) if k][:5],
                material_refs=[int(r) for r in (s.get("material_refs") or []) if isinstance(r, int)][:5],
                target_words=words,
            )
        )
    if not sections:
        return None
    return Outline(title_candidates=titles, sections=sections)


async def plan_outline(brief: Brief) -> tuple[Outline | None, TokenUsage, str | None]:
    """生成大纲。返回 (outline, usage, error)。大纲是 HITL 的中断点。"""
    provider = get_model_provider()
    if not provider.enabled:
        return None, TokenUsage(), "模型未配置（OPENAI_API_KEY 缺失），无法生成大纲"

    messages = [
        {"role": "system", "content": OUTLINE_SYSTEM},
        {
            "role": "user",
            "content": OUTLINE_USER.format(
                mode=brief.mode,
                target_words=brief.target_words,
                platform=brief.platform or "通用",
                title=brief.title,
                annotations=_fmt_annotations(brief),
                materials=_fmt_materials(brief),
                prompts=_fmt_prompts(brief),
            ),
        },
    ]
    try:
        payload, usage = await provider.chat_json(messages, task=Task.WRITE_PLAN)
    except ModelError as exc:
        log.warning("compose.outline_failed", error=str(exc)[:200])
        return None, TokenUsage(), str(exc)[:200]

    outline = _parse_outline(payload)
    if outline is None:
        return None, usage, "模型未返回可用大纲（sections 为空）"
    log.info("compose.outline_done", sections=len(outline.sections), **usage.as_dict())
    return outline, usage, None


# ---------------- 分段写作 ----------------


async def write_section(
    brief: Brief, section: Section, context: str
) -> tuple[str, TokenUsage]:
    provider = get_model_provider()
    messages = [
        {"role": "system", "content": SECTION_SYSTEM},
        {
            "role": "user",
            "content": SECTION_USER.format(
                context=context[:800],
                materials=_fmt_materials(brief),
                heading=section.heading,
                key_points="；".join(section.key_points) or "（按小标题展开）",
                target_words=section.target_words,
            ),
        },
    ]
    try:
        text, usage = await provider.chat(messages, task=Task.WRITE_SECTION)
    except ModelError as exc:
        log.warning("compose.section_failed", heading=section.heading[:30], error=str(exc)[:150])
        return "", TokenUsage()
    return (text or "").strip(), usage


async def write_sections(
    brief: Brief, outline: Outline
) -> tuple[list[Section], TokenUsage]:
    """分段并行写作。★ 段落之间无依赖，所以可以并发（这是耗时的大头）。"""
    context = (
        f"文章主题：{brief.title}\n"
        f"主理人观点：{_fmt_annotations(brief)[:1200]}\n"
        f"模式：{brief.mode}"
    )
    total = TokenUsage()
    results = await asyncio.gather(
        *[write_section(brief, s, context) for s in outline.sections]
    )
    for section, (text, usage) in zip(outline.sections, results, strict=False):
        section.content = text
        total.merge(usage)
    return outline.sections, total


# ---------------- 落库 ----------------


def assemble_markdown(title: str, sections: list[Section]) -> tuple[str, dict]:
    """拼装正文，并生成「段落 → 素材」的可追溯映射。"""
    parts: list[str] = []
    citation: dict[str, list[str]] = {}
    for i, s in enumerate(sections, start=1):
        key = f"section_{i}"
        parts.append(f"## {s.heading}\n\n{s.content}")
        citation[key] = {
            "heading": s.heading,
            "material_refs": s.material_refs,
        }
    body = "\n\n".join(parts)
    return (f"# {title}\n\n{body}" if title else body), citation


async def save_article(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    run: AgentRun,
    brief: Brief,
    outline: Outline,
    sections: list[Section],
) -> Article:
    """落库稿件与首个版本。"""
    title = outline.title_candidates[0] if outline.title_candidates else brief.title
    content, citation = assemble_markdown(title, sections)

    article = Article(
        user_id=user_id,
        project_id=project_id,
        title=title,
        status="draft",
        platform=brief.platform,
    )
    session.add(article)
    await session.flush()

    version = ArticleVersion(
        article_id=article.id,
        version_no=1,
        title=title,
        content=content,
        citation_map={
            "title_candidates": outline.title_candidates,
            "sections": citation,
            "brief_mode": brief.mode,
        },
        source=ArticleVersionSource.ai,
        word_count=len(content),
    )
    session.add(version)
    article.current_version_no = 1

    # 成本台账（与 review 同口径）
    if run.token_input or run.token_output:
        session.add(
            UsageRecord(
                user_id=user_id,
                run_id=run.id,
                category="compose",
                model=run.model,
                token_input=run.token_input,
                token_output=run.token_output,
            )
        )
    await session.flush()
    return article


def outline_to_dict(outline: Outline) -> dict:
    return {
        "title_candidates": outline.title_candidates,
        "sections": [
            {
                "heading": s.heading,
                "key_points": s.key_points,
                "material_refs": s.material_refs,
                "target_words": s.target_words,
            }
            for s in outline.sections
        ],
    }


async def fail_run(run: AgentRun, message: str) -> None:
    run.status = RunStatus.failed
    run.error_message = message[:500]
    run.finished_at = datetime.now()


def brief_from_dict(d: dict) -> Brief:
    return Brief(
        project_id=uuid.UUID(d["project_id"]),
        title=d.get("title", "未命名选题"),
        mode=d.get("mode", "digest"),
        platform=d.get("platform"),
        target_words=d.get("target_words", 1200),
        annotations=d.get("annotations") or [],
        materials=d.get("materials") or [],
        prompts=d.get("prompts") or [],
    )


def outline_from_dict(d: dict) -> Outline:
    return Outline(
        title_candidates=d.get("title_candidates") or [],
        sections=[
            Section(
                heading=s.get("heading", ""),
                key_points=s.get("key_points") or [],
                material_refs=s.get("material_refs") or [],
                target_words=s.get("target_words", 300),
            )
            for s in (d.get("sections") or [])
        ],
    )


# ---------------- 两个阶段（HITL）----------------


async def plan_phase(
    user_id: uuid.UUID, project_id: uuid.UUID, run_id: uuid.UUID
) -> dict:
    """★ 第一阶段：编译 brief + 生成大纲，然后**中断等人工确认**。

    docs/04 §5.4 的规则：interrupt = job 结束。
    这里 job 正常返回，run 停在 `waiting_human`；用户点确认后由**新 job** 续跑。
    （若让 job 挂着等用户，20 个并发用户就能耗尽 worker 槽位。）
    """
    async with SessionLocal() as session:
        run = await session.get(AgentRun, run_id)
        project = await session.get(Project, project_id)
        if run is None or project is None:
            return {"error": "run 或 project 不存在"}

        run.status = RunStatus.running
        run.started_at = datetime.now()
        await session.flush()

        brief = await build_brief(session, project)
        outline, usage, err = await plan_outline(brief)
        run.token_input += usage.input
        run.token_output += usage.output

        if err or outline is None:
            await fail_run(run, err or "大纲生成失败")
            project.status = "drafting"
            await session.commit()
            return {
                "run_id": str(run_id),
                "status": RunStatus.failed.value,
                "error": err or "大纲生成失败",
            }

        # ★ 中断点：把 brief + outline 存进 interrupt_payload，job 到此结束
        run.status = RunStatus.waiting_human
        run.interrupt_payload = {
            "outline": outline_to_dict(outline),
            "brief": brief_to_dict(brief),
        }
        await session.commit()

        log.info(
            "compose.waiting_human",
            run_id=str(run_id),
            sections=len(outline.sections),
            mode=brief.mode,
        )
        return {
            "run_id": str(run_id),
            "status": RunStatus.waiting_human.value,
            "mode": brief.mode,
            "outline": outline_to_dict(outline),
        }


async def resume_phase(user_id: uuid.UUID, run_id: uuid.UUID) -> dict:
    """★ 第二阶段（新 job）：读断点 → 分段写作 → 落库稿件。"""
    async with SessionLocal() as session:
        run = await session.get(AgentRun, run_id)
        if run is None or run.user_id != user_id:
            return {"error": "run 不存在"}
        if run.status != RunStatus.waiting_human or not run.interrupt_payload:
            return {"error": f"run 状态为 {run.status.value}，不可恢复"}

        payload = run.interrupt_payload
        outline = outline_from_dict(payload.get("outline") or {})
        brief = brief_from_dict(payload.get("brief") or {})

        run.status = RunStatus.running
        run.resumed_at = datetime.now()
        await session.flush()

        sections, usage = await write_sections(brief, outline)
        run.token_input += usage.input
        run.token_output += usage.output

        filled = [s for s in sections if s.content]
        if not filled:
            await fail_run(run, "所有段落写作失败")
            await session.commit()
            return {
                "run_id": str(run_id),
                "status": RunStatus.failed.value,
                "error": "段落写作全部失败",
            }

        article = await save_article(
            session,
            user_id=user_id,
            project_id=brief.project_id,
            run=run,
            brief=brief,
            outline=outline,
            sections=sections,
        )

        project = await session.get(Project, brief.project_id)
        if project is not None:
            project.status = "completed"

        run.status = RunStatus.succeeded
        run.finished_at = datetime.now()
        run.interrupt_payload = None  # ★ 恢复后清空断点数据
        version = (
            await session.execute(
                select(ArticleVersion)
                .where(ArticleVersion.article_id == article.id)
                .order_by(ArticleVersion.version_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        run.output = {
            "article_id": str(article.id),
            "title": article.title,
            "word_count": version.word_count if version else 0,
            "sections": len(filled),
        }
        await session.commit()

        log.info(
            "compose.succeeded",
            run_id=str(run_id),
            article_id=str(article.id),
            sections=len(filled),
        )
        return {
            "run_id": str(run_id),
            "status": RunStatus.succeeded.value,
            "article_id": str(article.id),
            "title": article.title,
            "word_count": version.word_count if version else 0,
            "sections": len(filled),
        }


__all__ = [
    "Brief",
    "Outline",
    "Section",
    "build_brief",
    "brief_to_dict",
    "brief_from_dict",
    "plan_outline",
    "write_sections",
    "assemble_markdown",
    "save_article",
    "outline_to_dict",
    "outline_from_dict",
    "plan_phase",
    "resume_phase",
    "fail_run",
]
