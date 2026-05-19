// DD Dashboard - Due Diligence Tracking for Private Funds
// Pipeline/Kanban + Dashboard + List views

let allFunds = [];
let filteredFunds = [];
let uploadedFiles = [];
let currentView = 'pipeline';
let pendingReminders = [];
let remindersCollapsed = false;

const STAGES = {
  initial: { label: '初步接触', color: '#6b7280', icon: '🔍' },
  communicating: { label: '沟通中', color: '#f59e0b', icon: '💬' },
  diligenced: { label: '已尽调', color: '#3b82f6', icon: '📋' },
  approved: { label: '已入库', color: '#8b5cf6', icon: '✅' },
  invested: { label: '已投资', color: '#10b981', icon: '💰' },
  rejected: { label: '已否决', color: '#ef4444', icon: '❌' }
};

document.addEventListener('DOMContentLoaded', () => {
  loadFunds();
  loadPendingReminders();
  document.getElementById('searchInput').addEventListener('input', handleSearch);
});

async function loadFunds() {
  try {
    const res = await fetch('/api/funds');
    allFunds = await res.json();
    filteredFunds = allFunds;
    renderCurrentView();
  } catch (err) {
    console.error('加载失败:', err);
  }
}

function renderCurrentView() {
  if (currentView === 'pipeline') renderPipeline();
  else if (currentView === 'dashboard') renderDashboard();
  else if (currentView === 'list') renderGrid();
}

function handleSearch() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  if (!search) {
    filteredFunds = allFunds;
  } else {
    filteredFunds = allFunds.filter(fund => {
      const text = (fund.company.name + ' ' + (fund.company.shortName || '') + ' ' +
        (fund.tags || []).join(' ') + ' ' +
        (fund.strategies || []).map(s => s.type + ' ' + s.name).join(' ')).toLowerCase();
      return text.includes(search);
    });
  }
  renderCurrentView();
}

// ===== 视图切换 =====
function switchView(view) {
  currentView = view;
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  const viewEl = document.getElementById(`view-${view}`);
  if (viewEl) viewEl.classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelector(`[data-view="${view}"]`)?.classList.add('active');

  const titles = { pipeline: '尽调看板', dashboard: '尽调仪表盘', list: '全部管理人' };
  document.getElementById('pageTitle').textContent = titles[view] || '尽调看板';

  renderCurrentView();
}

function filterByStrategy(strategy) {
  switchView('list');
  const el = document.getElementById('filterStrategy');
  if (el) {
    // 尝试精确匹配option，如果没有就用搜索框
    const options = Array.from(el.options).map(o => o.value);
    if (options.includes(strategy)) {
      el.value = strategy;
    } else {
      el.value = '';
      document.getElementById('searchInput').value = strategy;
    }
  }
  applyFilters();
}

// ===== Pipeline/Kanban View =====
function renderPipeline() {
  const container = document.getElementById('pipelineContainer');
  if (!container) return;

  let html = '';
  Object.entries(STAGES).forEach(([stageKey, stageInfo]) => {
    const stageFunds = filteredFunds.filter(f => f.stage === stageKey);
    html += `<div class="pipeline-column">`;
    html += `<div class="pipeline-column-header">`;
    html += `<div class="pipeline-column-title">`;
    html += `<span class="pipeline-icon">${stageInfo.icon}</span>`;
    html += `<span>${stageInfo.label}</span>`;
    html += `<span class="pipeline-count">${stageFunds.length}</span>`;
    html += `</div></div>`;
    html += `<div class="pipeline-cards">`;

    if (stageFunds.length === 0) {
      html += `<div class="pipeline-empty">暂无项目</div>`;
    } else {
      stageFunds.forEach(fund => {
        const strategies = (fund.strategies || []).map(s => s.type).filter(Boolean);
        const updatedAt = fund.updatedAt ? new Date(fund.updatedAt).toLocaleDateString('zh-CN') : '-';
        const hasHighRisk = fund.risks?.some(r => r.level === '高');

        html += `<div class="pipeline-card" onclick="showDetail('${fund.id}')">`;
        html += `<div class="pipeline-card-header">`;
        html += `<div class="pipeline-card-name">${fund.company.shortName || fund.company.name}</div>`;
        if (hasHighRisk) html += `<span class="pipeline-risk-dot" title="含高风险项"></span>`;
        html += `</div>`;

        if (strategies.length) {
          html += `<div class="pipeline-card-tags">`;
          strategies.slice(0, 3).forEach(s => {
            html += `<span class="pipeline-tag">${s}</span>`;
          });
          html += `</div>`;
        }

        html += `<div class="pipeline-card-footer">`;
        html += `<span class="pipeline-card-date">${updatedAt}</span>`;
        if (fund.company.actualScale) {
          html += `<span class="pipeline-card-scale">${fund.company.actualScale}</span>`;
        }
        html += `</div>`;
        html += `</div>`;
      });
    }

    html += `</div></div>`;
  });

  container.innerHTML = html;
}

// ===== 仪表盘 =====
function renderDashboard() {
  const stats = {
    total: allFunds.length,
    initial: allFunds.filter(f => f.stage === 'initial').length,
    communicating: allFunds.filter(f => f.stage === 'communicating').length,
    diligenced: allFunds.filter(f => f.stage === 'diligenced').length,
    approved: allFunds.filter(f => f.stage === 'approved').length,
    invested: allFunds.filter(f => f.stage === 'invested').length,
    rejected: allFunds.filter(f => f.stage === 'rejected').length,
    highRisk: allFunds.filter(f => f.risks?.some(r => r.level === '高')).length
  };

  const statsRow = document.getElementById('statsRow');
  if (statsRow) {
    statsRow.innerHTML = `
      <div class="stat-card">
        <div class="stat-label">管理人总数</div>
        <div class="stat-value">${stats.total}</div>
        <div class="stat-sub">已录入尽调库</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">沟通中</div>
        <div class="stat-value" style="color:var(--orange)">${stats.communicating}</div>
        <div class="stat-sub">正在沟通跟进</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已尽调</div>
        <div class="stat-value" style="color:var(--blue)">${stats.diligenced}</div>
        <div class="stat-sub">完成现场/远程尽调</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已入库</div>
        <div class="stat-value" style="color:var(--purple)">${stats.approved}</div>
        <div class="stat-sub">通过入库评审</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">已投资</div>
        <div class="stat-value" style="color:var(--green)">${stats.invested}</div>
        <div class="stat-sub">实际配置资金</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">高风险项</div>
        <div class="stat-value" style="color:var(--red)">${stats.highRisk}</div>
        <div class="stat-sub">含高风险标记</div>
      </div>
    `;
  }

  // 表格
  const sorted = [...allFunds].sort((a, b) =>
    new Date(b.updatedAt || b.createdAt || 0) - new Date(a.updatedAt || a.createdAt || 0)
  );

  const tbody = document.getElementById('fundsTableBody');
  if (tbody) {
    tbody.innerHTML = sorted.map(fund => {
      const maxRisk = fund.risks?.find(r => r.level === '高') ? '高' :
                      fund.risks?.find(r => r.level === '中') ? '中' : '低';
      const stageInfo = STAGES[fund.stage] || STAGES.initial;
      return `
        <tr onclick="showDetail('${fund.id}')">
          <td><strong>${fund.company.shortName || fund.company.name}</strong></td>
          <td>${fund.strategies?.map(s => s.type).filter(Boolean).join(', ') || '-'}</td>
          <td>${fund.company.actualScale || '-'}</td>
          <td><span class="risk-badge risk-${maxRisk}">${maxRisk}</span></td>
          <td><span class="stage-badge stage-${fund.stage}">${stageInfo.label}</span></td>
          <td>${fund.updatedAt ? new Date(fund.updatedAt).toLocaleDateString('zh-CN') : '-'}</td>
        </tr>
      `;
    }).join('');
  }
}

// ===== 待办提醒 =====
async function loadPendingReminders() {
  try {
    const res = await fetch('/api/reminders/pending');
    pendingReminders = await res.json();
    renderRemindersPanel();
    // Re-render current view to update dots
    renderCurrentView();
  } catch (err) {
    console.error('加载待办提醒失败:', err);
    pendingReminders = [];
  }
}

function renderRemindersPanel() {
  let panel = document.getElementById('remindersPanel');
  if (!panel) {
    // Create the panel and insert before fundsGrid
    const gridContainer = document.getElementById('fundsGrid');
    if (!gridContainer) return;
    panel = document.createElement('div');
    panel.id = 'remindersPanel';
    gridContainer.parentNode.insertBefore(panel, gridContainer);
  }

  if (!pendingReminders.length) {
    panel.innerHTML = '';
    panel.style.display = 'none';
    return;
  }

  panel.style.display = '';
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const sevenDaysLater = new Date(today);
  sevenDaysLater.setDate(sevenDaysLater.getDate() + 7);

  const itemsHtml = remindersCollapsed ? '' : pendingReminders.map(r => {
    const rDate = new Date(r.date);
    rDate.setHours(0, 0, 0, 0);
    let dateStyle = '';
    let statusLabel = '';
    if (rDate < today) {
      dateStyle = 'color:#ef4444;font-weight:600;';
      statusLabel = '<span style="background:#ef4444;color:#fff;font-size:11px;padding:1px 6px;border-radius:4px;margin-left:6px;">已过期</span>';
    } else if (rDate <= sevenDaysLater) {
      dateStyle = 'color:#f59e0b;font-weight:600;';
      statusLabel = '<span style="background:#f59e0b;color:#fff;font-size:11px;padding:1px 6px;border-radius:4px;margin-left:6px;">即将到期</span>';
    }

    const fundName = r.fundName || '未知基金';
    return `<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;background:rgba(255,255,255,0.03);border-radius:8px;margin-bottom:6px;border:1px solid rgba(255,255,255,0.06);">
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <a href="#" onclick="event.preventDefault();showDetail('${r.fundId}')" style="color:var(--accent);font-weight:600;text-decoration:none;font-size:13px;">${fundName}</a>
          <span style="font-size:12px;color:var(--text-muted);background:rgba(255,255,255,0.06);padding:2px 8px;border-radius:4px;">${r.type || '提醒'}</span>
          <span style="font-size:12px;${dateStyle}">${r.date}${statusLabel}</span>
        </div>
        <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">${r.content || ''}</div>
      </div>
      <button onclick="completeReminder('${r.fundId}', '${r.id}')" style="flex-shrink:0;margin-left:12px;padding:4px 12px;font-size:12px;background:var(--green);color:#fff;border:none;border-radius:6px;cursor:pointer;transition:opacity 0.2s;" onmouseover="this.style.opacity='0.8'" onmouseout="this.style.opacity='1'">完成</button>
    </div>`;
  }).join('');

  panel.innerHTML = `<div style="margin-bottom:16px;background:var(--card-bg);border-radius:12px;border:1px solid var(--border);padding:16px;">
    <div style="display:flex;align-items:center;justify-content:space-between;cursor:pointer;" onclick="toggleRemindersPanel()">
      <div style="font-size:15px;font-weight:700;color:var(--text-primary);">📋 待办提醒 (${pendingReminders.length})</div>
      <span style="font-size:12px;color:var(--text-muted);">${remindersCollapsed ? '▶ 展开' : '▼ 收起'}</span>
    </div>
    ${!remindersCollapsed ? `<div style="margin-top:12px;">${itemsHtml}</div>` : ''}
  </div>`;
}

