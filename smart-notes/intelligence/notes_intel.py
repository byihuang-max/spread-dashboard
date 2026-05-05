"""
Smart Notes 智能分类核心模块
================================

职责：
1. 扫描 smart-notes 所有 .md → 生成向量索引
2. 计算每个类别的中心向量
3. 对新内容做分类 / 迭代候选判断

依赖：
- sentence-transformers（本地 BGE-base-zh-v1.5）
- numpy

所有向量离线计算、零 API 成本。
"""

from __future__ import annotations

import json
import os
import re
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable

import numpy as np

# ---------- 路径常量 ----------
ROOT = Path(__file__).resolve().parent.parent  # smart-notes/
INTEL_DIR = Path(__file__).resolve().parent  # smart-notes/intelligence/
MODEL_PATH = Path.home() / ".cache/modelscope/hub/models/AI-ModelScope/bge-base-zh-v1___5"
EMBEDDINGS_FILE = INTEL_DIR / "note_vectors.json"
CATEGORY_CENTERS_FILE = INTEL_DIR / "category_centers.json"

# ---------- 分类规则 ----------
# 类别 → 对应目录的 glob 规则
CATEGORY_DIRS = {
    "concepts": ["concepts"],
    "conversations": ["conversations"],
    "decisions": ["decisions"],
    "sessions": ["sessions"],
    "research/factors": ["notes/research/factors"],
    "research/strategy": ["notes/research/strategy"],
    "research/narrative": ["notes/research/narrative"],
    "engineering": ["notes/engineering"],
    "reports": ["notes/reports"],
    "emerging_markets": ["notes/emerging_markets"],
}

# 分类决策阈值
AUTO_CLASSIFY_THRESHOLD = 0.60    # >= 0.60 直接落位
CONFIRM_THRESHOLD = 0.50           # 0.50~0.60 灰区，需确认
NEW_CATEGORY_THRESHOLD = 0.50      # < 0.50 提示新类别可能

# 迭代判断阈值
STRONG_ITERATION_THRESHOLD = 0.82  # >= 0.82 + 标题命中 → 强迭代
WEAK_ITERATION_THRESHOLD = 0.72    # 0.72~0.82 → 候选迭代


# ---------- 数据结构 ----------
@dataclass
class NoteRecord:
    path: str            # 相对 smart-notes/ 的路径
    category: str        # 归属类别
    title: str           # 笔记标题（从文件名或 H1 提取）
    preview: str         # 前 300 字符用于人类识别
    content_hash: str    # 用于检测文件变化
    vector: list[float] = field(default_factory=list)


# ---------- 模型加载（延迟） ----------
_model = None


def get_model():
    global _model
    if _model is None:
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(str(MODEL_PATH))
    return _model


def encode(texts: list[str]) -> np.ndarray:
    """把文本列表编码成向量矩阵 (N, 768)，已 L2 归一化。"""
    m = get_model()
    vecs = m.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


# ---------- 笔记扫描 ----------
def infer_category(relpath: str) -> str:
    """从相对路径推断类别"""
    for cat, dirs in CATEGORY_DIRS.items():
        for d in dirs:
            if relpath.startswith(d + "/") or relpath == d:
                return cat
    return "unknown"


def extract_title(filepath: Path, content: str) -> str:
    """提取标题：优先 H1，其次文件名"""
    for line in content.splitlines()[:10]:
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    stem = filepath.stem
    # 去掉日期 / 编号前缀，便于阅读
    stem = re.sub(r"^\d{3}_", "", stem)
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}[-_]?", "", stem)
    return stem


def content_fingerprint(content: str) -> str:
    """哈希用于检测变化"""
    return hashlib.md5(content.encode("utf-8")).hexdigest()[:12]


def title_overlap_score(a: str, b: str) -> float:
    """标题重叠度：用 2-gram 汉字 + 英数词联合命中"""
    def tokens(s: str) -> set[str]:
        s = s.lower()
        # 英数词（≥2 字符）
        words = set(re.findall(r"[a-z0-9]{2,}", s))
        # 汉字 2-gram
        chars = re.findall(r"[\u4e00-\u9fff]", s)
        bigrams = {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}
        return words | bigrams

    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def build_embedding_text(title: str, content: str) -> str:
    """构造用于 embedding 的文本
    格式：标题 + 前 1500 字符正文
    BGE 最大 512 tokens ≈ 1000-1500 汉字
    """
    body = re.sub(r"\n{3,}", "\n\n", content.strip())
    if len(body) > 1500:
        body = body[:1500]
    return f"{title}\n\n{body}"
    """构造用于 embedding 的文本
    格式：标题 + 前 1500 字符正文
    BGE 最大 512 tokens ≈ 1000-1500 汉字
    """
    body = re.sub(r"\n{3,}", "\n\n", content.strip())
    if len(body) > 1500:
        body = body[:1500]
    return f"{title}\n\n{body}"


def scan_notes() -> list[dict]:
    """扫描所有 .md 笔记，返回元数据列表（不含向量）"""
    notes = []
    for cat, dirs in CATEGORY_DIRS.items():
        for d in dirs:
            base = ROOT / d
            if not base.exists():
                continue
            for md in base.rglob("*.md"):
                if md.name.startswith("."):
                    continue
                try:
                    content = md.read_text(encoding="utf-8")
                except Exception:
                    continue
                relpath = str(md.relative_to(ROOT))
                title = extract_title(md, content)
                notes.append({
                    "path": relpath,
                    "category": cat,
                    "title": title,
                    "preview": content[:300].replace("\n", " "),
                    "content_hash": content_fingerprint(content),
                    "_content_for_embed": build_embedding_text(title, content),
                })
    return notes


