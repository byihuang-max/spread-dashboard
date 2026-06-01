# Kimi 联网搜索 Skill

## 触发条件

当需要联网搜索验证信息时触发：
- "搜一下"、"查一下"、"联网搜索"、"kimi搜索"
- 需要验证数据口径、政策变化、市场事件
- 需要获取最新公开信息

## 用法

### Python 调用

```python
import sys
sys.path.insert(0, '/Users/apple/Desktop/gamt-dashboard/skills/kimi-search')
from kimi_search import search, search_batch

# 单条搜索
result = search("2024年北向资金披露规则变化")

# 批量搜索
results = search_batch(["query1", "query2"])
```

### 命令行

```bash
cd ~/Desktop/gamt-dashboard/skills/kimi-search
python3 kimi_search.py "你的搜索问题"
```

## 注意事项

- 频率限制：批量搜索间隔 1.5s，遇到 429 自动退避
- 模型：moonshot-v1-128k（128k 上下文，适合长搜索结果）
- 联网搜索通过 Kimi 的 `$web_search` builtin tool 实现
- 密钥在 `config/api_keys.json`