function toggleRemindersPanel() {
  remindersCollapsed = !remindersCollapsed;
  renderRemindersPanel();
}

async function completeReminder(fundId, reminderId) {
  try {
    const res = await fetch(`/api/funds/${fundId}/reminders/${reminderId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'done' })
    });
    const result = await res.json();
    if (result.success !== false) {
      // Remove from local list and re-render
      pendingReminders = pendingReminders.filter(r => r.id !== reminderId);
      renderRemindersPanel();
      renderCurrentView();
    }
  } catch (err) {
    alert('操作失败');
  }
}

// Helper: check if a fund has pending reminders
function fundHasPendingReminder(fundId) {
  return pendingReminders.some(r => r.fundId === fundId);
}

// Helper: get rating badge for a fund
function getRatingBadge(fund) {
  const score = fund.investmentScore?.overall;
  if (score == null) return '';
  let grade, color;
  if (score >= 80) { grade = 'A'; color = '#10b981'; }
  else if (score >= 60) { grade = 'B'; color = '#3b82f6'; }
  else if (score >= 40) { grade = 'C'; color = '#f59e0b'; }
  else { grade = 'D'; color = '#ef4444'; }
  return `<span style="display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:6px;background:${color};color:#fff;font-size:11px;font-weight:700;margin-left:6px;">${grade}</span>`;
}

// ===== 卡片网格 (List View) =====
function renderGrid() {
  const container = document.getElementById('fundsGrid');
  if (!container) return;

  // Render reminders panel above grid
  renderRemindersPanel();

  if (filteredFunds.length === 0) {
    container.innerHTML = '<div style="text-align:center;padding:60px;color:var(--text-muted);grid-column:1/-1;">暂无匹配数据</div>';
    return;
  }

  container.innerHTML = filteredFunds.map(fund => {
    const stageInfo = STAGES[fund.stage] || STAGES.initial;
    const hasPending = fundHasPendingReminder(fund.id);
    const ratingBadge = getRatingBadge(fund);
    return `
      <div class="fund-card" onclick="showDetail('${fund.id}')" style="position:relative;">
        ${hasPending ? '<span style="position:absolute;top:12px;right:12px;width:10px;height:10px;background:#ef4444;border-radius:50%;box-shadow:0 0 6px rgba(239,68,68,0.6);"></span>' : ''}
        <div class="fund-card-header">
          <div>
            <h3>${fund.company.shortName || fund.company.name}${ratingBadge}</h3>
            <div class="sub-name">${fund.company.name}</div>
          </div>
          <span class="stage-badge stage-${fund.stage}">${stageInfo.label}</span>
        </div>
        <div class="meta-row">
          <span>📅 ${fund.company.established || '-'}</span>
          <span>💰 ${fund.company.actualScale || '-'}</span>
          <span>👥 ${fund.company.teamSize || '-'}人</span>
        </div>
        <div class="tags-row">
          ${(fund.tags || []).slice(0, 4).map(t => `<span class="tag">${t}</span>`).join('')}
        </div>
      </div>
    `;
  }).join('');
}

// ===== 筛选 =====
function applyFilters() {
  const search = document.getElementById('searchInput').value.toLowerCase();
  const strategy = document.getElementById('filterStrategy')?.value || '';
  const stage = document.getElementById('filterStage')?.value || '';
  const risk = document.getElementById('filterRisk')?.value || '';

  filteredFunds = allFunds.filter(fund => {
    if (search) {
      const text = (fund.company.name + ' ' + (fund.company.shortName || '') + ' ' +
        (fund.tags || []).join(' ') + ' ' +
        (fund.strategies || []).map(s => s.type + ' ' + s.name).join(' ')).toLowerCase();
      if (!text.includes(search)) return false;
    }
    if (strategy) {
      const matched = fund.strategies?.some(s => {
        const t = (s.type || '').toLowerCase();
        const n = (s.name || '').toLowerCase();
        const kw = strategy.toLowerCase();
        return t.includes(kw) || n.includes(kw) || t === kw;
      });
      if (!matched) return false;
    }
    if (stage && fund.stage !== stage) return false;
    if (risk && !fund.risks?.some(r => r.level === risk)) return false;
    return true;
  });

  renderCurrentView();
}

function resetFilters() {
  document.getElementById('searchInput').value = '';
  const els = ['filterStrategy', 'filterStage', 'filterRisk'];
  els.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  filteredFunds = allFunds;
  renderCurrentView();
}

// ===== 详情模态框 =====
async function showDetail(id) {
  const fund = allFunds.find(f => f.id === id);
  if (!fund) return;

  document.getElementById('detailTitle').textContent = fund.company.shortName || fund.company.name;

  let html = '';

  // ===== DD Summary Card（一页纸概览）=====
  const stageInfo = STAGES[fund.stage] || STAGES.initial;
  const ratingInfo = fund.rating || {};
  const ratingGrade = ratingInfo.grade || '未评';
  const ratingColors = { 'A': '#10b981', 'B': '#3b82f6', 'C': '#f59e0b', 'D': '#ef4444', '未评': '#6b7280' };
  const ratingColor = ratingColors[ratingGrade] || '#6b7280';
  const summaryStrategy = fund.strategies?.[0];
  const strategyOneLiner = summaryStrategy ? `${summaryStrategy.name}${summaryStrategy.type ? ' · ' + summaryStrategy.type : ''}` : '暂无策略';
  const topHighlights = (fund.highlights || []).slice(0, 2);
  const topRisk = fund.risks?.[0];
  const lastDDDate = fund.dueDiligence?.date || '-';

  html += `<div style="background:linear-gradient(135deg, #1e293b 0%, #334155 100%);border-radius:12px;padding:20px 24px;margin-bottom:20px;border:1px solid rgba(99,102,241,0.3);">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;">
      <div style="display:flex;align-items:center;gap:12px;">
        <span style="font-size:20px;font-weight:700;color:#f1f5f9;">${fund.company.shortName || fund.company.name}</span>
        <span style="background:${stageInfo.color};color:#fff;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">${stageInfo.icon} ${stageInfo.label}</span>
        <span style="background:${ratingColor};color:#fff;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:700;">${ratingGrade}级</span>
      </div>
      <div style="font-size:13px;color:#94a3b8;">${strategyOneLiner}</div>
    </div>
    ${topHighlights.length ? `<div style="margin-top:12px;display:flex;gap:16px;flex-wrap:wrap;">
      ${topHighlights.map(h => `<span style="background:rgba(16,185,129,0.15);color:#6ee7b7;padding:4px 12px;border-radius:8px;font-size:12px;">✨ ${h}</span>`).join('')}
    </div>` : ''}
    <div style="margin-top:12px;display:flex;align-items:center;gap:24px;flex-wrap:wrap;font-size:12px;color:#94a3b8;">
      ${topRisk ? `<span style="color:#fca5a5;">⚠️ ${topRisk.level}风险: ${topRisk.content.slice(0, 30)}${topRisk.content.length > 30 ? '...' : ''}</span>` : ''}
      <span>📅 最近尽调: ${lastDDDate}</span>
    </div>
  </div>`;

  // Stage transition buttons
  html += `<div class="detail-section stage-section">
    <div class="detail-section-title">当前阶段</div>
    <div class="stage-current">
      <span class="stage-badge stage-${fund.stage}" style="font-size:14px;padding:6px 16px;">${stageInfo.icon} ${stageInfo.label}</span>
    </div>
    <div class="stage-transitions">
      ${Object.entries(STAGES).filter(([key]) => key !== fund.stage).map(([key, info]) =>
        `<button class="stage-btn stage-btn-${key}" onclick="changeStage('${fund.id}', '${key}')">${info.icon} 转为${info.label}</button>`
      ).join('')}
    </div>
  </div>`;

  // 投资评分（增强版 - 5维度评分模块）
  {
    const score = fund.investmentScore || {};
    const hasScore = score.overall !== undefined;
    const scoreClass = score.overall >= 80 ? 'score-high' : score.overall >= 60 ? 'score-mid' : 'score-low';
    const scoreItems = [
      { label: 'Alpha能力', key: 'alpha', color: 'var(--green)' },
      { label: '风控能力', key: 'riskControl', color: 'var(--blue)' },
      { label: '团队稳定性', key: 'team', color: 'var(--orange)' },
      { label: '费率友好度', key: 'fee', color: 'var(--purple)' },
      { label: '容量空间', key: 'capacity', color: 'var(--accent)' }
    ];

    // Rating grade from rating field
    const ratingObj = fund.rating || {};
    const gradeDisplay = ratingObj.grade ? `<span style="margin-left:16px;background:${ratingColors[ratingObj.grade] || '#6b7280'};color:#fff;padding:4px 12px;border-radius:8px;font-size:13px;font-weight:700;">综合评级: ${ratingObj.grade}</span>` : '';

    html += `<div class="detail-section">
      <div class="detail-section-title">投资评分 ${gradeDisplay}</div>`;

    if (hasScore) {
      html += `<div style="display:flex;align-items:center;gap:32px;">
        <div class="score-ring ${scoreClass}">${score.overall}</div>
        <div style="flex:1;">
          <div class="score-bars">
            ${scoreItems.filter(item => score[item.key] !== undefined).map(item => `
              <div class="score-bar-item">
                <span class="score-bar-label">${item.label}</span>
                <div class="score-bar"><div class="score-bar-fill" style="width:${score[item.key]}%;background:${item.color}"></div></div>
                <span class="score-bar-value">${score[item.key]}</span>
              </div>
            `).join('')}
          </div>
        </div>
      </div>`;
    } else {
      html += `<div style="text-align:center;padding:20px;color:var(--text-muted);">
        <p>暂未评分</p>
        <button onclick="showRatingModal('${fund.id}')" style="margin-top:8px;background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:8px;cursor:pointer;font-size:13px;">📝 立即评分</button>
      </div>`;
    }

    if (hasScore) {
      html += `<div style="margin-top:12px;text-align:right;">
        <button onclick="showRatingModal('${fund.id}')" style="background:transparent;color:var(--accent);border:1px solid var(--accent);padding:6px 14px;border-radius:6px;cursor:pointer;font-size:12px;">修改评分</button>
      </div>`;
    }

    html += `</div>`;
  }

  // 基本信息
  const companyFields = [
    { label: '成立时间', value: fund.company.established },
    { label: '实控人', value: fund.company.controller },
    { label: '管理规模', value: fund.company.actualScale },
    { label: '注册资本', value: fund.company.registeredCapital },
    { label: '团队规模', value: fund.company.teamSize ? fund.company.teamSize + '人' : null },
    { label: '办公地址', value: fund.company.location },
    { label: '联系方式', value: fund.company.contact },
    { label: '协会编号', value: fund.company.amacId }
  ].filter(f => f.value);

  if (companyFields.length) {
    html += `<div class="detail-section">
      <div class="detail-section-title">基本信息</div>
      <div class="detail-grid">
        ${companyFields.map(f => `<div class="detail-cell"><div class="cell-label">${f.label}</div><div class="cell-value">${f.value}</div></div>`).join('')}
      </div>
    </div>`;
  }

  // 核心人员
  if (fund.keyPersonnel?.length) {
    html += `<div class="detail-section">
      <div class="detail-section-title">核心人员</div>
      ${fund.keyPersonnel.map(p => `
        <div class="personnel-card">
          <div class="name">${p.name}</div>
          <div class="role">${p.role || ''}</div>
          ${p.birthYear ? `<div class="bio">出生年份: ${p.birthYear}</div>` : ''}
          ${p.background ? `<div class="bio">${p.background}</div>` : ''}
          ${p.previousScale ? `<div class="bio">此前管理规模: ${p.previousScale}</div>` : ''}
          ${p.joinDate ? `<div class="bio">加入时间: ${p.joinDate}</div>` : ''}
          ${p.note ? `<div class="bio" style="margin-top:8px;color:var(--text-muted);">💡 ${p.note}</div>` : ''}
        </div>
      `).join('')}
    </div>`;
  }

  // 策略体系
  if (fund.strategies?.length) {
    html += `<div class="detail-section">
      <div class="detail-section-title" style="display:flex;align-items:center;justify-content:space-between;">
        <span>策略体系</span>
        <button onclick="showStrategyTypeEditor('${fund.id}')" style="background:#8b5cf6;color:#fff;border:none;padding:4px 12px;border-radius:6px;font-size:12px;cursor:pointer;">✏️ 修改策略分类</button>
      </div>
      ${fund.strategies.map((s, idx) => `
        <div class="strategy-card">
          <div class="strat-name">${s.name}${s.product ? ' · ' + s.product : ''}</div>
          ${s.type ? `<div style="margin:4px 0;"><span class="pipeline-tag">${s.type}</span></div>` : '<div style="margin:4px 0;"><span style="color:#6b7280;font-size:12px;">未分类</span></div>'}
          <div style="font-size:13px;color:var(--text-secondary);margin-top:8px;">
            ${s.scale ? `<strong>规模：</strong>${s.scale} · ` : ''}${s.capacity ? `<strong>容量：</strong>${s.capacity} · ` : ''}${s.startDate ? `<strong>起始：</strong>${s.startDate}` : ''}
          </div>
          ${s.framework ? `<div style="font-size:13px;color:var(--text-muted);margin-top:8px;line-height:1.6;">${s.framework}</div>` : ''}
        </div>
      `).join('')}
    </div>`;
  }

  // 投资亮点
  if (fund.highlights?.length) {
    html += `<div class="detail-section">
      <div class="detail-section-title">投资亮点</div>
      ${fund.highlights.map(h => `<div class="highlight-item">✨ ${h}</div>`).join('')}
    </div>`;
  }

  // 风险点
  if (fund.risks?.length) {
    html += `<div class="detail-section">
      <div class="detail-section-title">风险与关注点</div>
      ${fund.risks.map(r => `
        <div class="risk-item">
          <span class="risk-badge risk-${r.level}">${r.level}</span>
          <span>${r.content}</span>
        </div>
      `).join('')}
    </div>`;
  }

  // 费率
  if (fund.fees && (fund.fees.management || fund.fees.performance || fund.fees.channel)) {
    html += `<div class="detail-section">
      <div class="detail-section-title">费率条款</div>
      <div class="detail-grid">
        ${fund.fees.management ? `<div class="detail-cell"><div class="cell-label">管理费</div><div class="cell-value">${fund.fees.management}</div></div>` : ''}
        ${fund.fees.performance ? `<div class="detail-cell"><div class="cell-label">业绩报酬</div><div class="cell-value">${fund.fees.performance}</div></div>` : ''}
        ${fund.fees.channel ? `<div class="detail-cell"><div class="cell-label">代销渠道</div><div class="cell-value">${fund.fees.channel}</div></div>` : ''}
      </div>
    </div>`;
  }

  // 尽调信息
  if (fund.dueDiligence && (fund.dueDiligence.date || fund.dueDiligence.method || fund.dueDiligence.analyst)) {
    html += `<div class="detail-section">
      <div class="detail-section-title">尽调信息</div>
      <div class="detail-grid">
        ${fund.dueDiligence.date ? `<div class="detail-cell"><div class="cell-label">尽调日期</div><div class="cell-value">${fund.dueDiligence.date}</div></div>` : ''}
        ${fund.dueDiligence.location ? `<div class="detail-cell"><div class="cell-label">尽调地点</div><div class="cell-value">${fund.dueDiligence.location}</div></div>` : ''}
        ${fund.dueDiligence.method ? `<div class="detail-cell"><div class="cell-label">尽调方式</div><div class="cell-value">${fund.dueDiligence.method}</div></div>` : ''}
        ${fund.dueDiligence.contact ? `<div class="detail-cell"><div class="cell-label">对接人</div><div class="cell-value">${fund.dueDiligence.contact}</div></div>` : ''}
        ${fund.dueDiligence.analyst ? `<div class="detail-cell"><div class="cell-label">尽调人</div><div class="cell-value">${fund.dueDiligence.analyst}</div></div>` : ''}
        ${fund.dueDiligence.status ? `<div class="detail-cell"><div class="cell-label">状态</div><div class="cell-value">${fund.dueDiligence.status}</div></div>` : ''}
      </div>
      ${fund.dueDiligence.nextSteps?.length ? `
        <div style="margin-top:16px;">
          <div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-bottom:8px;">后续跟进计划</div>
          ${fund.dueDiligence.nextSteps.map(s => `<div class="next-step-item">• ${s}</div>`).join('')}
        </div>
      ` : ''}
    </div>`;
  }

  // 沟通记录时间线
  if (fund.communications?.length) {
    html += `<div class="detail-section">
      <div class="detail-section-title">沟通记录</div>
      <div class="timeline">
        ${fund.communications.map(c => `
          <div class="timeline-item">
            <div class="timeline-dot"></div>
            <div class="timeline-content">
              <div class="timeline-header">
                <span class="timeline-date">${c.date}</span>
                <span class="timeline-type">${c.type}</span>
              </div>
              ${c.participants ? `<div class="timeline-participants">👥 ${c.participants}</div>` : ''}
              ${c.summary ? `<div class="timeline-summary">${c.summary}</div>` : ''}
              ${c.keyPoints?.length ? `
                <div class="timeline-points">
                  ${c.keyPoints.map(p => `<div class="timeline-point">• ${p}</div>`).join('')}
                </div>
              ` : ''}
            </div>
          </div>
        `).join('')}
      </div>
    </div>`;
  }

  // 对标产品
  if (fund.benchmarkProducts?.length) {
    html += `<div class="detail-section">
      <div class="detail-section-title">对标产品</div>
      ${fund.benchmarkProducts.map(b => `
        <div class="benchmark-card">
          <div class="benchmark-header">
            <span class="benchmark-name">${b.name}</span>
            ${b.relation ? `<span class="benchmark-relation">${b.relation}</span>` : ''}
          </div>
          ${b.comparison ? `<div class="benchmark-comparison">${b.comparison}</div>` : ''}
        </div>
      `).join('')}
    </div>`;
  }

  // 入库评审
  if (fund.reviewChecklist && fund.reviewChecklist.criteria?.length) {
    const review = fund.reviewChecklist;
    const passCount = review.criteria.filter(c => c.pass).length;
    const totalCount = review.criteria.length;
    html += `<div class="detail-section">
      <div class="detail-section-title">入库评审</div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding:12px;background:var(--main-bg);border-radius:8px;flex-wrap:wrap;gap:12px;">
        <div>
          <span style="font-size:13px;color:var(--text-secondary);">评审状态：</span>
          <span class="stage-badge stage-approved">${review.status || '待评审'}</span>
        </div>
        <div>
          <span style="font-size:13px;color:var(--text-secondary);">通过率：</span>
          <span style="font-size:18px;font-weight:700;color:${passCount === totalCount ? 'var(--green)' : 'var(--orange)'}">${passCount}/${totalCount}</span>
        </div>
        ${review.targetDate ? `<div>
          <span style="font-size:13px;color:var(--text-secondary);">目标日期：</span>
          <span style="font-weight:600;">${review.targetDate}</span>
        </div>` : ''}
      </div>
      <table class="review-table">
        <thead><tr><th>评审项</th><th>要求</th><th>实际</th><th>状态</th></tr></thead>
        <tbody>
          ${review.criteria.map(c => `
            <tr>
              <td>${c.item}</td>
              <td>${c.requirement || '-'}</td>
              <td>${c.actual || '-'}</td>
              <td><span class="review-status ${c.pass ? 'pass' : 'pending'}">${c.pass ? '✓ 通过' : '⏳ 待达标'}</span></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>`;
  }

  // 提醒模块（增强版）
  {
    const reminders = fund.reminders || [];
    html += `<div class="detail-section">
      <div class="detail-section-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>🔔 提醒事项</span>
        <button onclick="showAddReminderModal('${fund.id}')" style="background:var(--accent);color:#fff;border:none;padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px;">+ 添加提醒</button>
      </div>`;
    if (reminders.length === 0) {
      html += `<div style="text-align:center;padding:16px;color:var(--text-muted);font-size:13px;">暂无提醒事项</div>`;
    } else {
      html += reminders.map(r => {
        const isPending = r.status !== 'done';
        const bgColor = isPending ? 'rgba(245,158,11,0.1)' : 'rgba(107,114,128,0.1)';
        const borderColor = isPending ? 'rgba(245,158,11,0.3)' : 'rgba(107,114,128,0.2)';
        const textColor = isPending ? '#fbbf24' : '#9ca3af';
        return `<div style="background:${bgColor};border:1px solid ${borderColor};border-radius:8px;padding:12px 16px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;">
          <div style="flex:1;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="color:${textColor};font-size:12px;font-weight:600;">${r.date || ''}</span>
              ${r.type ? `<span style="color:var(--text-muted);font-size:11px;background:rgba(255,255,255,0.05);padding:2px 6px;border-radius:4px;">${r.type}</span>` : ''}
              ${!isPending ? '<span style="color:#6b7280;font-size:11px;">✓ 已完成</span>' : ''}
            </div>
            <div style="color:${isPending ? 'var(--text-primary)' : '#6b7280'};font-size:13px;margin-top:4px;${!isPending ? 'text-decoration:line-through;' : ''}">${r.content}</div>
          </div>
          ${isPending ? `<button onclick="completeReminder('${fund.id}', '${r.id || r.date}')" style="background:rgba(16,185,129,0.2);color:#6ee7b7;border:1px solid rgba(16,185,129,0.3);padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11px;margin-left:12px;">完成</button>` : ''}
        </div>`;
      }).join('');
    }
    html += `</div>`;
  }

  // Tags - 分层标签体系
  // 将现有tags按层级分类
  const categorizedTags = {};
  const uncategorizedTags = [];
  (fund.tags || []).forEach(tag => {
    let found = false;
    for (const [category, info] of Object.entries(TAG_TAXONOMY)) {
      if (info.tags.includes(tag)) {
        if (!categorizedTags[category]) categorizedTags[category] = [];
        categorizedTags[category].push(tag);
        found = true;
        break;
      }
    }
    if (!found) uncategorizedTags.push(tag);
  });

  html += `<div class="detail-section">
    <div class="detail-section-title" style="display:flex;align-items:center;justify-content:space-between;">
      <span>标签管理</span>
      <button onclick="showTagEditor('${fund.id}')" style="background:#6366f1;color:#fff;border:none;padding:4px 12px;border-radius:6px;font-size:12px;cursor:pointer;">✏️ 编辑标签</button>
    </div>
    <div id="tagDisplay-${fund.id}">`;

  // 按层级显示
  for (const [category, info] of Object.entries(TAG_TAXONOMY)) {
    const tags = categorizedTags[category] || [];
    if (tags.length > 0) {
      html += `<div style="margin-bottom:8px;">
        <span style="font-size:11px;color:#94a3b8;margin-right:8px;">${category}:</span>
        ${tags.map(t => `<span style="background:${info.color}22;color:${info.color};border:1px solid ${info.color}44;padding:3px 10px;border-radius:12px;font-size:12px;margin-right:6px;margin-bottom:4px;display:inline-block;">${t}</span>`).join('')}
      </div>`;
    }
  }
  if (uncategorizedTags.length > 0) {
    html += `<div style="margin-bottom:8px;">
      <span style="font-size:11px;color:#94a3b8;margin-right:8px;">其他:</span>
      ${uncategorizedTags.map(t => `<span style="background:#374151;color:#d1d5db;border:1px solid #4b5563;padding:3px 10px;border-radius:12px;font-size:12px;margin-right:6px;margin-bottom:4px;display:inline-block;">${t}</span>`).join('')}
    </div>`;
  }
  if (!fund.tags?.length) {
    html += `<div style="color:#6b7280;font-size:13px;">暂无标签，点击编辑添加</div>`;
  }

  html += `</div></div>`;

  // 附件分类展示
  if (fund.attachments?.length) {
    const categories = {
      '尽调纪要': [],
      '产品介绍': [],
      '策略介绍': [],
      '路演材料': [],
      '其他': []
    };
    fund.attachments.forEach(a => {
      const isObj = typeof a === 'object';
      const displayName = isObj ? a.originalName : a;
      const category = (isObj && a.category) ? a.category : '其他';
      // Try to auto-categorize by filename
      let cat = category;
      if (cat === '其他') {
        const lower = displayName.toLowerCase();
        if (lower.includes('尽调') || lower.includes('dd') || lower.includes('纪要')) cat = '尽调纪要';
        else if (lower.includes('产品') || lower.includes('product')) cat = '产品介绍';
        else if (lower.includes('策略') || lower.includes('strategy')) cat = '策略介绍';
        else if (lower.includes('路演') || lower.includes('roadshow') || lower.includes('ppt')) cat = '路演材料';
      }
      if (!categories[cat]) categories[cat] = [];
      categories[cat].push(a);
    });

    html += `<div class="detail-section">
      <div class="detail-section-title">附件资料</div>`;

    const catIcons = { '尽调纪要': '📝', '产品介绍': '📦', '策略介绍': '📊', '路演材料': '🎬', '其他': '📎' };
    Object.entries(categories).forEach(([catName, files]) => {
      if (files.length === 0) return;
      html += `<div style="margin-bottom:12px;">
        <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">${catIcons[catName] || '📎'} ${catName} (${files.length})</div>
        <div class="attachments-list">`;
      files.forEach(a => {
        const isObj = typeof a === 'object';
        const displayName = isObj ? a.originalName : a;
        const filePath = isObj ? a.path : `/uploads/${a}`;
        const ext = displayName.split('.').pop().toLowerCase();
        const icon = ['pdf'].includes(ext) ? '📄' : ['doc','docx'].includes(ext) ? '📝' : ['xls','xlsx'].includes(ext) ? '📊' : ['ppt','pptx'].includes(ext) ? '📽️' : '📎';
        html += `<a class="attachment-link" href="${filePath}" target="_blank" title="点击打开: ${displayName}">
          <span class="attachment-icon">${icon}</span>
          <span class="attachment-name">${displayName}</span>
          <span class="attachment-open">打开 ↗</span>
        </a>`;
      });
      html += `</div></div>`;
    });

    html += `</div>`;
  }

  // ===== 阶段流转时间线 =====
  {
    const stageHistory = fund.stageHistory || [];
    html += `<div class="detail-section">
      <div class="detail-section-title" style="display:flex;justify-content:space-between;align-items:center;">
        <span>📈 阶段流转</span>
        <button onclick="showStageTransitionModal('${fund.id}')" style="background:var(--accent);color:#fff;border:none;padding:5px 12px;border-radius:6px;cursor:pointer;font-size:12px;">推进阶段</button>
      </div>`;
    if (stageHistory.length === 0) {
      html += `<div style="text-align:center;padding:16px;color:var(--text-muted);font-size:13px;">暂无阶段流转记录</div>`;
    } else {
      html += `<div style="position:relative;padding-left:20px;">`;
      // vertical line
      html += `<div style="position:absolute;left:8px;top:4px;bottom:4px;width:2px;background:rgba(99,102,241,0.3);"></div>`;
      [...stageHistory].reverse().forEach(h => {
        const fromStage = STAGES[h.from] || { label: h.from, color: '#6b7280' };
        const toStage = STAGES[h.to] || { label: h.to, color: '#6b7280' };
        html += `<div style="position:relative;margin-bottom:16px;padding-left:16px;">
          <div style="position:absolute;left:-16px;top:6px;width:10px;height:10px;border-radius:50%;background:${toStage.color};border:2px solid rgba(30,41,59,1);"></div>
          <div style="font-size:12px;color:var(--text-muted);">${h.date || '-'}</div>
          <div style="font-size:13px;color:var(--text-primary);margin-top:2px;">
            <span style="color:${fromStage.color};">${fromStage.label}</span>
            <span style="color:var(--text-muted);"> → </span>
            <span style="color:${toStage.color};font-weight:600;">${toStage.label}</span>
          </div>
          ${h.reason ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:2px;">原因: ${h.reason}</div>` : ''}
          ${h.operator ? `<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">操作人: ${h.operator}</div>` : ''}
        </div>`;
      });
      html += `</div>`;
    }
    html += `</div>`;
  }

  // ===== 操作日志（折叠区域）=====
  {
    const auditLog = fund.auditLog || [];
    html += `<div class="detail-section">
      <div class="detail-section-title" style="cursor:pointer;" onclick="this.parentElement.querySelector('.audit-log-content').classList.toggle('collapsed')">
        <span>📝 操作日志 (${auditLog.length})</span>
        <span style="font-size:11px;color:var(--text-muted);margin-left:8px;">点击展开/收起</span>
      </div>
      <div class="audit-log-content collapsed" style="overflow:hidden;">`;
    if (auditLog.length === 0) {
      html += `<div style="padding:12px;color:var(--text-muted);font-size:13px;">暂无操作记录</div>`;
    } else {
      [...auditLog].reverse().forEach(log => {
        html += `<div style="padding:8px 12px;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;display:flex;align-items:center;gap:12px;">
          <span style="color:var(--text-muted);min-width:80px;">${log.date || '-'}</span>
          <span style="color:var(--text-primary);flex:1;">${log.action || '-'}</span>
          <span style="color:var(--text-secondary);">${log.operator || '-'}</span>
          ${log.detail ? `<span style="color:var(--text-muted);font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${log.detail}">${log.detail}</span>` : ''}
        </div>`;
      });
    }
    html += `</div></div>`;
  }

  // Collapsed style for audit log
  html = `<style>
    .audit-log-content.collapsed { max-height:0 !important; }
    .audit-log-content { max-height:2000px; transition: max-height 0.3s ease; }
  </style>` + html;

  document.getElementById('detailContent').innerHTML = html;
  document.getElementById('detailModal').classList.add('show');
}

function closeDetail() {
  document.getElementById('detailModal').classList.remove('show');
}

// ===== 标签编辑器 =====
const TAG_TAXONOMY = {
  '策略大类': {
    color: '#6366f1',
    tags: ['指数增强', '量化选股', '市场中性', 'CTA', '主观多头', '期权', '可转债', '黄金', '宏观', '固收+', '多策略']
  },
  '策略细分': {
    color: '#8b5cf6',
    tags: ['500指增', '1000指增', '2000指增', 'A500', '北证', '量化CTA', '主观CTA', '短周期', '趋势', '套利', '截面中性', '多空', '红利', '高股息', '转债多头', '转债指增', '商品多头', '黑色系', '化工', '农产品', '波动率']
  },
  '团队背景': {
    color: '#0ea5e9',
    tags: ['世坤系', '启林系', '敦和系', '因诺系', '清华系', '北大系', '中科院系', '海归派', '产业背景', '券商自营系', '公募系', '保险系']
  },
  '特征标签': {
    color: '#10b981',
    tags: ['深度学习', '机器学习', '高频', '中频', '低频', '大容量', '百亿级', '新私募', '小规模', '高夏普', '低回撤', '高换手', '基本面', '量价因子']
  },
  '跟踪状态': {
    color: '#f59e0b',
    tags: ['GAMT池', '重点跟踪', '暂缓', '待复调', '待入库', '已否决']
  }
};

let editorTags = [];

function showTagEditor(fundId) {
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund) return;
  editorTags = [...(fund.tags || [])];
  renderTagEditorModal(fundId, fund);
}

function renderTagEditorModal(fundId, fund) {
  // 先移除旧的
  const old = document.getElementById('tagEditorModal');
  if (old) old.remove();

  let modalHtml = `
    <div id="tagEditorModal" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;" onclick="if(event.target===this)closeTagEditor()">
      <div style="background:#1e293b;border-radius:16px;padding:28px;width:90%;max-width:700px;max-height:80vh;overflow-y:auto;border:1px solid #334155;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
          <h3 style="color:#f1f5f9;margin:0;font-size:18px;">🏷️ 标签管理 - ${fund.company.shortName || fund.company.name}</h3>
          <button onclick="closeTagEditor()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button>
        </div>
        
        <div style="margin-bottom:16px;padding:12px;background:#0f172a;border-radius:8px;">
          <div style="font-size:12px;color:#94a3b8;margin-bottom:8px;">当前标签 (${editorTags.length})：</div>
          <div id="currentTagsDisplay" style="min-height:30px;">
            ${editorTags.length ? editorTags.map(t => {
              let tagColor = '#6b7280';
              for (const [cat, info] of Object.entries(TAG_TAXONOMY)) {
                if (info.tags.includes(t)) { tagColor = info.color; break; }
              }
              return `<span onclick="removeTagFromEditor('${fundId}','${t.replace(/'/g, "\\'")}')"
                style="display:inline-block;background:${tagColor}22;color:${tagColor};border:1px solid ${tagColor}44;padding:4px 10px;border-radius:12px;font-size:12px;margin:3px 4px;cursor:pointer;" 
                title="点击移除">${t} ✕</span>`;
            }).join('') : '<span style="color:#6b7280;font-size:12px;">暂无标签，点击下方添加</span>'}
          </div>
        </div>

        <div style="margin-bottom:16px;">
          <div style="display:flex;gap:8px;align-items:center;">
            <input type="text" id="customTagInput" placeholder="输入自定义标签后回车添加" 
              style="flex:1;background:#0f172a;border:1px solid #334155;color:#f1f5f9;padding:8px 12px;border-radius:8px;font-size:13px;"
              onkeydown="if(event.key==='Enter'){event.preventDefault();addCustomTag('${fundId}');}">
            <button onclick="addCustomTag('${fundId}')" style="background:#6366f1;color:#fff;border:none;padding:8px 16px;border-radius:8px;font-size:13px;cursor:pointer;white-space:nowrap;">添加</button>
          </div>
        </div>

        <div style="font-size:13px;color:#94a3b8;margin-bottom:12px;">点击标签快速切换：</div>`;

  for (const [category, info] of Object.entries(TAG_TAXONOMY)) {
    modalHtml += `
      <div style="margin-bottom:14px;">
        <div style="font-size:12px;font-weight:600;color:${info.color};margin-bottom:6px;">${category}</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;">`;
    info.tags.forEach(tag => {
      const isActive = editorTags.includes(tag);
      modalHtml += `<span onclick="toggleTagInEditor('${fundId}','${tag}')" 
        style="display:inline-block;padding:4px 12px;border-radius:12px;font-size:12px;cursor:pointer;transition:all 0.15s;
        ${isActive 
          ? `background:${info.color};color:#fff;border:1px solid ${info.color};font-weight:600;` 
          : `background:${info.color}15;color:${info.color};border:1px solid ${info.color}33;`
        }">${isActive ? '✓ ' : ''}${tag}</span>`;
    });
    modalHtml += `</div></div>`;
  }

  modalHtml += `
        <div style="margin-top:20px;display:flex;justify-content:flex-end;gap:12px;">
          <button onclick="closeTagEditor()" style="background:#374151;color:#d1d5db;border:none;padding:8px 20px;border-radius:8px;cursor:pointer;">取消</button>
          <button onclick="saveTagsFromEditor('${fundId}')" style="background:#10b981;color:#fff;border:none;padding:8px 20px;border-radius:8px;cursor:pointer;font-weight:600;">✅ 保存标签</button>
        </div>
      </div>
    </div>`;

  document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function toggleTagInEditor(fundId, tag) {
  const idx = editorTags.indexOf(tag);
  if (idx >= 0) {
    editorTags.splice(idx, 1);
  } else {
    editorTags.push(tag);
  }
  const fund = allFunds.find(f => f.id === fundId);
  renderTagEditorModal(fundId, fund);
}

function removeTagFromEditor(fundId, tag) {
  const idx = editorTags.indexOf(tag);
  if (idx >= 0) {
    editorTags.splice(idx, 1);
    const fund = allFunds.find(f => f.id === fundId);
    renderTagEditorModal(fundId, fund);
  }
}

function addCustomTag(fundId) {
  const input = document.getElementById('customTagInput');
  const tag = input.value.trim();
  if (tag && !editorTags.includes(tag)) {
    editorTags.push(tag);
    const fund = allFunds.find(f => f.id === fundId);
    renderTagEditorModal(fundId, fund);
    setTimeout(() => {
      const newInput = document.getElementById('customTagInput');
      if (newInput) newInput.focus();
    }, 50);
  }
}

function closeTagEditor() {
  const modal = document.getElementById('tagEditorModal');
  if (modal) modal.remove();
}

async function saveTagsFromEditor(fundId) {
  try {
    const res = await fetch(`/api/funds/${fundId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: editorTags })
    });
    if (res.ok) {
      // 更新本地数据
      const fund = allFunds.find(f => f.id === fundId);
      if (fund) fund.tags = [...editorTags];
      closeTagEditor();
      // 刷新详情页
      showDetail(fundId);
    } else {
      alert('保存失败');
    }
  } catch (err) {
    alert('保存失败: ' + err.message);
  }
}

// ===== 策略类型编辑器 =====
const STRATEGY_TYPES = [
  '指数增强', '量化选股', '量化多头', '市场中性', '量化CTA', '主观CTA',
  '主观多头', '主观择时多头', '股票短线', '期权套利', '期权策略',
  '可转债', '可转债多头', '可转债指增', '黄金主题', '黄金增强',
  '宏观策略', '大类资产配置', '固收+', '多策略',
  '商品多头', '趋势策略', '量化择时', '其他'
];

function showStrategyTypeEditor(fundId) {
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund || !fund.strategies?.length) return;

  let modalHtml = `
    <div id="strategyTypeModal" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;" onclick="if(event.target===this)closeStrategyTypeEditor()">
      <div style="background:#1e293b;border-radius:16px;padding:28px;width:90%;max-width:600px;max-height:80vh;overflow-y:auto;border:1px solid #334155;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
          <h3 style="color:#f1f5f9;margin:0;font-size:18px;">✏️ 修改策略分类 - ${fund.company.shortName || fund.company.name}</h3>
          <button onclick="closeStrategyTypeEditor()" style="background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">✕</button>
        </div>
        <div style="font-size:13px;color:#94a3b8;margin-bottom:16px;">为每个策略选择正确的分类，也可以自定义输入</div>
        <form id="strategyTypeForm" onsubmit="submitStrategyTypes(event,'${fundId}')">`;

  fund.strategies.forEach((s, idx) => {
    modalHtml += `
      <div style="background:#0f172a;border-radius:10px;padding:16px;margin-bottom:12px;border:1px solid #334155;">
        <div style="font-size:14px;font-weight:600;color:#f1f5f9;margin-bottom:8px;">${s.name}${s.product ? ' · ' + s.product : ''}</div>
        <div style="display:flex;gap:8px;align-items:center;">
          <select name="stratType_${idx}" style="flex:1;background:#1e293b;border:1px solid #475569;color:#f1f5f9;padding:8px 12px;border-radius:8px;font-size:13px;">
            <option value="">选择策略类型</option>
            ${STRATEGY_TYPES.map(t => `<option value="${t}" ${s.type === t ? 'selected' : ''}>${t}</option>`).join('')}
            ${s.type && !STRATEGY_TYPES.includes(s.type) ? `<option value="${s.type}" selected>${s.type}</option>` : ''}
          </select>
          <span style="color:#6b7280;font-size:12px;">或</span>
          <input type="text" name="stratCustom_${idx}" placeholder="自定义类型" value=""
            style="width:140px;background:#1e293b;border:1px solid #475569;color:#f1f5f9;padding:8px 12px;border-radius:8px;font-size:13px;">
        </div>
        <div style="margin-top:6px;font-size:11px;color:#6b7280;">当前：${s.type || '未分类'}</div>
      </div>`;
  });

  modalHtml += `
          <div style="margin-top:20px;display:flex;justify-content:flex-end;gap:12px;">
            <button type="button" onclick="closeStrategyTypeEditor()" style="background:#374151;color:#d1d5db;border:none;padding:8px 20px;border-radius:8px;cursor:pointer;">取消</button>
            <button type="submit" style="background:#8b5cf6;color:#fff;border:none;padding:8px 20px;border-radius:8px;cursor:pointer;font-weight:600;">✅ 保存分类</button>
          </div>
        </form>
      </div>
    </div>`;

  document.body.insertAdjacentHTML('beforeend', modalHtml);
}

function closeStrategyTypeEditor() {
  const modal = document.getElementById('strategyTypeModal');
  if (modal) modal.remove();
}

async function submitStrategyTypes(e, fundId) {
  e.preventDefault();
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund) return;

  const form = e.target;
  const updatedStrategies = fund.strategies.map((s, idx) => {
    const selectVal = form[`stratType_${idx}`]?.value || '';
    const customVal = form[`stratCustom_${idx}`]?.value?.trim() || '';
    // 自定义优先，否则用下拉框
    const newType = customVal || selectVal || s.type;
    return { ...s, type: newType };
  });

  try {
    const res = await fetch(`/api/funds/${fundId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategies: updatedStrategies })
    });
    if (res.ok) {
      fund.strategies = updatedStrategies;
      closeStrategyTypeEditor();
      showDetail(fundId);
    } else {
      alert('保存失败');
    }
  } catch (err) {
    alert('保存失败: ' + err.message);
  }
}

// ===== 评分模块 Modal =====
function showRatingModal(fundId) {
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund) return;
  const existing = fund.rating || {};
  const dimensions = [
    { key: 'alpha', label: 'Alpha能力' },
    { key: 'riskControl', label: '风控能力' },
    { key: 'team', label: '团队稳定性' },
    { key: 'fee', label: '费率友好度' },
    { key: 'capacity', label: '容量空间' }
  ];

  let modalHtml = `<div id="ratingModalOverlay" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;" onclick="if(event.target===this)this.remove()">
    <div style="background:#1e293b;border-radius:12px;padding:24px;width:400px;max-width:90vw;border:1px solid rgba(99,102,241,0.3);">
      <h3 style="color:#f1f5f9;margin:0 0 20px;font-size:16px;">🌟 投资评分 - ${fund.company.shortName || fund.company.name}</h3>
      <form onsubmit="submitRating(event, '${fundId}')">`;

  dimensions.forEach(dim => {
    const val = existing[dim.key] || 3;
    modalHtml += `<div style="margin-bottom:16px;">
      <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">${dim.label}</label>
      <div style="display:flex;gap:8px;align-items:center;">
        ${[1,2,3,4,5].map(n => `<label style="cursor:pointer;">
          <input type="radio" name="${dim.key}" value="${n}" ${n === val ? 'checked' : ''} style="display:none;">
          <span style="font-size:20px;opacity:${n <= val ? '1' : '0.3'};" class="rating-star" data-dim="${dim.key}" data-val="${n}">⭐</span>
        </label>`).join('')}
        <span style="color:var(--text-muted);font-size:12px;margin-left:8px;" id="ratingVal_${dim.key}">${val}/5</span>
      </div>
    </div>`;
  });

  modalHtml += `<div style="margin-top:20px;display:flex;gap:12px;justify-content:flex-end;">
        <button type="button" onclick="document.getElementById('ratingModalOverlay').remove()" style="background:transparent;color:var(--text-muted);border:1px solid var(--text-muted);padding:8px 16px;border-radius:6px;cursor:pointer;">取消</button>
        <button type="submit" style="background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:6px;cursor:pointer;font-weight:600;">提交评分</button>
      </div>
      </form>
    </div>
  </div>`;

  document.body.insertAdjacentHTML('beforeend', modalHtml);

  // Star click handlers
  document.querySelectorAll('.rating-star').forEach(star => {
    star.onclick = function() {
      const dim = this.dataset.dim;
      const val = parseInt(this.dataset.val);
      document.querySelectorAll(`.rating-star[data-dim="${dim}"]`).forEach(s => {
        s.style.opacity = parseInt(s.dataset.val) <= val ? '1' : '0.3';
      });
      document.querySelector(`input[name="${dim}"][value="${val}"]`).checked = true;
      const valSpan = document.getElementById(`ratingVal_${dim}`);
      if (valSpan) valSpan.textContent = `${val}/5`;
    };
  });
}

async function submitRating(e, fundId) {
  e.preventDefault();
  const formData = new FormData(e.target);
  const rating = {
    alpha: parseInt(formData.get('alpha')) || 3,
    riskControl: parseInt(formData.get('riskControl')) || 3,
    team: parseInt(formData.get('team')) || 3,
    fee: parseInt(formData.get('fee')) || 3,
    capacity: parseInt(formData.get('capacity')) || 3
  };
  // Calculate overall and grade
  const overall = Math.round((rating.alpha + rating.riskControl + rating.team + rating.fee + rating.capacity) / 5 * 20);
  const grade = overall >= 80 ? 'A' : overall >= 60 ? 'B' : overall >= 40 ? 'C' : 'D';
  rating.overall = overall;
  rating.grade = grade;

  try {
    const res = await fetch(`/api/funds/${fundId}/rating`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(rating)
    });
    const result = await res.json();
    if (result.success !== false) {
      // Update local data
      const fund = allFunds.find(f => f.id === fundId);
      if (fund) {
        fund.rating = { grade, ...rating };
        fund.investmentScore = { overall, ...rating };
      }
      document.getElementById('ratingModalOverlay')?.remove();
      showDetail(fundId);
    } else {
      alert('评分保存失败');
    }
  } catch (err) {
    alert('评分保存失败');
  }
}

// ===== 阶段流转 Modal =====
function showStageTransitionModal(fundId) {
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund) return;

  let modalHtml = `<div id="stageTransitionOverlay" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;" onclick="if(event.target===this)this.remove()">
    <div style="background:#1e293b;border-radius:12px;padding:24px;width:420px;max-width:90vw;border:1px solid rgba(99,102,241,0.3);">
      <h3 style="color:#f1f5f9;margin:0 0 20px;font-size:16px;">🚀 推进阶段 - ${fund.company.shortName || fund.company.name}</h3>
      <form onsubmit="submitStageTransition(event, '${fundId}')">
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">当前阶段</label>
          <span style="background:${(STAGES[fund.stage] || STAGES.initial).color};color:#fff;padding:4px 12px;border-radius:8px;font-size:13px;">${(STAGES[fund.stage] || STAGES.initial).label}</span>
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">目标阶段 *</label>
          <select name="targetStage" required style="width:100%;padding:8px 12px;background:#0f172a;color:#f1f5f9;border:1px solid rgba(99,102,241,0.3);border-radius:6px;">
            ${Object.entries(STAGES).filter(([key]) => key !== fund.stage).map(([key, info]) => `<option value="${key}">${info.icon} ${info.label}</option>`).join('')}
          </select>
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">原因</label>
          <textarea name="reason" rows="2" style="width:100%;padding:8px 12px;background:#0f172a;color:#f1f5f9;border:1px solid rgba(99,102,241,0.3);border-radius:6px;resize:vertical;" placeholder="请输入推进原因..."></textarea>
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">操作人</label>
          <input type="text" name="operator" style="width:100%;padding:8px 12px;background:#0f172a;color:#f1f5f9;border:1px solid rgba(99,102,241,0.3);border-radius:6px;" placeholder="操作人姓名">
        </div>
        <div style="display:flex;gap:12px;justify-content:flex-end;">
          <button type="button" onclick="document.getElementById('stageTransitionOverlay').remove()" style="background:transparent;color:var(--text-muted);border:1px solid var(--text-muted);padding:8px 16px;border-radius:6px;cursor:pointer;">取消</button>
          <button type="submit" style="background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:6px;cursor:pointer;font-weight:600;">确认推进</button>
        </div>
      </form>
    </div>
  </div>`;

  document.body.insertAdjacentHTML('beforeend', modalHtml);
}

