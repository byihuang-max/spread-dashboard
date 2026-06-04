"""
Claude 中转 API 客户端（Smart Notes 用）
========================================

职责：
- 根据原始文本生成笔记元数据（标题、摘要、标签）
- 灰区兜底：embedding confirm 时由 LLM 做二次决策
- 版本迭代：对比新旧笔记给出 diff 摘要
"""

from __future__ import annotations

import json
import os
import re
import requests
import certifi


def _openclaw_cfg_path():
    """openclaw.json 真实路径（兼容 HOME 被 Hermes/代理重定向的场景）"""
    for p in [
        os.path.expanduser("~/.openclaw/openclaw.json"),
        "/Users/apple/.openclaw/openclaw.json",
        "/home/ubuntu/.openclaw/openclaw.json",
    ]:
        if os.path.exists(p):
            return p
    return os.path.expanduser("~/.openclaw/openclaw.json")


def _load_provider():
    with open(_openclaw_cfg_path()) as f:
        cfg = json.load(f)
    # 用 aicanapi（4.6 通道），比 aicanapi-47 更稳定
    return cfg["models"]["providers"]["aicanapi"]


def _load_openai_provider():
    with open(_openclaw_cfg_path()) as f:
        cfg = json.load(f)
    return cfg["models"]["providers"]["aicanopenai"]


def call_claude(prompt: str, system: str = "", max_tokens: int = 1000, model: str = "claude-opus-4-6") -> str:
    """调 LLM API，Claude Opus 4.6 优先，GPT-5.5 作为 fallback"""
    # 先尝试 Claude Opus 4.6（中文理解更好）
    try:
        prov = _load_provider()
        url = prov["baseUrl"].rstrip("/") + "/v1/messages"
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        r = requests.post(
            url,
            headers={
                "x-api-key": prov["apiKey"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
            verify=certifi.where(),
        )
        r.raise_for_status()
        data = r.json()
        # 防御：content 可能不是 text 类型（filter/tool_use/空响应）
        for block in data.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                return block["text"]
        raise ValueError(f"No text block in Claude response: {data.get('content', [])}")
    except (requests.exceptions.HTTPError, requests.exceptions.Timeout, ValueError) as e:
        print(f"[llm_client] Claude 失败 ({e})，fallback 到 GPT-5.5")

    # Fallback: GPT-5.5
    prov = _load_openai_provider()
    url = prov["baseUrl"].rstrip("/") + "/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {prov['apiKey']}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-5.5",
            "messages": messages,
            "max_tokens": max_tokens,
        },
        timeout=60,
        verify=certifi.where(),
    )
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]
    return data["content"][0]["text"]


# ---------- 业务封装 ----------

META_SYSTEM_PROMPT = """你是 Roni（FOF 基金经理）的笔记归档助手。
接到一段原文后，你需要返回严格的 JSON，包含：
- title: 5-20 字的标题，能代表内容核心
- summary: 1-2 句的摘要，陈述句
- tags: 3-6 个关键词标签（中文或英文，不带 # 号）
- category_hint: 对以下 10 个候选里选最合适的一个（只输出一个），如果都不合适输出 "__NEW__" 加简短建议类名

候选类别：
- concepts: 概念定义（"X 是什么"）
- conversations: 研究对话过程（和 AI 或团队的讨论）
- decisions: 最终决策（有明确结论影响后续开发）
- sessions: 阶段性共识 / 工作流
- research/factors: 因子研究
- research/strategy: 策略研究
- research/narrative: 叙事研究
- engineering: 工程/架构/产品化/部署
- reports: 外部研报
- emerging_markets: 新兴市场

只返回 JSON，不要任何解释。"""


def generate_metadata(text: str) -> dict:
    """让 LLM 生成笔记元数据"""
    prompt = f"原文：\n\n{text[:3000]}\n\n请返回 JSON。"
    raw = call_claude(prompt, system=META_SYSTEM_PROMPT, max_tokens=500)
    raw = raw.strip()
    # 去掉 <think>...</think>
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # 提取第一个 {...} 块（兼容代码围栏和多余文本）
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if m:
        raw = m.group(0)
    return json.loads(raw)


ITERATION_SYSTEM_PROMPT = """你是笔记版本比对助手。
给定"旧笔记"和"新笔记"，你要判断新笔记是否是旧笔记的迭代版本，并返回 JSON：
- is_iteration: true / false
- diff_summary: 如果是迭代，用 2-4 行 bullet 点列出新版相对旧版的变化；不是则空字符串
- confidence: low / medium / high

判断原则：
- 相同主题、相同目标、相近结构，内容有明显演进 → is_iteration=true
- 只是引用了相似概念但探讨方向不同 → is_iteration=false
- 只返回 JSON。"""


def judge_iteration(new_text: str, old_title: str, old_content: str) -> dict:
    """让 Claude 判断新内容是否是某旧笔记的迭代，并生成 diff 摘要"""
    prompt = f"""旧笔记标题：{old_title}
旧笔记内容（截取）：
{old_content[:1500]}

---

新笔记内容：
{new_text[:1500]}

请返回 JSON。"""
    raw = call_claude(prompt, system=ITERATION_SYSTEM_PROMPT, max_tokens=500)
    raw = raw.strip()
    import re
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    import re
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # 防御：尝试提取第一个 JSON 对象
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 尝试找 { ... } 子串
        import re as _re
        m = _re.search(r'\{[^{}]*\}', raw, _re.DOTALL)
        if m:
            return json.loads(m.group())
        # 实在解析不了，返回安全默认值
        return {"is_iteration": False, "diff_summary": "", "confidence": "low"}


