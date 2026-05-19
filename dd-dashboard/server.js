const express = require('express');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

const app = express();
const PORT = 3088;

// 中间件
app.use(express.json({ limit: '50mb' }));
// CORS - 允许 GAMT 主站跨域调用
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type,Authorization');
  if (req.method === 'OPTIONS') return res.sendStatus(200);
  next();
});
app.use(express.static(path.join(__dirname, 'public')));
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

// 文件上传配置
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, path.join(__dirname, 'uploads')),
  filename: (req, file, cb) => {
    const safeName = Buffer.from(file.originalname, 'latin1').toString('utf8');
    cb(null, Date.now() + '-' + safeName);
  }
});
const upload = multer({ storage, limits: { fileSize: 50 * 1024 * 1024 } });

// 数据文件路径
const DATA_FILE = path.join(__dirname, 'data', 'funds.json');

// 读取数据
function readData() {
  const raw = fs.readFileSync(DATA_FILE, 'utf8');
  return JSON.parse(raw);
}

// 写入数据
function writeData(data) {
  fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2), 'utf8');
}

// API: 获取所有基金
app.get('/api/funds', (req, res) => {
  const data = readData();
  res.json(data.funds);
});

// API: 获取单个基金
app.get('/api/funds/:id', (req, res) => {
  const data = readData();
  const fund = data.funds.find(f => f.id === req.params.id);
  if (!fund) return res.status(404).json({ error: 'Not found' });
  res.json(fund);
});

// API: 新增基金
app.post('/api/funds', (req, res) => {
  const data = readData();
  const newFund = req.body;
  newFund.id = newFund.id || `fund-${Date.now()}`;
  newFund.createdAt = new Date().toISOString().split('T')[0];
  newFund.updatedAt = newFund.createdAt;
  data.funds.push(newFund);
  writeData(data);
  res.json({ success: true, id: newFund.id });
});