async function submitStageTransition(e, fundId) {
  e.preventDefault();
  const formData = new FormData(e.target);
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund) return;

  const targetStage = formData.get('targetStage');
  const reason = formData.get('reason') || '';
  const operator = formData.get('operator') || '';
  const fromStage = fund.stage;

  try {
    const res = await fetch(`/api/funds/${fundId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stage: targetStage,
        stageHistory: [...(fund.stageHistory || []), {
          date: new Date().toISOString().split('T')[0],
          from: fromStage,
          to: targetStage,
          reason,
          operator
        }]
      })
    });
    const result = await res.json();
    if (result.success !== false) {
      fund.stage = targetStage;
      if (!fund.stageHistory) fund.stageHistory = [];
      fund.stageHistory.push({
        date: new Date().toISOString().split('T')[0],
        from: fromStage,
        to: targetStage,
        reason,
        operator
      });
      fund.updatedAt = new Date().toISOString();
      document.getElementById('stageTransitionOverlay')?.remove();
      renderCurrentView();
      showDetail(fundId);
    } else {
      alert('阶段推进失败');
    }
  } catch (err) {
    alert('阶段推进失败');
  }
}

// ===== 添加提醒 Modal =====
function showAddReminderModal(fundId) {
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund) return;

  let modalHtml = `<div id="reminderModalOverlay" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;" onclick="if(event.target===this)this.remove()">
    <div style="background:#1e293b;border-radius:12px;padding:24px;width:400px;max-width:90vw;border:1px solid rgba(99,102,241,0.3);">
      <h3 style="color:#f1f5f9;margin:0 0 20px;font-size:16px;">🔔 添加提醒 - ${fund.company.shortName || fund.company.name}</h3>
      <form onsubmit="submitReminder(event, '${fundId}')">
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">提醒日期 *</label>
          <input type="date" name="date" required style="width:100%;padding:8px 12px;background:#0f172a;color:#f1f5f9;border:1px solid rgba(99,102,241,0.3);border-radius:6px;">
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">类型</label>
          <select name="type" style="width:100%;padding:8px 12px;background:#0f172a;color:#f1f5f9;border:1px solid rgba(99,102,241,0.3);border-radius:6px;">
            <option value="跟进">跟进</option>
            <option value="尽调">尽调</option>
            <option value="会议">会议</option>
            <option value="报告">报告</option>
            <option value="其他">其他</option>
          </select>
        </div>
        <div style="margin-bottom:16px;">
          <label style="display:block;font-size:13px;color:var(--text-secondary);margin-bottom:6px;">提醒内容 *</label>
          <textarea name="content" rows="3" required style="width:100%;padding:8px 12px;background:#0f172a;color:#f1f5f9;border:1px solid rgba(99,102,241,0.3);border-radius:6px;resize:vertical;" placeholder="提醒内容..."></textarea>
        </div>
        <div style="display:flex;gap:12px;justify-content:flex-end;">
          <button type="button" onclick="document.getElementById('reminderModalOverlay').remove()" style="background:transparent;color:var(--text-muted);border:1px solid var(--text-muted);padding:8px 16px;border-radius:6px;cursor:pointer;">取消</button>
          <button type="submit" style="background:var(--accent);color:#fff;border:none;padding:8px 20px;border-radius:6px;cursor:pointer;font-weight:600;">添加</button>
        </div>
      </form>
    </div>
  </div>`;

  document.body.insertAdjacentHTML('beforeend', modalHtml);
}

async function submitReminder(e, fundId) {
  e.preventDefault();
  const formData = new FormData(e.target);
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund) return;

  const newReminder = {
    id: 'rem_' + Date.now(),
    date: formData.get('date'),
    type: formData.get('type'),
    content: formData.get('content'),
    status: 'pending'
  };

  const reminders = [...(fund.reminders || []), newReminder];

  try {
    const res = await fetch(`/api/funds/${fundId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reminders })
    });
    const result = await res.json();
    if (result.success !== false) {
      fund.reminders = reminders;
      document.getElementById('reminderModalOverlay')?.remove();
      showDetail(fundId);
    } else {
      alert('添加提醒失败');
    }
  } catch (err) {
    alert('添加提醒失败');
  }
}