# ---------- 索引构建 ----------
def build_index(force: bool = False) -> dict:
    """构建 / 增量更新向量索引"""
    existing = {}
    if EMBEDDINGS_FILE.exists() and not force:
        data = json.loads(EMBEDDINGS_FILE.read_text(encoding="utf-8"))
        existing = {r["path"]: r for r in data.get("notes", [])}

    notes = scan_notes()
    to_encode_idx = []
    to_encode_text = []
    for i, n in enumerate(notes):
        old = existing.get(n["path"])
        if old and old.get("content_hash") == n["content_hash"] and old.get("vector"):
            n["vector"] = old["vector"]
        else:
            to_encode_idx.append(i)
            to_encode_text.append(n["_content_for_embed"])

    if to_encode_text:
        print(f"[build_index] 需重算 {len(to_encode_text)} / {len(notes)} 条")
        vecs = encode(to_encode_text)
        for idx, v in zip(to_encode_idx, vecs):
            notes[idx]["vector"] = v.tolist()
    else:
        print(f"[build_index] 全部命中缓存，共 {len(notes)} 条")

    # 清理临时字段
    for n in notes:
        n.pop("_content_for_embed", None)

    out = {"model": "BAAI/bge-base-zh-v1.5", "count": len(notes), "notes": notes}
    EMBEDDINGS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[build_index] 已写入 {EMBEDDINGS_FILE}")

    # 同步刷新类别中心
    build_category_centers(notes)
    return out


def build_category_centers(notes: list[dict]) -> dict:
    """计算每个类别的中心向量（归一化均值）"""
    buckets: dict[str, list[list[float]]] = {}
    for n in notes:
        if not n.get("vector"):
            continue
        buckets.setdefault(n["category"], []).append(n["vector"])

    centers = {}
    for cat, vs in buckets.items():
        arr = np.asarray(vs, dtype=np.float32)
        center = arr.mean(axis=0)
        norm = np.linalg.norm(center)
        if norm > 0:
            center = center / norm
        centers[cat] = {
            "vector": center.tolist(),
            "count": len(vs),
        }

    CATEGORY_CENTERS_FILE.write_text(
        json.dumps(centers, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[build_centers] 已写入 {CATEGORY_CENTERS_FILE}（{len(centers)} 类）")
    return centers


# ---------- 查询与分类 ----------
def load_index() -> tuple[list[dict], dict]:
    notes = json.loads(EMBEDDINGS_FILE.read_text(encoding="utf-8"))["notes"] if EMBEDDINGS_FILE.exists() else []
    centers = json.loads(CATEGORY_CENTERS_FILE.read_text(encoding="utf-8")) if CATEGORY_CENTERS_FILE.exists() else {}
    return notes, centers


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def classify(text: str, title: str = "") -> dict:
    """对一段新内容做分类和迭代判断
    
    返回：
    {
        "category_ranking": [(cat, score), ...],   # 所有类别排序
        "recommended_category": str,
        "decision": "auto" | "confirm" | "new",
        "iteration_candidates": [(path, title, score), ...],  # top 3
        "iteration_decision": "strong" | "weak" | "none",
    }
    """
    notes, centers = load_index()
    if not centers:
        raise RuntimeError("索引未建立，请先跑 build_index.py")

    input_text = build_embedding_text(title or text[:50], text)
    qv = encode([input_text])[0]

    # 1) 类别中心匹配
    cat_scores = []
    for cat, obj in centers.items():
        cv = np.asarray(obj["vector"], dtype=np.float32)
        cat_scores.append((cat, cosine(qv, cv)))
    cat_scores.sort(key=lambda x: -x[1])

    top_cat, top_score = cat_scores[0]
    if top_score >= AUTO_CLASSIFY_THRESHOLD:
        decision = "auto"
        rec = top_cat
    elif top_score >= CONFIRM_THRESHOLD:
        decision = "confirm"
        rec = top_cat
    else:
        decision = "new"
        rec = None

    # 2) 单篇笔记迭代匹配
    note_scores = []
    for n in notes:
        if not n.get("vector"):
            continue
        nv = np.asarray(n["vector"], dtype=np.float32)
        s = cosine(qv, nv)
        tov = title_overlap_score(title, n["title"]) if title else 0.0
        note_scores.append((n["path"], n["title"], s, tov))
    note_scores.sort(key=lambda x: -x[2])

    top_notes = note_scores[:3]
    iter_decision = "none"
    if top_notes:
        p, t, s, tov = top_notes[0]
        if s >= STRONG_ITERATION_THRESHOLD and tov >= 0.4:
            iter_decision = "strong"
        elif s >= WEAK_ITERATION_THRESHOLD:
            iter_decision = "weak"

    return {
        "category_ranking": [(c, round(s, 3)) for c, s in cat_scores],
        "recommended_category": rec,
        "decision": decision,
        "top_category_score": round(top_score, 3),
        "iteration_candidates": [
            {"path": p, "title": t, "similarity": round(s, 3), "title_overlap": round(tov, 2)}
            for p, t, s, tov in top_notes
        ],
        "iteration_decision": iter_decision,
    }


# ---------- CLI ----------
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        force = "--force" in sys.argv
        build_index(force=force)
    elif len(sys.argv) > 1 and sys.argv[1] == "query":
        # 读 stdin
        text = sys.stdin.read()
        # 自动从首行 H1 提取标题
        auto_title = ""
        for line in text.splitlines()[:5]:
            line = line.strip()
            if line.startswith("# "):
                auto_title = line[2:].strip()
                break
        result = classify(text, title=auto_title)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("用法：")
        print("  python3 notes_intel.py build [--force]   # 建/增量索引")
        print("  python3 notes_intel.py query < input.md  # 分类查询")
