# 配置多个 Telegram AI 员工

**日期：** 2026-03-07  
**状态：** 配置完成，待重启验证

---

## 需求背景

Roni 想要3个独立的 AI 员工，每个有不同的职责和人设：
- **员工1（Eva）**：FOF 投资顾问 - 每天帮思考 FOF 整体投资思路、策略探讨
- **员工2（Leijun）**：策略分析师 - 分析不同策略的净值和表现
- **员工3（Musk）**：量化交易员 - 接收交易思路，实现量化交易代码

飞书无法实现多个独立 AI 身份，所以转向 Telegram。

---

## 创建的 Telegram Bot

| 员工 | Bot 用户名 | Token | 模型 |
|------|-----------|-------|------|
| Eva | eva_fof_bot | 8702748600:AAG1DcfnY4ls8y5k00-h-aEa5QHpyUZH4a0 | Claude Opus 4.6 |
| Leijun | leijun_quant_bot | 8711572283:AAHL7vkAbZdltbOmmvSWoOIL9zFyBUzx7UM | GPT-5.3-codex |
| Musk | musk_trader_bot | 8787904751:AAF_39sx3CEXvEINS2gwP5hO5iT_bWuTFFI | Claude Opus 4.6 |

---

## 配置修改

**文件：** `~/.openclaw/openclaw.json`  
**备份：** `~/.openclaw/openclaw.json.backup`

修改了 `channels.telegram` 配置，参考 feishu 的 accounts 结构：

```json
"telegram": {
  "enabled": true,
  "dmPolicy": "pairing",
  "groupPolicy": "allowlist",
  "streamMode": "partial",
  "accounts": {
    "eva": {
      "botToken": "8702748600:AAG1DcfnY4ls8y5k00-h-aEa5QHpyUZH4a0",
      "model": "aicanapi/claude-opus-4-6"
    },
    "leijun": {
      "botToken": "8711572283:AAHL7vkAbZdltbOmmvSWoOIL9zFyBUzx7UM",
      "model": "aicanopenai/gpt-5.3-codex"
    },
    "musk": {
      "botToken": "8787904751:AAF_39sx3CEXvEINS2gwP5hO5iT_bWuTFFI",
      "model": "aicanapi/claude-opus-4-6"
    }
  }
}
```

---

## 待完成任务

### 1. 重启 OpenAWS
```bash
openclaw gateway restart
```

### 2. 在 Telegram 中启动 bot
搜索并点击 Start：
- @eva_fof_bot
- @leijun_quant_bot
- @musk_trader_bot

### 3. 配置角色定义
为每个员工创建独立的角色配置，让他们有不同的"人设"和职责。

可能的方案：
- 在 workspace 下创建子文件夹（eva/, leijun/, musk/）
- 每个文件夹有独立的 SOUL.md 定义角色
- 或者使用 OpenAWS 的 agents 配置

---

## 注意事项

- ⚠️ Token 已暴露，如需安全可找 BotFather 重新生成
- 配置文件已备份，如有问题可回滚
- OpenAWS 的 telegram plugin 是否支持 accounts 结构需验证