async function completeReminder(fundId, reminderId) {
  const fund = allFunds.find(f => f.id === fundId);
  if (!fund || !fund.reminders) return;

  const reminders = fund.reminders.map(r => {
    if ((r.id && r.id === reminderId) || (!r.id && r.date === reminderId)) {
      return { ...r, status: 'done' };
    }
    return r;
  });

  try {
    const res = await fetch(`/api/funds/${fundId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reminders })
    });
    const result = await res.json();
    if (result.success !== false) {
      fund.reminders = reminders;
      showDetail(fundId);
    }
  } catch (err) {
    alert('操作失败');
  }
}

// ===== Stage Change =====
async function changeStage(id, newStage) {
  const fund = allFunds.find(f => f.id === id);
  if (!fund) return;

  const stageInfo = STAGES[newStage];
  if (!confirm(`确认将「${fund.company.shortName || fund.company.name}」转为「${stageInfo.label}」？`)) return;

  try {
    const res = await fetch(`/api/funds/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stage: newStage })
    });
    const result = await res.json();
    if (result.success !== false) {
      fund.stage = newStage;
      fund.updatedAt = new Date().toISOString();
      renderCurrentView();
      showDetail(id);
    }
  } catch (err) {
    alert('阶段更新失败');
  }
}

// ===== 新增表单 =====
let addFormMode = 'quick';