// API: 更新基金（自动追加 auditLog）
app.put('/api/funds/:id', (req, res) => {
  const data = readData();
  const idx = data.funds.findIndex(f => f.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Not found' });
  const before = { ...data.funds[idx] };
  data.funds[idx] = { ...data.funds[idx], ...req.body, updatedAt: new Date().toISOString().split('T')[0] };
  // 追加审计日志
  if (!data.funds[idx].auditLog) data.funds[idx].auditLog = [];
  data.funds[idx].auditLog.push({
    id: `audit-${Date.now()}`,
    action: 'update',
    timestamp: new Date().toISOString(),
    operator: req.body._operator || '系统',
    detail: `更新基金信息`
  });
  writeData(data);
  res.json({ success: true });
});

// API: 删除基金
app.delete('/api/funds/:id', (req, res) => {
  const data = readData();
  data.funds = data.funds.filter(f => f.id !== req.params.id);
  writeData(data);
  res.json({ success: true });
});

// API: 更新基金评分
app.put('/api/funds/:id/rating', (req, res) => {
  const data = readData();
  const idx = data.funds.findIndex(f => f.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Not found' });

  const { strategyClarity, performanceStability, riskControl, teamBackground, compliance, transparency, ratedBy, ...rest } = req.body;
  const scores = { strategyClarity, performanceStability, riskControl, teamBackground, compliance, transparency };
  const validScores = Object.values(scores).filter(v => typeof v === 'number');
  const overall = validScores.length > 0 ? +(validScores.reduce((a, b) => a + b, 0) / validScores.length).toFixed(2) : 0;

  let grade = 'C';
  if (overall >= 4.5) grade = 'A+';
  else if (overall >= 4) grade = 'A';
  else if (overall >= 3.5) grade = 'B+';
  else if (overall >= 3) grade = 'B';
  else if (overall >= 2.5) grade = 'B-';
  else if (overall >= 2) grade = 'C+';

  data.funds[idx].rating = { ...scores, ...rest, overall, grade, ratedBy, ratedAt: new Date().toISOString().split('T')[0] };
  data.funds[idx].updatedAt = new Date().toISOString().split('T')[0];

  // 审计日志
  if (!data.funds[idx].auditLog) data.funds[idx].auditLog = [];
  data.funds[idx].auditLog.push({
    id: `audit-${Date.now()}`,
    action: 'rating',
    timestamp: new Date().toISOString(),
    operator: ratedBy || '系统',
    detail: `评分更新: overall=${overall}, grade=${grade}`
  });

  writeData(data);
  res.json({ success: true, rating: data.funds[idx].rating });
});

// API: 阶段流转
app.post('/api/funds/:id/stage', (req, res) => {
  const data = readData();
  const idx = data.funds.findIndex(f => f.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Not found' });

  const { to, reason, operator } = req.body;
  if (!to) return res.status(400).json({ error: 'Missing "to" stage' });

  const from = data.funds[idx].stage || 'initial';
  data.funds[idx].stage = to;
  if (!data.funds[idx].stageHistory) data.funds[idx].stageHistory = [];
  data.funds[idx].stageHistory.push({
    from,
    to,
    reason: reason || '',
    operator: operator || '系统',
    timestamp: new Date().toISOString()
  });
  data.funds[idx].updatedAt = new Date().toISOString().split('T')[0];

  // 审计日志
  if (!data.funds[idx].auditLog) data.funds[idx].auditLog = [];
  data.funds[idx].auditLog.push({
    id: `audit-${Date.now()}`,
    action: 'stage',
    timestamp: new Date().toISOString(),
    operator: operator || '系统',
    detail: `阶段流转: ${from} → ${to}${reason ? ' (' + reason + ')' : ''}`
  });

  writeData(data);
  res.json({ success: true, stage: to, from });
});

// API: 添加提醒
app.post('/api/funds/:id/reminders', (req, res) => {
  const data = readData();
  const idx = data.funds.findIndex(f => f.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Not found' });

  const { date, type, content, createdBy } = req.body;
  if (!date || !type) return res.status(400).json({ error: 'Missing required fields: date, type' });

  const reminder = {
    id: `reminder-${Date.now()}`,
    date,
    type,
    content: content || '',
    createdBy: createdBy || '系统',
    status: 'pending',
    createdAt: new Date().toISOString()
  };

  if (!data.funds[idx].reminders) data.funds[idx].reminders = [];
  data.funds[idx].reminders.push(reminder);
  data.funds[idx].updatedAt = new Date().toISOString().split('T')[0];

  // 审计日志
  if (!data.funds[idx].auditLog) data.funds[idx].auditLog = [];
  data.funds[idx].auditLog.push({
    id: `audit-${Date.now()}`,
    action: 'reminder_add',
    timestamp: new Date().toISOString(),
    operator: createdBy || '系统',
    detail: `添加提醒: ${type} - ${date}`
  });

  writeData(data);
  res.json({ success: true, reminder });
});

// API: 更新提醒状态
app.put('/api/funds/:id/reminders/:reminderId', (req, res) => {
  const data = readData();
  const idx = data.funds.findIndex(f => f.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Fund not found' });

  if (!data.funds[idx].reminders) return res.status(404).json({ error: 'Reminder not found' });
  const rIdx = data.funds[idx].reminders.findIndex(r => r.id === req.params.reminderId);
  if (rIdx === -1) return res.status(404).json({ error: 'Reminder not found' });

  const { status } = req.body;
  if (status) data.funds[idx].reminders[rIdx].status = status;
  data.funds[idx].reminders[rIdx].updatedAt = new Date().toISOString();
  data.funds[idx].updatedAt = new Date().toISOString().split('T')[0];

  writeData(data);
  res.json({ success: true, reminder: data.funds[idx].reminders[rIdx] });
});

// API: 获取所有待办提醒（跨基金）
app.get('/api/reminders/pending', (req, res) => {
  const data = readData();
  const results = [];
  for (const fund of data.funds) {
    if (fund.reminders && fund.reminders.length > 0) {
      for (const reminder of fund.reminders) {
        if (reminder.status === 'pending') {
          results.push({
            fundId: fund.id,
            fundName: fund.name || fund.fundName || fund.id,
            reminder
          });
        }
      }
    }
  }
  // 按日期排序
  results.sort((a, b) => (a.reminder.date || '').localeCompare(b.reminder.date || ''));
  res.json(results);
});

// API: 添加操作日志（内部用）
app.post('/api/funds/:id/audit', (req, res) => {
  const data = readData();
  const idx = data.funds.findIndex(f => f.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Not found' });

  const { action, operator, detail } = req.body;
  if (!action) return res.status(400).json({ error: 'Missing required field: action' });

  if (!data.funds[idx].auditLog) data.funds[idx].auditLog = [];
  const logEntry = {
    id: `audit-${Date.now()}`,
    action,
    timestamp: new Date().toISOString(),
    operator: operator || '系统',
    detail: detail || ''
  };
  data.funds[idx].auditLog.push(logEntry);
  data.funds[idx].updatedAt = new Date().toISOString().split('T')[0];

  writeData(data);
  res.json({ success: true, log: logEntry });
});

// API: 上传附件（返回完整文件信息对象）
app.post('/api/upload', upload.array('files', 10), (req, res) => {
  const files = req.files.map(f => ({
    originalName: Buffer.from(f.originalname, 'latin1').toString('utf8'),
    filename: f.filename,
    path: `/uploads/${f.filename}`,
    size: f.size
  }));
  res.json({ success: true, files });
});

// API: 智能解析上传的文件（提取文本内容供前端AI解析）
app.post('/api/parse-file', upload.single('file'), async (req, res) => {
  if (!req.file) return res.status(400).json({ error: 'No file uploaded' });

  const safeName = Buffer.from(req.file.originalname, 'latin1').toString('utf8');
  const ext = safeName.split('.').pop().toLowerCase();
  const filePath = req.file.path;

  let textContent = '';

  try {
    if (ext === 'pdf') {
      // 尝试用 pdftotext 提取
      textContent = await new Promise((resolve, reject) => {
        exec(`pdftotext "${filePath}" -`, { maxBuffer: 10 * 1024 * 1024 }, (err, stdout) => {
          if (err) {
            // fallback: 读取原始内容的前几KB作为提示
            resolve(`[PDF文件: ${safeName}, 无法自动提取文本，请手动填写信息]`);
          } else {
            resolve(stdout.slice(0, 50000)); // 限制50K字符
          }
        });
      });
    } else if (['doc', 'docx'].includes(ext)) {
      // 尝试用 textutil (macOS) 或 antiword
      textContent = await new Promise((resolve, reject) => {
        exec(`textutil -convert txt -stdout "${filePath}" 2>/dev/null || cat "${filePath}" 2>/dev/null | strings | head -500`, 
          { maxBuffer: 10 * 1024 * 1024 }, (err, stdout) => {
          if (err || !stdout.trim()) {
            resolve(`[Word文件: ${safeName}, 无法自动提取文本]`);
          } else {
            resolve(stdout.slice(0, 50000));
          }
        });
      });
    } else if (['txt', 'md'].includes(ext)) {
      textContent = fs.readFileSync(filePath, 'utf8').slice(0, 50000);
    } else {
      textContent = `[文件: ${safeName}, 格式 ${ext} 暂不支持自动解析]`;
    }

    res.json({
      success: true,
      file: {
        originalName: safeName,
        filename: req.file.filename,
        path: `/uploads/${req.file.filename}`,
        size: req.file.size
      },
      textContent: textContent
    });
  } catch (err) {
    res.json({
      success: true,
      file: {
        originalName: safeName,
        filename: req.file.filename,
        path: `/uploads/${req.file.filename}`,
        size: req.file.size
      },
      textContent: `[解析失败: ${err.message}]`
    });
  }
});

// ===== 审批流程 API =====

// 获取待审批列表（新提交 + 阶段流转申请）
app.get('/api/admin/pending', (req, res) => {
  const data = readData();
  const pending = [];

  for (const fund of data.funds) {
    // 新提交待审批（status=pending）
    if (fund.approvalStatus === 'pending') {
      pending.push({
        type: 'new_submission',
        fundId: fund.id,
        fundName: fund.company?.shortName || fund.company?.name || fund.id,
        submittedBy: fund.submittedBy || fund.dueDiligence?.analyst || '未知',
        submittedAt: fund.submittedAt || fund.createdAt,
        stage: fund.stage,
        strategyType: fund.strategies?.[0]?.type || '未分类',
        detail: `新增尽调记录: ${fund.company?.name || fund.id}`
      });
    }

    // 阶段流转待审批
    if (fund.pendingStageChange) {
      pending.push({
        type: 'stage_change',
        fundId: fund.id,
        fundName: fund.company?.shortName || fund.company?.name || fund.id,
        submittedBy: fund.pendingStageChange.requestedBy || '未知',
        submittedAt: fund.pendingStageChange.requestedAt,
        currentStage: fund.stage,
        targetStage: fund.pendingStageChange.to,
        reason: fund.pendingStageChange.reason || '',
        detail: `阶段流转: ${fund.stage} → ${fund.pendingStageChange.to}`
      });
    }
  }

  // 按时间倒序
  pending.sort((a, b) => (b.submittedAt || '').localeCompare(a.submittedAt || ''));
  res.json({ pending, total: pending.length });
});

// 获取尽调库统计
app.get('/api/admin/dd-stats', (req, res) => {
  const data = readData();
  const funds = data.funds || [];
  const stats = {
    total: funds.length,
    byStage: {},
    pending: funds.filter(f => f.approvalStatus === 'pending').length,
    pendingStageChanges: funds.filter(f => f.pendingStageChange).length,
    approved: funds.filter(f => f.approvalStatus !== 'pending' && f.approvalStatus !== 'rejected').length,
    rejected: funds.filter(f => f.approvalStatus === 'rejected').length
  };
  const stageLabels = { initial: '初步接触', communicating: '沟通中', diligenced: '已尽调', approved: '已入库', invested: '已投资', rejected: '已否决' };
  for (const [key, label] of Object.entries(stageLabels)) {
    stats.byStage[key] = { label, count: funds.filter(f => f.stage === key).length };
  }
  res.json(stats);
});

// 审批新提交的尽调记录
app.post('/api/admin/dd-review', (req, res) => {
  const { fundId, action, reviewNote, reviewedBy } = req.body;
  if (!fundId || !action) return res.status(400).json({ error: 'Missing fundId or action' });
  if (!['approve', 'reject'].includes(action)) return res.status(400).json({ error: 'Invalid action' });

  const data = readData();
  const idx = data.funds.findIndex(f => f.id === fundId);
  if (idx === -1) return res.status(404).json({ error: 'Fund not found' });

  const fund = data.funds[idx];
  if (action === 'approve') {
    fund.approvalStatus = 'approved';
  } else {
    fund.approvalStatus = 'rejected';
  }
  fund.reviewedBy = reviewedBy || 'admin';
  fund.reviewedAt = new Date().toISOString();
  fund.reviewNote = reviewNote || '';
  fund.updatedAt = new Date().toISOString().split('T')[0];

  // 审计日志
  if (!fund.auditLog) fund.auditLog = [];
  fund.auditLog.push({
    id: `audit-${Date.now()}`,
    action: action === 'approve' ? 'submission_approved' : 'submission_rejected',
    timestamp: new Date().toISOString(),
    operator: reviewedBy || 'admin',
    detail: `尽调记录${action === 'approve' ? '通过' : '拒绝'}${reviewNote ? ': ' + reviewNote : ''}`
  });

  writeData(data);
  res.json({ ok: true, msg: action === 'approve' ? '已通过' : '已拒绝' });
});

// 审批阶段流转
app.post('/api/admin/dd-stage-review', (req, res) => {
  const { fundId, action, reviewNote, reviewedBy } = req.body;
  if (!fundId || !action) return res.status(400).json({ error: 'Missing fundId or action' });
  if (!['approve', 'reject'].includes(action)) return res.status(400).json({ error: 'Invalid action' });

  const data = readData();
  const idx = data.funds.findIndex(f => f.id === fundId);
  if (idx === -1) return res.status(404).json({ error: 'Fund not found' });

  const fund = data.funds[idx];
  if (!fund.pendingStageChange) return res.status(400).json({ error: 'No pending stage change' });

  const from = fund.stage;
  const to = fund.pendingStageChange.to;

  if (action === 'approve') {
    // 执行阶段流转
    fund.stage = to;
    if (!fund.stageHistory) fund.stageHistory = [];
    fund.stageHistory.push({
      from,
      to,
      reason: fund.pendingStageChange.reason || '',
      operator: fund.pendingStageChange.requestedBy || '系统',
      approvedBy: reviewedBy || 'admin',
      timestamp: new Date().toISOString()
    });
  }

  // 清除待审批状态
  delete fund.pendingStageChange;
  fund.updatedAt = new Date().toISOString().split('T')[0];

  // 审计日志
  if (!fund.auditLog) fund.auditLog = [];
  fund.auditLog.push({
    id: `audit-${Date.now()}`,
    action: action === 'approve' ? 'stage_change_approved' : 'stage_change_rejected',
    timestamp: new Date().toISOString(),
    operator: reviewedBy || 'admin',
    detail: `阶段流转${action === 'approve' ? '通过' : '拒绝'}: ${from} → ${to}${reviewNote ? ' (' + reviewNote + ')' : ''}`
  });

  writeData(data);
  res.json({ ok: true, msg: action === 'approve' ? `已通过: ${from} → ${to}` : '已拒绝流转' });
});

// 提交阶段流转申请（团队成员用）
app.post('/api/funds/:id/stage-request', (req, res) => {
  const data = readData();
  const idx = data.funds.findIndex(f => f.id === req.params.id);
  if (idx === -1) return res.status(404).json({ error: 'Not found' });

  const { to, reason, requestedBy } = req.body;
  if (!to) return res.status(400).json({ error: 'Missing target stage' });

  const fund = data.funds[idx];
  if (fund.pendingStageChange) {
    return res.status(400).json({ error: '已有待审批的阶段流转申请' });
  }

  fund.pendingStageChange = {
    to,
    reason: reason || '',
    requestedBy: requestedBy || '团队成员',
    requestedAt: new Date().toISOString()
  };
  fund.updatedAt = new Date().toISOString().split('T')[0];

  // 审计日志
  if (!fund.auditLog) fund.auditLog = [];
  fund.auditLog.push({
    id: `audit-${Date.now()}`,
    action: 'stage_change_requested',
    timestamp: new Date().toISOString(),
    operator: requestedBy || '团队成员',
    detail: `申请阶段流转: ${fund.stage} → ${to}${reason ? ' (' + reason + ')' : ''}`
  });

  writeData(data);
  res.json({ ok: true, msg: '阶段流转申请已提交，等待管理员审批' });
});

// 提交新尽调记录（团队成员用，需审批）
app.post('/api/funds/submit', (req, res) => {
  const data = readData();
  const newFund = req.body;
  newFund.id = newFund.id || `fund-${Date.now()}`;
  newFund.createdAt = new Date().toISOString().split('T')[0];
  newFund.updatedAt = newFund.createdAt;
  newFund.approvalStatus = 'pending';
  newFund.submittedBy = newFund.submittedBy || newFund.dueDiligence?.analyst || '团队成员';
  newFund.submittedAt = new Date().toISOString();
  newFund.stage = newFund.stage || 'initial';

  data.funds.push(newFund);
  writeData(data);
  res.json({ ok: true, id: newFund.id, msg: '尽调记录已提交，等待管理员审批' });
});

// 获取所有已审批通过的基金（供 GAMT 主站调用）
app.get('/api/funds/approved', (req, res) => {
  const data = readData();
  const approved = data.funds.filter(f => f.approvalStatus !== 'pending' && f.approvalStatus !== 'rejected');
  res.json(approved);
});

app.listen(PORT, () => {
  console.log(`尽调看板服务已启动: http://localhost:${PORT}`);
});
