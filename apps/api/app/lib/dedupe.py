"""去重与归簇算法。

把两件被混为一谈的事分开（这是本模块存在的原因）：

| 层 | 判定什么 | 方法 | 阈值语义 |
| --- | --- | --- | --- |
| L1 归一化 | 让文本可比 | 去来源前缀 / 全半角 / 标点 | — |
| L2 精确 | 完全相同 | content_hash | 精确 |
| **L3 转载** | 同一篇稿子的不同渠道转载 | **MinHash Jaccard** | 0~1（0.75 = 75% shingle 重合） |
| **L4 事件** | 同事件的不同角度报道 | 实体 + 语义 + 关键词 + 时间 | 0~1（可解释分项） |

为什么 L3 用 MinHash 而不是 simhash：
- 阈值有直观语义（Jaccard），simhash 的汉明距离没有
- 5-gram shingle 对"改写标题"比 2-gram 鲁棒
- 转载判定要精确率优先：误合并会丢掉一条独立的报道

为什么 L4 与 L3 必须分开：
- 转载应该「合并展示」→ 只留一条主条目 + source_count
- 同事件不同角度应该「都保留」→ 信息互补，正是交叉验证的素材
"""

from __future__ import annotations

import hashlib
import re
import struct
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------- 参数
NUM_PERM = 64
# ★ 中文用 3-gram：实测 5-gram 对"渠道改写"重合度只有 0.15（语序一变，连续 5 字
#   几乎不再重合），而 3-gram 能保留住大部分局部特征。英文可适当调大。
SHINGLE_K = 3
MASK64 = (1 << 64) - 1
PRIME = (1 << 61) - 1

# 确定性伪随机参数（固定种子 → 同一文本每次得到同一签名）
_PARAMS: list[tuple[int, int]] = []
_rng_seed = 20240926
for _i in range(NUM_PERM):
    _h = hashlib.blake2b(f"minhash-{_i}-{_rng_seed}".encode(), digest_size=16).digest()
    _a = int.from_bytes(_h[:8], "big") % (PRIME - 1) + 1
    _b = int.from_bytes(_h[8:], "big") % PRIME
    _PARAMS.append((_a, _b))

# 来源前缀：渠道常加「【有色发布】」「（独家）」等，会让标题看起来不相似
_PREFIX_RE = re.compile(r"^\s*[【\[（(][^】\]）)]{1,12}[】\]）)]\s*")
# 只保留「中文 / 字母 / 数字 / 小数点」，其余（标点、空白、各类括号）全部去掉。
# ★ 必须保留小数点：否则 "1.5%" 会变成 "15%"，把数字指纹毁掉。
_KEEP_RE = re.compile(r"[^一-鿿A-Za-z0-9.]+")


# ---------------------------------------------------------------- L1 归一化
def normalize_text(text: str | None) -> str:
    """清洗：全角转半角（NFKC）→ 去来源前缀 → 去标点与空白 → 英文小写。"""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text)
    s = _PREFIX_RE.sub("", s)
    s = _KEEP_RE.sub("", s)
    return s.lower()


# MinHash 的耗时 ∝ shingle 数 × num_perm。正文动辄几千字，
# 而判定转载用标题+开头已经足够 —— 统一截断，保证入库与回填都跑得动。
TEXT_LIMIT = 1000


def dedupe_text(title: str | None, content: str | None, limit: int = TEXT_LIMIT) -> str:
    """参与去重计算的文本（标题 + 正文开头，截断到 limit）。"""
    return f"{title or ''}\n{content or ''}"[:limit]


def shingles(text: str | None, k: int = SHINGLE_K) -> set[str]:
    """字符级 k-gram 集合。中文没有空格分词，字符 n-gram 最稳。"""
    s = normalize_text(text)
    if not s:
        return set()
    if len(s) <= k:
        return {s}
    return {s[i : i + k] for i in range(len(s) - k + 1)}


# ---------------------------------------------------------------- L3 MinHash
def minhash_signature(shs: set[str], num_perm: int = NUM_PERM) -> bytes:
    """MinHash 签名。返回 64 × uint64 的字节串（512 B）。

    用 universal hashing（a·x + b mod p）从单个哈希派生多个"独立"哈希，
    避免对每个 shingle 做 num_perm 次哈希——那在长文本上会非常慢。
    """
    sig = [PRIME] * num_perm
    for sh in shs:
        x = int.from_bytes(hashlib.blake2b(sh.encode("utf-8"), digest_size=8).digest(), "big")
        for i, (a, b) in enumerate(_PARAMS[:num_perm]):
            v = (a * x + b) % PRIME
            if v < sig[i]:
                sig[i] = v
    return struct.pack(f"<{num_perm}Q", *sig)


def signature_to_list(sig: bytes, num_perm: int = NUM_PERM) -> list[int]:
    """按需取前 num_perm 个值（bucket 只用到前几个，不能直接按总数解包）。"""
    need = num_perm * 8
    return list(struct.unpack(f"<{num_perm}Q", sig[:need]))