function showAddForm() {
  addFormMode = 'quick';
  uploadedFiles = [];
  renderAddForm();
  document.getElementById('addModal').classList.add('show');
}

function renderAddForm() {
  const container = document.getElementById('addFormContent');
  if (!container) return;

  const isQuick = addFormMode === 'quick';

  let html = `<form id="addForm" onsubmit="submitForm(event)">
    <div class="form-mode-toggle">
      <button type="button" class="mode-btn ${isQuick ? 'active' : ''}" onclick="addFormMode='quick';renderAddForm()">快速添加</button>
      <button type="button" class="mode-btn ${!isQuick ? 'active' : ''}" onclick="addFormMode='full';renderAddForm()">完整录入</button>
    </div>

    <div class="form-section">
      <div class="form-section-title">基本信息 <span class="required">*必填</span></div>
      <div class="form-row">
        <div class="form-group"><label>公司名称 *</label><input type="text" name="company.name" required placeholder="私募基金管理人全称"></div>
        <div class="form-group"><label>简称</label><input type="text" name="company.shortName" placeholder="简称"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>策略类型 *</label>
          <select name="strategyType" required>
            <option value="">选择策略类型</option>
            <option value="量化多头">量化多头</option>
            <option value="量化CTA">量化CTA</option>
            <option value="主观多头">主观多头</option>
            <option value="市场中性">市场中性</option>
            <option value="套利策略">套利策略</option>
            <option value="宏观策略">宏观策略</option>
            <option value="多策略">多策略</option>
            <option value="其他">其他</option>
          </select>
        </div>
        <div class="form-group"><label>当前阶段</label>
          <select name="stage">
            ${Object.entries(STAGES).map(([key, info]) => `<option value="${key}">${info.label}</option>`).join('')}
          </select>
        </div>
      </div>
    </div>

    <div class="form-section">
      <div class="form-group"><label>备注</label><textarea name="note" rows="2" placeholder="简要备注..."></textarea></div>
      <div class="form-group"><label>标签</label><input type="text" name="tags" placeholder="用逗号分隔，如：百亿私募,量化,头部"></div>
    </div>`;

  if (!isQuick) {
    html += `
    <div class="form-section">
      <div class="form-section-title">公司详情</div>
      <div class="form-row">
        <div class="form-group"><label>成立时间</label><input type="text" name="company.established" placeholder="如 2018-06"></div>
        <div class="form-group"><label>注册资本</label><input type="text" name="company.registeredCapital" placeholder="如 5000万"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>实控人</label><input type="text" name="company.controller" placeholder="实际控制人"></div>
        <div class="form-group"><label>管理规模</label><input type="text" name="company.actualScale" placeholder="如 50亿"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>团队人数</label><input type="number" name="company.teamSize" placeholder="团队总人数"></div>
        <div class="form-group"><label>办公地址</label><input type="text" name="company.location" placeholder="城市/地址"></div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>联系方式</label><input type="text" name="company.contact" placeholder="联系人/电话"></div>
        <div class="form-group"><label>协会编号</label><input type="text" name="company.amacId" placeholder="中基协登记编号"></div>
      </div>
    </div>

    <div class="form-section">
      <div class="form-section-title">尽调信息</div>
      <div class="form-row">
        <div class="form-group"><label>尽调日期</label><input type="date" name="dueDiligence.date"></div>
        <div class="form-group"><label>尽调方式</label>
          <select name="dueDiligence.method">
            <option value="">选择方式</option>
            <option value="现场尽调">现场尽调</option>
            <option value="远程尽调">远程尽调</option>
            <option value="电话沟通">电话沟通</option>
          </select>
        </div>
      </div>
      <div class="form-row">
        <div class="form-group"><label>尽调地点</label><input type="text" name="dueDiligence.location" placeholder="尽调地点"></div>
        <div class="form-group"><label>尽调人</label><input type="text" name="dueDiligence.analyst" placeholder="尽调分析师"></div>
      </div>
      <div class="form-group"><label>对接人</label><input type="text" name="dueDiligence.contact" placeholder="对方对接人"></div>
    </div>

    <div class="form-section">
      <div class="form-section-title">亮点与风险</div>
      <div class="form-group"><label>投资亮点</label><textarea name="highlights" rows="3" placeholder="每行一条亮点"></textarea></div>
      <div class="form-group"><label>风险点</label><textarea name="risks" rows="3" placeholder="格式：高|风险内容 或 中|风险内容，每行一条"></textarea></div>
    </div>`;
  }

  html += `
    <div class="form-section">
      <div class="form-section-title">附件</div>
      <div class="form-group">
        <input type="file" id="fileUpload" multiple>
        <div id="uploadedFiles" class="uploaded-files-list"></div>
      </div>
    </div>

    <div class="form-actions">
      <button type="button" class="btn-cancel" onclick="closeAddForm()">取消</button>
      <button type="submit" class="btn-submit">保存</button>
    </div>
  </form>`;

  container.innerHTML = html;
  document.getElementById('fileUpload')?.addEventListener('change', handleFileUpload);
}

