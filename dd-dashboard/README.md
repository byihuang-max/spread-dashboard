# DD Dashboard (尽调看板)

GAMT 私募基金尽调管理系统。管线看板 + 评分体系 + 附件解析 + 审计日志。

## 与 GAMT 看板的关系

- **母子关系**：尽调库是母，团队基金优选是子集
- 尽调完成 → 觉得好 → 推荐入库 → 出现在"团队基金优选"
- 审批权限统一在 GAMT admin.html 的"尽调管理"Tab

## 架构

```
dd-dashboard/
├── server.js              # Express 后端 (端口 3088)
├── package.json           # 依赖: express + multer
├── public/
│   ├── index.html         # 页面结构 (三视图)
│   ├── app.js             # 前端逻辑
│   └── styles.css         # 样式
├── data/
│   ├── funds.json         # 运行时数据库 (生产环境写入，不进 git)
│   └── funds_seed.json    # 种子数据 (27只基金，进 git)
├── uploads/               # 附件存储 (不进 git)
├── nginx-dd.conf          # Nginx 反代配置参考
├── dd-dashboard.service   # systemd 服务文件
└── README.md
```

## 部署

### 腾讯云

```bash
# 1. 安装依赖
cd /home/ubuntu/gamt-dashboard/dd-dashboard
npm install

# 2. 初始化数据（首次部署）
cp data/funds_seed.json data/funds.json
# 然后运行 Python 脚本设置 approvalStatus + stage 字段

# 3. 安装 systemd 服务
sudo cp dd-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dd-dashboard
sudo systemctl start dd-dashboard

# 4. Nginx 配置
# 在 /etc/nginx/sites-enabled/gamt-cn 的 server block 里加入 nginx-dd.conf 的内容
# 同样在 9876 端口的 server block 里加入（给 Tunnel 用）
sudo nginx -t && sudo systemctl reload nginx
```

### 本地开发

```bash
cd ~/Desktop/gamt-dashboard/dd-dashboard
npm install
node server.js
# 访问 http://localhost:3088
```

## API

### 原有 API（前端用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/funds | 获取所有基金 |
| GET | /api/funds/:id | 获取单个基金 |
| POST | /api/funds | 新增基金（直接入库，无需审批） |
| PUT | /api/funds/:id | 更新基金 |
| DELETE | /api/funds/:id | 删除基金 |
| PUT | /api/funds/:id/rating | 更新评分 |
| POST | /api/funds/:id/stage | 直接阶段流转（管理员用） |
| POST | /api/funds/:id/reminders | 添加提醒 |
| POST | /api/upload | 上传附件 |
| POST | /api/parse-file | 上传并解析文件 |

### 审批 API（admin.html 调用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/admin/dd-stats | 尽调库统计 |
| GET | /api/admin/pending | 待审批列表（新提交 + 阶段流转） |
| POST | /api/admin/dd-review | 审批新提交的尽调记录 |
| POST | /api/admin/dd-stage-review | 审批阶段流转申请 |
| POST | /api/funds/submit | 团队成员提交新尽调（需审批） |
| POST | /api/funds/:id/stage-request | 申请阶段流转（需审批） |
| GET | /api/funds/approved | 获取所有已通过的基金 |

## 审批流程

```
团队成员提交尽调记录
  → POST /api/funds/submit
  → approvalStatus = 'pending'
  → admin.html "尽调管理" Tab 显示待审批
  → 管理员通过/拒绝
  → 通过后在尽调看板可见

团队成员申请阶段流转
  → POST /api/funds/:id/stage-request
  → pendingStageChange 字段记录申请
  → admin.html 显示待审批
  → 管理员通过 → 执行流转
  → 管理员拒绝 → 清除申请
```

## 数据保护

- `data/funds.json` 是生产运行时数据，**不进 git**，不被 sync-to-cloud.sh 覆盖
- `data/funds_seed.json` 是种子数据，进 git，首次部署时复制为 funds.json
- `uploads/` 目录不进 git
