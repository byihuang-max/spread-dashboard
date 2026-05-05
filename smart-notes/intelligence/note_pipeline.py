"""
Smart Notes 笔记入库编排器
==========================

把 embedding 分类（notes_intel）+ LLM 生成（llm_client）串成完整流程。

典型入口：
    from note_pipeline import ingest
    result = ingest("一段笔记原文...")
    # result = {
    #   "status": "written",
    #   "path": "notes/engineering/2026-05-05_xxx.md",
    #   "category": "engineering",
    #   "is_iteration": True,
    #   "iteration_of": "notes/engineering/2026-04-17_三端对齐操作手册.md",
    #   "iteration_version": "v2",
    #   "decisions": [...]  # 过程日志
    # }
"""

from __future__ import annotations

import json
import re
import datetime as dt
from pathlib import Path

from notes_intel import (
    ROOT,
    classify,
    build_index,
    build_embedding_text,
    AUTO_CLASSIFY_THRESHOLD,
    CONFIRM_THRESHOLD,
)
from llm_client import generate_metadata, judge_iteration, gray_zone_arbitrate


def _safe_filename(title: str) -> str:
    """把 title 压成合法的文件名段"""
    s = re.sub(r"[\\/:*?\"<>|]+", "", title).strip()
    s = re.sub(r"\s+", "_", s)
    return s[:60] or "untitled"


def _detect_version_from_filename(name: str) -> tuple[str, int | float]:
    """从文件名里提取 base name 和版本号。
    例：
      'xxx_v2.md' → ('xxx', 2)
      'xxx_v1.5_2026-05-02.md' → ('xxx_2026-05-02', 1.5)
      '029_强势股日报体系v1.5_2026-05-02.md' → ('029_强势股日报体系_2026-05-02', 1.5)
      'xxx.md' → ('xxx', 1)
    """
    stem = Path(name).stem
    # 匹配任意位置的 v<数字>（可带小数），前后可能有下划线或无
    m = re.search(r"[_\-]?v(\d+(?:\.\d+)?)([_\-]|$)", stem, re.IGNORECASE)
    if m:
        ver_str = m.group(1)
        ver = float(ver_str) if "." in ver_str else int(ver_str)
        # 从原字符串把 vX.Y 段去掉
        base = stem[:m.start()] + stem[m.end() - len(m.group(2)):]
        base = re.sub(r"__+", "_", base).strip("_")
        return base, ver
    return stem, 1


def _next_version_path(old_path: Path) -> Path:
    base, v = _detect_version_from_filename(old_path.name)
    # 下一个整数版本
    next_v = int(v) + 1
    new_name = f"{base}_v{next_v}.md"
    return old_path.with_name(new_name)


def _format_note(title: str, content: str, meta: dict, extends: str | None = None,
                 iter_diff: str | None = None, version: int = 1) -> str:
    """组装笔记 markdown"""
    today = dt.date.today().isoformat()
    tags = " ".join(f"#{t}" for t in meta.get("tags", []))
    summary = meta.get("summary", "").strip()

    parts = [f"# {title}", ""]
    parts.append(f"**日期**: {today}")
    if version > 1:
        parts.append(f"**版本**: v{version}")
    if extends:
        parts.append(f"**迭代自**: `{extends}`")
    if tags:
        parts.append(f"**标签**: {tags}")
    parts.append("")
    parts.append("---")
    parts.append("")
    if summary:
        parts.append(f"## 摘要\n\n{summary}")
        parts.append("")
    if iter_diff:
        parts.append(f"## 相比上一版")
        parts.append("")
        parts.append(iter_diff)
        parts.append("")
    parts.append("## 正文")
    parts.append("")
    parts.append(content.strip())
    return "\n".join(parts) + "\n"