function closeAddForm() {
  document.getElementById('addModal').classList.remove('show');
}

async function submitForm(e) {
  e.preventDefault();
  const formData = new FormData(e.target);
  const data = {
    stage: formData.get('stage') || 'initial',
    company: {},
    dueDiligence: {},
    keyPersonnel: [],
    strategies: [],
    highlights: [],
    risks: [],
    tags: [],
    attachments: uploadedFiles.map(f => f.filename),
    communications: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };

  for (let [key, value] of formData.entries()) {
    if (!value) continue;
    if (key.startsWith('company.')) {
      const field = key.replace('company.', '');
      data.company[field] = field === 'teamSize' ? parseInt(value) || 0 : value;
    } else if (key.startsWith('dueDiligence.')) {
      data.dueDiligence[key.replace('dueDiligence.', '')] = value;
    } else if (key === 'highlights') {
      data.highlights = value.split('\n').filter(v => v.trim());
    } else if (key === 'risks') {
      data.risks = value.split('\n').filter(v => v.trim()).map(line => {
        const parts = line.split('|');
        return parts.length >= 2
          ? { level: parts[0].trim(), content: parts.slice(1).join('|').trim() }
          : { level: '中', content: line.trim() };
      });
    } else if (key === 'tags') {
      data.tags = value.split(/[,，]/).map(t => t.trim()).filter(Boolean);
    } else if (key === 'note' && value.trim()) {
      data.communications.push({
        date: new Date().toISOString().split('T')[0],
        type: '备注',
        participants: '',
        summary: value.trim(),
        keyPoints: []
      });
    }
  }

  // Add strategy from strategyType
  const strategyType = formData.get('strategyType');
  if (strategyType) {
    data.strategies.push({
      name: strategyType + '策略',
      product: '',
      type: strategyType,
      startDate: '',
      scale: '',
      capacity: '',
      performance: {},
      framework: ''
    });
  }

  try {
    const res = await fetch('/api/funds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    const result = await res.json();
    if (result.success !== false) {
      closeAddForm();
      loadFunds();
    } else {
      alert('保存失败: ' + (result.error || '未知错误'));
    }
  } catch (err) {
    alert('保存失败');
  }
}

// File upload handler
async function handleFileUpload(e) {
  const files = e.target.files;
  if (!files.length) return;
  const formData = new FormData();
  for (let file of files) formData.append('files', file);
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: formData });
    const result = await res.json();
    if (result.success) {
      uploadedFiles.push(...result.files);
      document.getElementById('uploadedFiles').innerHTML =
        uploadedFiles.map(f => `<div class="uploaded-file">✅ ${f.originalName}</div>`).join('');
    }
  } catch (err) {
    alert('上传失败');
  }
}

