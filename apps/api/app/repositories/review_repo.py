"""体检报告与事实卡片仓储。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import FindingStatus, ReportVerdict
from app.models.review import FactCard, FactCardClaim, ReviewFinding, ReviewReport


class ReviewRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---------------- 报告 ----------------

    async def create_report(
        self,
        *,
        user_id: uuid.UUID,
        annotation_id: uuid.UUID,
        annotation_version_no: int,
        run_id: uuid.UUID | None,
    ) -> ReviewReport:
        report = ReviewReport(
            user_id=user_id,
            annotation_id=annotation_id,
            annotation_version_no=annotation_version_no,
            run_id=run_id,
            verdict=ReportVerdict.passed,
        )
        self.session.add(report)
        await self.session.flush()
        return report

    async def add_findings(self, report: ReviewReport, findings: list[ReviewFinding]) -> None:
        for f in findings:
            f.report_id = report.id
            self.session.add(f)
        report.findings_count = len(findings)
        report.verdict = verdict_of(findings)
        await self.session.flush()

    async def get_report(
        self, report_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[ReviewReport, list[ReviewFinding]] | None:
        report = (
            await self.session.execute(
                select(ReviewReport).where(
                    ReviewReport.id == report_id, ReviewReport.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if report is None:
            return None
        findings = await self.findings_of(report.id)
        return report, findings

    async def findings_of(self, report_id: uuid.UUID) -> list[ReviewFinding]:
        stmt = (
            select(ReviewFinding)
            .where(ReviewFinding.report_id == report_id)
            .order_by(ReviewFinding.severity.asc(), ReviewFinding.created_at.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def latest_report_of(self, annotation_id: uuid.UUID) -> ReviewReport | None:
        return (
            await self.session.execute(
                select(ReviewReport)
                .where(ReviewReport.annotation_id == annotation_id)
                .order_by(ReviewReport.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    async def latest_reports(self, annotation_ids: list[uuid.UUID]) -> dict[uuid.UUID, ReviewReport]:
        if not annotation_ids:
            return {}
        rows = (
            await self.session.execute(
                select(ReviewReport)
                .where(ReviewReport.annotation_id.in_(annotation_ids))
                .order_by(ReviewReport.created_at.desc())
            )
        ).scalars().all()
        out: dict[uuid.UUID, ReviewReport] = {}
        for r in rows:
            out.setdefault(r.annotation_id, r)
        return out

    async def open_findings(self, report_ids: list[uuid.UUID]) -> list[ReviewFinding]:
        if not report_ids:
            return []
        stmt = select(ReviewFinding).where(
            ReviewFinding.report_id.in_(report_ids),
            ReviewFinding.status == FindingStatus.open,
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def dismissed_signatures(self, annotation_id: uuid.UUID) -> set[tuple[str, str]]:
        """这条点评历史上被驳回过的 (track, quote)。

        ★ 产品语义：驳回 = 用户说"这不算问题，我已经确认过"，同一问题不再重复报。
        没有这条，用户每改一次正文、每复检一次，都要把同样的误报再驳回一遍。
        """
        rows = (
            await self.session.execute(
                select(ReviewFinding.track, ReviewFinding.quote)
                .join(ReviewReport, ReviewReport.id == ReviewFinding.report_id)
                .where(
                    ReviewReport.annotation_id == annotation_id,
                    ReviewFinding.status == FindingStatus.dismissed,
                )
            )
        ).all()
        return {(t.value, q or "") for t, q in rows}

    async def get_finding(
        self, finding_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReviewFinding | None:
        return (
            await self.session.execute(
                select(ReviewFinding)
                .join(ReviewReport, ReviewReport.id == ReviewFinding.report_id)
                .where(ReviewFinding.id == finding_id, ReviewReport.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def resolve_finding(
        self, finding: ReviewFinding, status: FindingStatus, reason: str | None
    ) -> ReviewFinding:
        finding.status = status
        finding.reason = reason
        finding.resolved_at = datetime.now()
        await self.session.flush()
        return finding

    async def refresh_verdict(self, report: ReviewReport) -> ReviewReport:
        findings = await self.findings_of(report.id)
        report.verdict = verdict_of(findings)
        await self.session.flush()
        return report

    # ---------------- 事实基线 ----------------

    async def get_card(self, news_item_id: uuid.UUID) -> FactCard | None:
        return (
            await self.session.execute(
                select(FactCard).where(FactCard.news_item_id == news_item_id)
            )
        ).scalar_one_or_none()

    async def claims_of(self, card_id: uuid.UUID) -> list[FactCardClaim]:
        stmt = (
            select(FactCardClaim)
            .where(FactCardClaim.card_id == card_id)
            .order_by(FactCardClaim.seq.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def upsert_card(
        self,
        news_item_id: uuid.UUID,
        *,
        context_notes: str | None,
        related_symbols: list[str],
        open_questions: list,
        model: str | None,
        claims: list[dict],
    ) -> FactCard:
        card = await self.get_card(news_item_id)
        if card is None:
            card = FactCard(news_item_id=news_item_id)
            self.session.add(card)
            await self.session.flush()
        card.context_notes = context_notes
        card.related_symbols = related_symbols
        card.open_questions = open_questions
        card.model = model
        card.generated_at = datetime.now()
        card.status = "ready"

        await self.session.execute(delete(FactCardClaim).where(FactCardClaim.card_id == card.id))
        for i, c in enumerate(claims, start=1):
            evidence = c.get("evidence") or []
            status = c.get("status", "unverifiable")
            # ★ 硬约束：没有 evidence 的 claim 不允许标 verified
            if status == "verified" and not evidence:
                status = "unverifiable"
            self.session.add(
                FactCardClaim(
                    card_id=card.id,
                    seq=i,
                    claim=c["claim"],
                    status=status,
                    confidence=c.get("confidence", 0.5),
                    evidence=evidence,
                )
            )
        await self.session.flush()
        return card


def verdict_of(findings: list[ReviewFinding]) -> ReportVerdict:
    """verdict 派生规则（docs/03 §3 步骤⑦）：blocker → blocked；high/medium → needs_revision。

    已处置（accepted/dismissed/ignored）的 finding 不再参与判定。
    """
    verdict = ReportVerdict.passed
    for f in findings:
        # status 为 None 表示对象刚从 server_default 落库、尚未回读，按 open 处理
        if f.status not in (None, FindingStatus.open):
            continue
        if f.severity.value == "blocker":
            return ReportVerdict.blocked
        if f.severity.value in {"high", "medium"}:
            verdict = ReportVerdict.needs_revision
    return verdict


__all__ = ["ReviewRepository", "verdict_of"]
