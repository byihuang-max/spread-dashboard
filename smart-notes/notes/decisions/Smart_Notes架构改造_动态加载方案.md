# Smart Notes架构改造：动态加载方案

## 问题
Smart Notes的笔记内容被硬编码在前端HTML的JS变量（BUILTIN_NOTES）里，导致：
- 添加新笔记需要手动更新 `index.html`
- 容易忘记更新前端
- 维护成本高

## 解决方案

### 架构改造
从**静态硬编码**改为**动态API加载**

```
旧架构：
笔记.md → 手动复制到 index.html BUILTIN_NOTES → 前端读取

新架构：
笔记.md → 后端API扫描 → 前端异步加载
```

### 技术实现

#### 1. 后端API（refresh_server.py）
新增 `/api/notes` 接口：
```python
def _serve_notes_list(self):
    """返回Smart Notes所有笔记的元数据列表"""
    from pathlib import Path
    notes_dir = Path(BASE_DIR) / 'smart-notes' / 'notes'
    notes = []
    
    # 递归扫描 notes/ 目录
    for md_file in notes_dir.rglob("*.md"):
        rel_path = md_file.relative_to(notes_dir.parent)
        
        # 推断分类（根据目录结构）
        parts = md_file.relative_to(notes_dir).parts
        category = parts[0] if len(parts) > 1 else "uncategorized"
        
        # 读取内容
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        notes.append({
            "name": md_file.stem,
            "path": str(rel_path),
            "category": category,
            "content": content
        })
    
    self._json(200, notes)
```

#### 2. 前端加载（index.html）
修改 `loadNotes()` 为异步函数：
```javascript
async function loadNotes() {
  const userData = loadUserData();
  
  // 从API加载笔记
  try {
    const response = await fetch('/api/notes');
    const notes = await response.json();
    
    for (const entry of notes) {
      const id = entry.path.replace(/\.md$/, '');
      const content = userData[id]?.content || entry.content;
      parseNote(id, entry.path, entry.category, entry.name, content);
    }
  } catch (error) {
    console.error('Failed to load notes from API:', error);
    // 降级：使用BUILTIN_NOTES
    for (const entry of BUILTIN_NOTES) {
      const id = entry.path.replace(/\.md$/, '');
      const content = userData[id]?.content || entry.content;
      parseNote(id, entry.path, entry.category, entry.name, content);
    }
  }
  
  renderNav();
  showWelcome();
}
```

### 优势

1. **自动发现**：新增笔记文件后自动出现在列表
2. **分类自动识别**：根据目录结构自动分类
3. **降级保护**：API失败时仍用BUILTIN_NOTES
4. **维护简单**：只需创建.md文件，无需手动更新HTML

### 使用方式

**添加新笔记（新流程）：**
```bash
# 1. 创建笔记文件
echo "# 新笔记内容" > ~/Desktop/gamt-dashboard/smart-notes/notes/新笔记.md

# 2. 提交推送
git add smart-notes/notes/新笔记.md
git commit -m "添加新笔记"
git push

# 3. 完成！刷新页面即可看到
```

**旧流程（不再需要）：**
```bash
# ❌ 不再需要手动更新 index.html
# ❌ 不再需要运行 add_smart_note.py
# ❌ 不再需要编辑 BUILTIN_NOTES 数组
```

### 分类规则

笔记分类根据目录结构自动识别：
```
notes/
  ├── concepts/        → category: "concepts"
  ├── decisions/       → category: "decisions"
  ├── sessions/        → category: "sessions"
  └── 新笔记.md        → category: "uncategorized"
```

### 降级机制

如果API加载失败（网络问题、服务器未启动等），前端会：
1. 捕获错误并记录到console
2. 降级使用 BUILTIN_NOTES（保持向后兼容）
3. 用户仍能看到笔记（虽然可能不是最新）

### 技术细节

**API端点：** `GET /api/notes`

**返回格式：**
```json
[
  {
    "name": "笔记名称",
    "path": "notes/分类/笔记名称.md",
    "category": "分类",
    "content": "# 笔记内容\n..."
  }
]
```

**前端兼容性：**
- 保留 BUILTIN_NOTES 作为降级方案
- 异步加载不阻塞页面渲染
- 支持用户自定义笔记（localStorage）

### 部署状态

- ✅ 后端API已集成到 `refresh_server.py`
- ✅ 前端已改为异步加载
- ✅ 已推送到GitHub
- ✅ 云端已同步并重启
- ⏳ 等待Cloudflare Pages部署（1-2分钟）

### 相关文件

- 后端API：`~/Desktop/gamt-dashboard/server/refresh_server.py`
- 前端加载：`~/Desktop/gamt-dashboard/smart-notes/index.html`
- 独立API脚本：`~/Desktop/gamt-dashboard/smart-notes/notes_api.py`（备用）

### 未来优化

1. **增量更新**：只加载修改过的笔记
2. **缓存机制**：前端缓存笔记列表，减少API调用
3. **搜索优化**：后端提供全文搜索API
4. **版本控制**：记录笔记修改历史

---

**实施时间：** 2026-03-15  
**对话来源：** 与Roni讨论Smart Notes维护问题  
**标签：** #架构改造 #动态加载 #API #维护优化