// ===== Delete Fund =====
async function deleteFund(id) {
  const fund = allFunds.find(f => f.id === id);
  if (!fund) return;
  if (!confirm(`确认删除「${fund.company.shortName || fund.company.name}」？此操作不可恢复。`)) return;

  try {
    const res = await fetch(`/api/funds/${id}`, { method: 'DELETE' });
    const result = await res.json();
    if (result.success !== false) {
      closeDetail();
      loadFunds();
    }
  } catch (err) {
    alert('删除失败');
  }
}

// ===== 快速录入弹窗 =====
function showQuickAddModal() {
  uploadedFiles = [];
  document.getElementById('quickAddForm').reset();
  document.getElementById('quickUploadedFiles').innerHTML = '';
  document.getElementById('quickAddModal').classList.add('show');

  // 绑定文件上传
  const fileInput = document.getElementById('quickFileUpload');
  fileInput.value = '';
  fileInput.onchange = async (e) => {
    const files = e.target.files;
    if (!files.length) return;
    const formData = new FormData();
    for (let file of files) formData.append('files', file);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      const result = await res.json();
      if (result.success) {
        uploadedFiles.push(...result.files);
        document.getElementById('quickUploadedFiles').innerHTML =
          uploadedFiles.map(f => `<div class="uploaded-file">✅ ${f.originalName}</div>`).join('');
      }
    } catch (err) {
      alert('上传失败');
    }
  };
}

function closeQuickAdd() {
  document.getElementById('quickAddModal').classList.remove('show');
}

