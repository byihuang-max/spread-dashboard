# 知识星球爬虫系统

自动抓取订阅的知识星球内容，用于投资研究。

---

## 快速开始

### 1. 获取Cookie

1. 浏览器打开知识星球网页版：https://wx.zsxq.com
2. 登录你的账号
3. 按F12打开开发者工具
4. 切换到"网络"(Network)标签
5. 刷新页面
6. 找到任意请求，查看请求头中的Cookie
7. 复制完整的Cookie字符串

### 2. 配置

编辑 `config.json`：

```json
{
  "cookie": "你的Cookie字符串",
  "planets": [
    {
      "id": "星球ID",
      "name": "星球名称",
      "enabled": true
    }
  ]
}
```

**如何找到星球ID：**
- 打开星球页面，URL中的数字就是ID
- 例如：https://wx.zsxq.com/group/51122858222824 → ID是 51122858222824

### 3. 运行

```bash
cd ~/Desktop/gamt-dashboard/zsxq
python3 crawler.py
```

---

## 数据存储

- `data/raw/` - 原始JSON数据
- `data/processed/` - 处理后的数据（待实现）
- `cache/` - 缓存文件

---

## 下一步功能

- [ ] 增量更新（只抓取新内容）
- [ ] AI总结关键观点
- [ ] 按主题分类
- [ ] 整合到看板
- [ ] 定时自动更新

---

## 注意事项

⚠️ 仅限个人使用，不要分享付费内容
⚠️ Cookie会过期，需要定期更新
⚠️ 不要频繁请求，避免被限流
