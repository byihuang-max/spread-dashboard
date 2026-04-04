# 2026-04-05 GitHub Pages 推送问题排查与修复

- 日期：2026-04-05
- 类型：运维经验 / 故障排查
- 标签：GitHub Pages, .nojekyll, Jekyll, 腾讯云, 推送, 前端发布

---

## 一、问题现象

push 成功后，前端页面一直没有更新。具体表现：
- `git push` 返回成功
- 远端 `main` 已是新 commit
- 但 `https://byihuang-max.github.io/spread-dashboard/` 仍是旧内容
- `timing-research/data/ml_exposure_score.json` 在 GitHub Pages 上返回 404

---

## 二、排查过程

### 1. 确认 push 是否真的成功
- 本地 HEAD = 远端 main = `0d6ce51` ✅
- raw 文件内容已是新的 ✅
- 问题不在 push，在发布层

### 2. 查 GitHub Pages build 状态
通过 GitHub API 查到：
- `pages.status = errored`
- 最新 build 状态一直是 `building`，超过 1 小时不变
- 说明 **GitHub Pages legacy build 卡住了**

### 3. 触发 rebuild 无效
- 通过 API `POST /repos/.../pages/builds` 触发 rebuild → 返回 201
- 但 build 仍然卡在 `building`
- 再 push 一次新 commit 也一样卡住

### 4. 定位根因
检查仓库目录大小：
- 仓库整体约 **1.8G**
- `env_fit/` 约 **1.1G**
- `venv/` 约 **264M**
- 根目录没有 `.nojekyll`

**根因：GitHub Pages 默认走 Jekyll legacy build，在处理这个 1.8G 大仓库时超时/卡死。**

---

## 三、修复方案

在仓库根目录加 `.nojekyll` 文件：

```bash
touch .nojekyll
git add .nojekyll
git commit -m "fix: disable jekyll for pages publish"
git push origin main
```

加了 `.nojekyll` 之后：
- Pages build 60 秒内完成
- `pages.status = built`
- 前端内容立刻更新

---

## 四、经验总结

### GitHub Pages 相关
- **大仓库必须加 `.nojekyll`**，否则 Jekyll legacy build 很容易超时卡死
- Pages build 状态 `building` 超过 15 分钟不变 → 判断为 GitHub 那边卡住，不是代码问题
- 连续两个不同 commit 都卡住 → 判断为 legacy build 链路故障，不是单次内容问题
- 排查顺序：先看 raw 文件是否已更新 → 再查 Pages build 状态 → 再看是否需要 `.nojekyll`

### 正式域名 vs GitHub Pages
- `dashboard.gamtfof.com` 走腾讯云服务器，不是 GitHub Pages
- 腾讯云需要 `git pull` 才能同步，不是实时的
- 工作日 08:20 / 17:00 定时任务会自动 pull
- 手动同步需要 SSH 进腾讯云（**代理开着时 SSH 不通，需先关代理**）

### 代理与 SSH 互斥（再次确认）
- 开代理时 SSH 到腾讯云 `Connection closed`
- 关代理后 SSH 可通
- push GitHub 需要代理，SSH 腾讯云需要关代理
- 操作顺序：关代理 → SSH → 开代理 → push

---

## 五、后续建议

1. 腾讯云服务器上的 `git pull` 依赖直连 GitHub，偶尔不稳定
2. 如需手动同步，关代理后 SSH 进去跑 `git pull origin main`
3. 如不急，等工作日定时任务自动同步即可