async function submitQuickAdd(e) {
  e.preventDefault();
  const formData = new FormData(e.target);
  const data = {
    stage: formData.get('stage') || 'initial',
    company: { name: formData.get('name') },
    strategies: [],
    tags: [],
    highlights: [],
    risks: [],
    communications: [],
    attachments: uploadedFiles.map(f => ({ originalName: f.originalName, filename: f.filename, path: f.path })),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };

  const strategyType = formData.get('strategyType');
  if (strategyType) {
    data.strategies.push({ name: strategyType + '策略', type: strategyType, performance: {} });
  }

  const tags = formData.get('tags');
  if (tags) data.tags = tags.split(/[,，]/).map(t => t.trim()).filter(Boolean);

  const note = formData.get('note');
  if (note && note.trim()) {
    data.communications.push({
      date: new Date().toISOString().split('T')[0],
      type: '备注',
      summary: note.trim(),
      keyPoints: []
    });
  }

  try {
    const res = await fetch('/api/funds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    const result = await res.json();
    if (result.success !== false) {
      closeQuickAdd();
      loadFunds();
    } else {
      alert('保存失败');
    }
  } catch (err) {
    alert('保存失败');
  }
}

// ===== 智能录入 =====
let smartUploadFiles = [];
let smartParsedFiles = [];

function showSmartUpload() {
  smartUploadFiles = [];
  smartParsedFiles = [];
  document.getElementById('smartUploadStep1').style.display = '';
  document.getElementById('smartUploadStep2').style.display = 'none';
  document.getElementById('smartUploadStep3').style.display = 'none';
  document.getElementById('smartFileList').innerHTML = '';
  document.getElementById('smartParseActions').style.display = 'none';
  document.getElementById('smartUploadModal').classList.add('show');

  // 绑定拖拽和点击
  const dropZone = document.getElementById('smartDropZone');
  const fileInput = document.getElementById('smartFileInput');

  dropZone.onclick = () => fileInput.click();
  fileInput.value = '';
  fileInput.onchange = (e) => handleSmartFiles(e.target.files);

  dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('dragover'); };
  dropZone.ondragleave = () => dropZone.classList.remove('dragover');
  dropZone.ondrop = (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    handleSmartFiles(e.dataTransfer.files);
  };
}

function closeSmartUpload() {
  document.getElementById('smartUploadModal').classList.remove('show');
}

function handleSmartFiles(files) {
  for (let f of files) {
    smartUploadFiles.push(f);
  }
  renderSmartFileList();
}

function renderSmartFileList() {
  const container = document.getElementById('smartFileList');
  container.innerHTML = smartUploadFiles.map((f, i) => {
    const ext = f.name.split('.').pop().toLowerCase();
    const icon = ['pdf'].includes(ext) ? '📄' : ['doc','docx'].includes(ext) ? '📝' : ['xls','xlsx'].includes(ext) ? '📊' : '📎';
    return `<div class="smart-file-item">
      <span>${icon} ${f.name}</span>
      <span class="file-size">${(f.size / 1024).toFixed(0)}KB</span>
      <button class="btn-ghost btn-xs" onclick="removeSmartFile(${i})">✕</button>
    </div>`;
  }).join('');

  document.getElementById('smartParseActions').style.display = smartUploadFiles.length ? '' : 'none';
}

function removeSmartFile(idx) {
  smartUploadFiles.splice(idx, 1);
  renderSmartFileList();
}

async function startSmartParse() {
  document.getElementById('smartUploadStep1').style.display = 'none';
  document.getElementById('smartUploadStep2').style.display = '';

  let allText = '';
  smartParsedFiles = [];

  // 上传并解析每个文件
  for (const file of smartUploadFiles) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/parse-file', { method: 'POST', body: formData });
      const result = await res.json();
      if (result.success) {
        smartParsedFiles.push(result.file);
        allText += `\n=== ${result.file.originalName} ===\n${result.textContent}\n`;
      }
    } catch (err) {
      console.error('解析失败:', file.name, err);
    }
  }

  // 用简单规则提取关键信息（前端解析）
  const extracted = extractInfoFromText(allText);

  // 填充表单
  document.getElementById('smart_name').value = extracted.name || '';
  document.getElementById('smart_shortName').value = extracted.shortName || '';
  document.getElementById('smart_strategyType').value = extracted.strategyType || '';
  document.getElementById('smart_scale').value = extracted.scale || '';
  document.getElementById('smart_established').value = extracted.established || '';
  document.getElementById('smart_controller').value = extracted.controller || '';
  document.getElementById('smart_teamSize').value = extracted.teamSize || '';
  document.getElementById('smart_location').value = extracted.location || '';
  document.getElementById('smart_highlights').value = (extracted.highlights || []).join('\n');
  document.getElementById('smart_risks').value = (extracted.risks || []).join('\n');
  document.getElementById('smart_tags').value = (extracted.tags || []).join(', ');
  document.getElementById('smart_summary').value = extracted.summary || '';

  document.getElementById('smartUploadStep2').style.display = 'none';
  document.getElementById('smartUploadStep3').style.display = '';
}

// 前端文本解析规则
function extractInfoFromText(text) {
  const result = {};

  // 公司名称
  const namePatterns = [
    /(?:公司名称|管理人|公司全称)[\uff1a:]+\s*(.+)/,
    /([\u4e00-\u9fa5]+(?:资产管理|基金管理|投资管理|私募基金)(?:有限公司)?)/,
    /([\u4e00-\u9fa5]+(?:资本|投资|资产)(?:有限公司)?)/
  ];
  for (const p of namePatterns) {
    const m = text.match(p);
    if (m) { result.name = m[1].trim(); break; }
  }

  // 简称
  const shortNameMatch = text.match(/(?:简称)[\uff1a:]+\s*(.+)/);
  if (shortNameMatch) result.shortName = shortNameMatch[1].trim();

  // 规模
  const scaleMatch = text.match(/(?:管理规模|基金规模|资产规模)[\uff1a:]+\s*([\d.]+\s*[亿万]?)/i);
  if (scaleMatch) result.scale = scaleMatch[1].trim();

  // 成立时间
  const estMatch = text.match(/(?:成立时间|成立于|成立日期)[\uff1a:]+\s*(\d{4}[\-\/年]?\d{0,2})/i);
  if (estMatch) result.established = estMatch[1].replace(/[年月日]/g, '').trim();

  // 实控人/基金经理
  const ctrlMatch = text.match(/(?:实控人|基金经理|核心人物|创始人|董事长|总经理)[\uff1a:]+\s*([\u4e00-\u9fa5]{2,4})/);
  if (ctrlMatch) result.controller = ctrlMatch[1].trim();

  // 团队
  const teamMatch = text.match(/(?:团队|\u4eba\u6570|\u5458\u5de5)[\uff1a:]*\s*(\d+)\s*[人名]/i);
  if (teamMatch) result.teamSize = teamMatch[1];

  // 地址
  const locMatch = text.match(/(?:办公地址|地址|注册地)[\uff1a:]+\s*(.+)/i);
  if (locMatch) result.location = locMatch[1].trim().slice(0, 50);

  // 策略类型
  const strategyKeywords = {
    '市场中性': ['市场中性', '中性策略', '对冲'],
    '量化多头': ['量化多头', '量化选股', '量化股票'],
    '量化CTA': ['CTA', '商品期货', '管理期货'],
    '指数增强': ['指数增强', '指增'],
    '主观多头': ['主观多头', '主观股票'],
    '多策略': ['多策略', '复合策略']
  };
  for (const [type, keywords] of Object.entries(strategyKeywords)) {
    if (keywords.some(k => text.includes(k))) {
      result.strategyType = type;
      break;
    }
  }

  // 标签提取
  const tags = [];
  if (result.strategyType) tags.push(result.strategyType);
  if (text.includes('量化')) tags.push('量化');
  if (text.match(/北京|上海|深圳|杭州|广州|珠海/)) {
    const cityMatch = text.match(/(北京|上海|深圳|杭州|广州|珠海)/);
    if (cityMatch) tags.push(cityMatch[1]);
  }
  result.tags = [...new Set(tags)];

  // 摘要（取前200字）
  const cleanText = text.replace(/[=\n\r]+/g, ' ').trim();
  if (cleanText.length > 20) {
    result.summary = cleanText.slice(0, 200) + '...';
  }

  return result;
}

async function submitSmartResult(e) {
  e.preventDefault();
  const form = e.target;
  const formData = new FormData(form);

  const data = {
    stage: 'initial',
    company: {
      name: formData.get('name'),
      shortName: formData.get('shortName') || undefined,
      actualScale: formData.get('scale') || undefined,
      established: formData.get('established') || undefined,
      controller: formData.get('controller') || undefined,
      teamSize: formData.get('teamSize') ? parseInt(formData.get('teamSize')) : undefined,
      location: formData.get('location') || undefined
    },
    strategies: [],
    tags: [],
    highlights: [],
    risks: [],
    communications: [],
    attachments: smartParsedFiles.map(f => ({ originalName: f.originalName, filename: f.filename, path: f.path })),
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };

  const strategyType = formData.get('strategyType');
  if (strategyType) {
    data.strategies.push({ name: strategyType + '策略', type: strategyType, performance: {} });
  }

  const tags = formData.get('tags');
  if (tags) data.tags = tags.split(/[,，]/).map(t => t.trim()).filter(Boolean);

  const highlights = formData.get('highlights');
  if (highlights) data.highlights = highlights.split('\n').filter(v => v.trim());

  const risks = formData.get('risks');
  if (risks) {
    data.risks = risks.split('\n').filter(v => v.trim()).map(line => {
      const parts = line.split('|');
      return parts.length >= 2
        ? { level: parts[0].trim(), content: parts.slice(1).join('|').trim() }
        : { level: '中', content: line.trim() };
    });
  }

  const summary = formData.get('summary');
  if (summary && summary.trim()) {
    data.communications.push({
      date: new Date().toISOString().split('T')[0],
      type: '智能解析摘要',
      summary: summary.trim(),
      keyPoints: []
    });
  }

  // 清理 undefined
  Object.keys(data.company).forEach(k => { if (data.company[k] === undefined) delete data.company[k]; });

  try {
    const res = await fetch('/api/funds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    const result = await res.json();
    if (result.success !== false) {
      closeSmartUpload();
      loadFunds();
      alert('✅ 录入成功！');
    } else {
      alert('保存失败');
    }
  } catch (err) {
    alert('保存失败');
  }
}

// ESC关闭弹窗
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeDetail();
    closeAddForm();
    closeQuickAdd();
    closeSmartUpload();
  }
});