GRAY_ZONE_SYSTEM_PROMPT = """你是笔记归类仲裁助手。
embedding 系统对一段新内容的归类信心不足（处于灰区），需要你读完原文做最终决策。

你会收到：
- 新内容
- 所有可选类别清单（带简短说明）

你要返回 JSON：
- final_category: 必须从候选清单里选一个；只有当内容**完全无法**归入任何现有类别时才输出 "__NEW__:<新类名>"
- reason: 1 句话解释

**重要规则：**
- 优先从现有类别里选，不要轻易建议新类
- 即使某个类别现在是空的，只要语义匹配就选它（比如 emerging_markets 虽然空但新兴市场内容就该归这里）
- 只有当话题跨所有现有类别都不匹配时（比如"个人生活日记"），才提示 __NEW__

只返回 JSON，不要任何解释或代码块标记。"""


ALL_CATEGORIES_DESC = """- concepts: 概念定义（"X 是什么"）
- conversations: 研究对话过程（和 AI 或团队的讨论）
- decisions: 最终决策（有明确结论影响后续开发）
- sessions: 阶段性共识 / 工作流
- research/factors: 因子研究
- research/strategy: 策略研究
- research/narrative: 叙事 / 主题研究
- engineering: 工程 / 架构 / 部署 / 产品化
- reports: 外部研报
- emerging_markets: 新兴市场（巴西/印度/东南亚/拉美等）"""


def gray_zone_arbitrate(text: str, top_candidates: list[tuple[str, float]]) -> dict:
    """灰区仲裁：让 Claude 读原文决定归哪类（看所有候选，不只 top3）"""
    top3_str = "\n".join(f"  - {c}: embedding {s:.2f}" for c, s in top_candidates[:3])
    prompt = f"""新内容：
{text[:2000]}

所有候选类别：
{ALL_CATEGORIES_DESC}

embedding 给出的 top 3 分数（仅供参考）：
{top3_str}

请返回 JSON。"""
    raw = call_claude(prompt, system=GRAY_ZONE_SYSTEM_PROMPT, max_tokens=300)
    raw = raw.strip()
    import re
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    import re
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    return json.loads(raw)


# ══════════════════════════════════════════
# Kimi 联网搜索
# ══════════════════════════════════════════

KIMI_API_KEY = "sk-AwJmpC5sGDye5P9FdkwSJw3hpw2VbZ1VwxQ03yYWSzjhtrMa"
KIMI_BASE_URL = "https://api.moonshot.cn/v1/chat/completions"


def kimi_search(query: str, max_tokens: int = 1500) -> str:
    """用 Kimi 联网搜索，返回搜索结果文本"""
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json",
    }
    tools = [{"type": "builtin_function", "function": {"name": "$web_search"}}]

    # 第一轮：触发搜索
    messages = [{"role": "user", "content": query}]
    resp1 = requests.post(
        KIMI_BASE_URL,
        headers=headers,
        json={
            "model": "moonshot-v1-128k",
            "messages": messages,
            "max_tokens": max_tokens,
            "tools": tools,
        },
        timeout=120,
        verify=certifi.where(),
    )
    resp1.raise_for_status()
    data1 = resp1.json()
    assistant_msg = data1["choices"][0]["message"]

    # 如果没有 tool_calls，直接返回 content
    if not assistant_msg.get("tool_calls"):
        return assistant_msg.get("content", "")

    # 第二轮：把搜索结果回传，获取最终答案
    messages.append(assistant_msg)
    for tc in assistant_msg["tool_calls"]:
        messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": tc["function"]["arguments"],
        })

    resp2 = requests.post(
        KIMI_BASE_URL,
        headers=headers,
        json={
            "model": "moonshot-v1-128k",
            "messages": messages,
            "max_tokens": max_tokens,
            "tools": tools,
        },
        timeout=120,
        verify=certifi.where(),
    )
    resp2.raise_for_status()
    data2 = resp2.json()
    return data2["choices"][0]["message"].get("content", "")


def search_and_analyze(queries: list, system_prompt: str = "") -> str:
    """批量搜索多个关键词，合并结果后用 GPT-5.5 做结构化分析"""
    all_results = []
    for q in queries:
        try:
            result = kimi_search(q)
            if result:
                all_results.append(f"【搜索：{q}】\n{result}")
        except Exception as e:
            all_results.append(f"【搜索：{q}】失败: {e}")

    combined = "\n\n---\n\n".join(all_results)

    if not system_prompt:
        system_prompt = "你是一个金融分析助手。根据搜索结果，提取关键信息并结构化整理。"

    # 用 GPT-5.5 做结构化分析
    analysis = call_claude(
        prompt=f"以下是多个搜索结果，请结构化整理关键信息：\n\n{combined}",
        system=system_prompt,
        max_tokens=2000,
    )
    return analysis


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 快速测试
        text = """巴西央行最近加息周期告一段落，雷亚尔兑美元企稳在 5.0 附近。
从 FOF 角度，新兴市场配置里巴西的股债性价比开始好转，尤其是本币债。"""
        print("=== 生成元数据 ===")
        meta = generate_metadata(text)
        print(json.dumps(meta, ensure_ascii=False, indent=2))