def ingest(text: str, dry_run: bool = False) -> dict:
    """把一段文本落成笔记。
    
    流程：
    1. LLM 生成元数据（标题/摘要/标签/category_hint）
    2. embedding 分类（recommended_category + iteration_candidates）
    3. 归类决策：
       - 两者一致 → 用这个
       - 灰区 → Claude 仲裁
       - LLM 提示 __NEW__ → 标记待人工确认
    4. 迭代决策：
       - strong → 直接 v+1
       - weak → Claude 二次判断
       - none → 新建
    5. 写入 / dry_run
    """
    decisions = []

    # Step 1: LLM 生成元数据
    decisions.append("→ 调用 Claude 生成元数据")
    meta = generate_metadata(text)
    title = meta.get("title", "").strip() or text.strip().split("\n")[0][:30]
    llm_category_hint = meta.get("category_hint", "").strip()

    # Step 2: embedding 分类
    decisions.append("→ 运行 embedding 分类")
    embed_result = classify(text, title=title)
    rec = embed_result["recommended_category"]
    top_score = embed_result["top_category_score"]
    embed_decision = embed_result["decision"]
    iter_cands = embed_result["iteration_candidates"]
    iter_decision = embed_result["iteration_decision"]

    # Step 3: 归类最终决策
    final_category = None
    category_source = ""

    if llm_category_hint.startswith("__NEW__"):
        new_cat_suggestion = llm_category_hint.replace("__NEW__", "").lstrip(":").strip() or "unknown"
        final_category = None
        category_source = f"LLM 建议新类 '{new_cat_suggestion}'，需人工确认"
        decisions.append(f"⚠️  {category_source}")
    elif llm_category_hint and rec and llm_category_hint == rec:
        final_category = rec
        category_source = f"LLM + embedding 一致 → {rec} (embed {top_score:.2f})"
        decisions.append(f"✓ {category_source}")
    elif embed_decision == "auto":
        final_category = rec
        category_source = f"embedding auto → {rec} ({top_score:.2f})"
        decisions.append(f"✓ {category_source}")
    elif embed_decision == "confirm":
        # 灰区仲裁
        decisions.append(f"⚠️  embedding 灰区 ({top_score:.2f})，启用 Claude 仲裁")
        top3 = embed_result["category_ranking"][:3]
        arb = gray_zone_arbitrate(text, top3)
        fc = arb.get("final_category", "")
        if fc.startswith("__NEW__"):
            final_category = None
            category_source = f"LLM 仲裁提示新类 '{fc.replace('__NEW__','').lstrip(':').strip()}'，需人工确认"
        else:
            final_category = fc
            category_source = f"Claude 仲裁 → {fc}：{arb.get('reason','')}"
        decisions.append(f"  {category_source}")
    else:
        # LLM hint 存在但 embedding 也不确定 → 优先用 LLM
        if llm_category_hint:
            final_category = llm_category_hint
            category_source = f"LLM 兜底 → {llm_category_hint}（embedding {top_score:.2f} 偏低）"
            decisions.append(f"✓ {category_source}")

    if not final_category:
        return {
            "status": "need_confirm",
            "reason": category_source,
            "meta": meta,
            "embed_result": embed_result,
            "decisions": decisions,
        }

    # Step 4: 迭代决策
    extends_path = None
    iter_diff = None
    next_version = 1

    if iter_cands:
        top_cand = iter_cands[0]
        if iter_decision == "strong":
            # 强迭代直接升级
            extends_path = top_cand["path"]
            decisions.append(f"✓ 识别为强迭代 → {extends_path} (sim {top_cand['similarity']:.2f})")
            # 获取 diff 摘要
            old_file = ROOT / extends_path
            if old_file.exists():
                old_content = old_file.read_text(encoding="utf-8")
                judge = judge_iteration(text, top_cand["title"], old_content)
                if judge.get("is_iteration"):
                    iter_diff = judge.get("diff_summary", "")
            _, v = _detect_version_from_filename(old_file.name)
            next_version = int(v) + 1 if isinstance(v, int) else int(v) + 1
        elif iter_decision == "weak":
            # 弱迭代让 Claude 二次确认
            decisions.append(f"⚠️  弱迭代候选 → Claude 确认 {top_cand['path']} (sim {top_cand['similarity']:.2f})")
            old_file = ROOT / top_cand["path"]
            if old_file.exists():
                old_content = old_file.read_text(encoding="utf-8")
                judge = judge_iteration(text, top_cand["title"], old_content)
                if judge.get("is_iteration") and judge.get("confidence") in ("medium", "high"):
                    extends_path = top_cand["path"]
                    iter_diff = judge.get("diff_summary", "")
                    _, v = _detect_version_from_filename(old_file.name)
                    next_version = int(v) + 1 if isinstance(v, int) else int(v) + 1
                    decisions.append(f"  Claude 确认是迭代 ({judge.get('confidence')})")
                else:
                    decisions.append("  Claude 判定非迭代，当独立新笔记")

    # Step 5: 决定文件路径
    category_dir_map = {
        "concepts": "concepts",
        "conversations": "conversations",
        "decisions": "decisions",
        "sessions": "sessions",
        "research/factors": "notes/research/factors",
        "research/strategy": "notes/research/strategy",
        "research/narrative": "notes/research/narrative",
        "engineering": "notes/engineering",
        "reports": "notes/reports",
        "emerging_markets": "notes/emerging_markets",
    }
    target_dir = category_dir_map.get(final_category)
    if not target_dir:
        return {
            "status": "need_confirm",
            "reason": f"无法映射类别 '{final_category}' 到目录",
            "meta": meta,
            "decisions": decisions,
        }

    target_dir_abs = ROOT / target_dir
    target_dir_abs.mkdir(parents=True, exist_ok=True)

    if extends_path:
        old_file = ROOT / extends_path
        target_file = _next_version_path(old_file)
    else:
        today = dt.date.today().isoformat()
        fname = f"{today}_{_safe_filename(title)}.md"
        target_file = target_dir_abs / fname

    # Step 6: 组装内容
    doc = _format_note(
        title=title,
        content=text,
        meta=meta,
        extends=str(target_file.parent.relative_to(ROOT) / Path(extends_path).name) if extends_path else None,
        iter_diff=iter_diff,
        version=next_version,
    )

    if dry_run:
        return {
            "status": "dry_run",
            "target_path": str(target_file.relative_to(ROOT)),
            "category": final_category,
            "is_iteration": bool(extends_path),
            "iteration_of": extends_path,
            "iteration_version": next_version,
            "preview_doc": doc,
            "decisions": decisions,
        }

    # Step 7: 实际写入
    target_file.write_text(doc, encoding="utf-8")
    decisions.append(f"✓ 已写入 {target_file.relative_to(ROOT)}")

    return {
        "status": "written",
        "path": str(target_file.relative_to(ROOT)),
        "category": final_category,
        "is_iteration": bool(extends_path),
        "iteration_of": extends_path,
        "iteration_version": next_version,
        "meta": meta,
        "decisions": decisions,
    }


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    text = sys.stdin.read()
    if not text.strip():
        print("用法：python3 note_pipeline.py [--dry] < input.md")
        sys.exit(1)
    result = ingest(text, dry_run=dry)
    print(json.dumps(result, ensure_ascii=False, indent=2))