def jaccard_from_signatures(a: bytes, b: bytes, num_perm: int = NUM_PERM) -> float:
    """由 MinHash 签名估计 Jaccard 相似度（0~1）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    la = signature_to_list(a, num_perm)
    lb = signature_to_list(b, num_perm)
    same = sum(1 for x, y in zip(la, lb, strict=False) if x == y)
    return same / num_perm


def jaccard_text(a: str | None, b: str | None, k: int = SHINGLE_K) -> float:
    """直接算两段文本的 Jaccard（精确值，仅供小样本/测试用）。"""
    sa, sb = shingles(a, k), shingles(b, k)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def minhash_bucket(sig: bytes, bands: int = 8) -> int:
    """简化 LSH：取签名前 bands 个值混合成一个桶号，用于 SQL 粗筛候选。

    只比较同桶的条目，避免每次入库都和窗口内全部条目算 Jaccard。
    """
    if not sig:
        return 0
    vals = signature_to_list(sig, bands)
    h = 0
    for v in vals:
        h = (h * 31 + v) & MASK64
    # ★ 转有符号：PG 的 bigint 是 int64，无符号 64 位会报
    #   "value out of int64 range"
    return h - (1 << 64) if h >= (1 << 63) else h


# ---------------------------------------------------------------- L4 事件聚类
@dataclass
class EventCandidate:
    """参与事件聚类的最小特征集。

    ★ `title_shingles` 是主信号：实测库里 entities / keywords / industries
    **15982 条无一有值**（规则版 enrich 没写这些字段），embedding 也几乎没有。
    所以事件聚类必须依赖能直接从标题算出来的特征，否则打分恒为 0。
    """

    entities: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    published_at: datetime = field(default_factory=datetime.now)
    embedding: list[float] | None = None
    # 预计算的标题 3-gram 集合（构造时算一次，避免在两两比较里重复计算）
    title_shingles: set[str] = field(default_factory=set)

    @classmethod
    def from_item(
        cls,
        title: str | None,
        entities=None,
        keywords=None,
        published_at: datetime | None = None,
        embedding=None,
    ) -> EventCandidate:
        return cls(
            entities=list(entities or []),
            keywords=list(keywords or []),
            published_at=published_at or datetime.now(),
            embedding=list(embedding) if embedding is not None else None,
            title_shingles=shingles(title),
        )


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def event_score(
    a: EventCandidate,
    b: EventCandidate,
    *,
    window_hours: float = 72.0,
    w_title: float = 0.55,
    w_embed: float = 0.25,
    w_entity: float = 0.10,
    w_keyword: float = 0.05,
    w_time: float = 0.05,
) -> tuple[float, dict[str, float]]:
    """同事件打分（0~1）。返回 (score, 分项)，分项用于向用户解释"为什么归在一起"。

    embedding 缺失时（存量未向量化），该项权重按比例分摊给其余项，
    因此**没有 embedding 也能工作**，只是精度略低。
    """
    ent = _jaccard({e.strip() for e in a.entities if e}, {e.strip() for e in b.entities if e})
    kw = _jaccard({k.strip() for k in a.keywords if k}, {k.strip() for k in b.keywords if k})
    title = _jaccard(set(a.title_shingles), set(b.title_shingles))

    hours = abs((a.published_at - b.published_at).total_seconds()) / 3600.0
    # ★ 时间是**硬门槛**而不只是软权重：只给 0.10 权重时，相隔 10 天、实体关键词
    #   完全相同的两条仍能拿到 0.85 分。但 10 天后的"茅台财报"已经是另一件事了。
    within_window = window_hours <= 0 or hours <= window_hours
    time_score = max(0.0, 1.0 - hours / window_hours) if window_hours > 0 else 0.0

    has_emb = a.embedding is not None and b.embedding is not None
    emb = cosine(a.embedding, b.embedding) if has_emb else 0.0

    if has_emb:
        weights = {
            "title": w_title,
            "embed": w_embed,
            "entity": w_entity,
            "keyword": w_keyword,
            "time": w_time,
        }
        parts = {"title": title, "embed": emb, "entity": ent, "keyword": kw, "time": time_score}
    else:
        # 没有 embedding 时把它的权重按比例分摊（title 拿大头），保证仍能判定
        base = w_title + w_entity + w_keyword + w_time
        weights = {
            "title": w_title / base,
            "entity": w_entity / base,
            "keyword": w_keyword / base,
            "time": w_time / base,
        }
        parts = {"title": title, "entity": ent, "keyword": kw, "time": time_score}

    if not within_window:
        return 0.0, {**parts, "time": 0.0, "out_of_window": True}

    score = sum(weights[k] * parts[k] for k in weights)
    return round(score, 4), parts


__all__ = [
    "normalize_text",
    "dedupe_text",
    "shingles",
    "minhash_signature",
    "signature_to_list",
    "jaccard_from_signatures",
    "jaccard_text",
    "minhash_bucket",
    "EventCandidate",
    "event_score",
    "cosine",
    "NUM_PERM",
    "SHINGLE_K",
]
