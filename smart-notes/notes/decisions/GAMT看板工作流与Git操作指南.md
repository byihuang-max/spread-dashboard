# GAMT 看板工作流与 Git 操作指南

**创建时间**: 2026-03-31  
**类型**: 决策记录  
**标签**: #工作流 #Git #部署 #GAMT

---

## 核心结论

### Git Push 不需要代理
- 本地和腾讯云都用 **HTTPS + GitHub Personal Access Token**
- URL 格式：`https://username:token@github.com/repo.git`
- 国内直连 GitHub HTTPS 能通（虽然偶尔慢）
- **实测验证：关闭代理，git push 成功**

### 腾讯云每天自动 push
- 腾讯云 cron：08:20 / 17:00 / 18:00
- 每次跑完 `update_all.py` 后自动 `git push`
- commit 作者：`GAMT Server <server@gamtfof.com>`
- **所以不手动 push，前端也会每天更新**

### 本地 Mac 也在 push
- 本地 cron：17:00 / 18:00
- 也跑 `update_all.py` 并 push
- commit 作者：`byihuang-max`
- 作为备份和补跑机制

---

## 完整工作流

```
【数据更新层】

腾讯云 cron (08:20/17:00/18:00)
  ↓
python3 update_all.py
  ↓
拉数据 (Tushare/iFind/火富牛)
  ↓
生成 JSON/HTML
  ↓
git add + commit + push
  ↓
GitHub 仓库更新
  ↓
Cloudflare Pages 自动部署
  ↓
前端显示最新数据
```

---

## 什么时候需要手动 push？

### 需要手动 push 的情况
- 新增模块
- 改代码逻辑
- 改前端页面结构
- 改 HTML 模板
- 临时修复 bug
- 改 `module_registry.py`

### 不需要手动 push 的情况
- 日常数据更新（腾讯云自动处理）
- 定时任务正常运行（自动 commit + push）

---

## Git 操作口令表

### 最常用命令
| 你说 | 我做 |
|------|------|
| **"推 git"** | 直接 push 当前改动 |
| **"查 git"** | 检查未 push / 未 commit |
| **"上线这个模块"** | commit + push + 确认部署 |
| **"帮我 commit + push"** | 规范提交信息后 push |

### 标准流程
```bash
# 1. 检查改动
git status

# 2. 添加文件
git add -A

# 3. 提交
git commit -m "feat: 描述改动"

# 4. 推送
git push origin main

# 5. 确认
git log origin/main -3
```

---

## 三个角色分工

### 1. 本地 Mac
- **作用**: 开发台 / 调试台 / 备用生产机
- **负责**: 写代码、测试模块、生成数据、补跑任务
- **push 方式**: HTTPS + Token（不需要代理）

### 2. 腾讯云服务器
- **作用**: 生产服务器 + 后端服务器
- **负责**: 定时自动更新、生成数据、提供 API
- **push 方式**: HTTPS + Token（不需要代理）
- **IP**: 111.229.129.146

### 3. GitHub + Cloudflare Pages
- **GitHub**: 中央仓库 + 部署中转站
- **Pages**: 静态前端托管
- **触发**: GitHub push → 自动部署

---

## 常见误区澄清

### 误区 1: "push 必须开代理"
❌ 错误  
✅ 正确：HTTPS + Token 方式不需要代理

### 误区 2: "腾讯云 push 不上去"
❌ 错误  
✅ 正确：腾讯云每天都在成功 push

### 误区 3: "日志里的同步失败 = git push 失败"
❌ 错误  
✅ 正确：那是 SSH 同步到其他服务器失败，git push 本身成功

---

## 验证方法

### 检查本地和远端差异
```bash
cd ~/Desktop/gamt-dashboard
git log --oneline -5
git log origin/main --oneline -5
```

### 测试不开代理能否 push
```bash
unset http_proxy
unset https_proxy
git push --dry-run origin main
```

### 查看谁在 push
```bash
git log --format="%h %ai %an %s" -10
```

---

## 关键文件位置

- 本地项目：`~/Desktop/gamt-dashboard/`
- 腾讯云项目：`/home/ubuntu/gamt-dashboard/`
- 更新脚本：`server/update_all.py`
- 模块注册：`server/module_registry.py`
- GitHub 仓库：`https://github.com/byihuang-max/spread-dashboard`
- 前端地址：`https://gamt-dashboard.pages.dev/`
- 正式域名：`https://dashboard.gamtfof.com/`

---

## 记录时间
2026-03-31 19:12
