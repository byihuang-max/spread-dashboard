# Skill: unify-theme

## 触发词
- "统一主题"、"套上日夜模式"、"统一 CSS 变量"、"去掉 bb-override"
- "把 xxx.html 统一主题"
- "批量统一所有子页面主题"

## 功能
将 GAMT 看板子页面从旧架构（硬编码颜色 + bb-override 暴力覆盖）迁移到新架构（CSS 变量驱动明暗切换）。

## 新架构标准

### CSS 变量模板
```css
:root {
  --bg:#f5f6f8; --card-bg:#fff; --text:#2d3142; --text-sub:#8b92a5;
  --border:#e8eaef; --accent:#ff8c00; --grid-color:#f0f0f0;
  --note-bg:#f9fafb; --signal-bg:#f8f9fa;
  --tag-bg:rgba(0,0,0,0.05); --tag-text:#5a6070;
}
html.bb-dark {
  --bg:#0a0a0a; --card-bg:#0a0a0a; --text:#ccc; --text-sub:#888;
  --border:#2a2a2a; --accent:#ff8c00; --grid-color:#222;
  --note-bg:#111; --signal-bg:#0f0f0f;
  --tag-bg:rgba(255,255,255,0.06); --tag-text:#888;
}
```

### 组件统一风格
- `.signal-bar`: 左侧 3px 橙色竖线，无渐变/圆角
- `.signal-main`: 橙色标题
- `.s-card` / `.chart-box`: 左侧 3px 橙色竖线，无圆角
- `.chart-note`: `var(--note-bg)` + `var(--border)`

### Bootstrap 脚本模板（放在 `</head>` 前）
```html
<script>
(function(){
  function isDark(){return document.documentElement.classList.contains("bb-dark");}
  function registerPlugin(){
    if(typeof Chart==="undefined")return false;
    Chart.defaults.font.family="JetBrains Mono,SF Mono,monospace";
    Chart.register({
      id:"themeGrid",
      afterLayout:function(chart){
        var textSub=isDark()?"#888":"#8b92a5";
        var gridColor=isDark()?"#222":"#f0f0f0";
        Object.values(chart.scales).forEach(function(scale){
          if(scale.options.grid){scale.options.grid.color=gridColor;}
          if(scale.options.ticks){scale.options.ticks.color=textSub;}
        });
      }
    });
    return true;
  }
  if(!registerPlugin()){var tries=0;var iv=setInterval(function(){tries++;if(registerPlugin()||tries>50)clearInterval(iv);},50);}
})();
</script>
<script>
(function(){
  var _mode="dark";
  try{_mode=window.parent.__bbMode||window.parent.localStorage.getItem("bbMode")||"dark";}catch(e){}
  window.__bbMode=_mode;
  if(_mode!=="light"){document.documentElement.classList.add("bb-dark");}
  window.addEventListener("message",function(e){
    if(!e.data||e.data.type!=="bb-theme")return;
    var m=e.data.mode;window.__bbMode=m;
    if(m==="light"){document.documentElement.classList.remove("bb-dark");}
    else{document.documentElement.classList.add("bb-dark");}
    if(typeof Chart!=="undefined"){Object.values(Chart.instances||{}).forEach(function(c){try{c.update();}catch(_e){}});}
  });
})();
</script>
```

### 迁移步骤
1. 删掉 `<style id="bb-override" media="not all">...</style>` 整块
2. 把主 `<style>` 中硬编码颜色替换为 CSS 变量引用
3. 删掉旧 bootstrap 脚本（含 `isBloomberg` / `bb-override-link` / `bloomberg-override.css` 引用）
4. 加入新 bootstrap 脚本模板
5. 删掉 Chart.js 中 `grid:{color:'#f0f0f0'}` 硬编码
6. 对大量 inline style 的页面（如反脆弱），加 `html.bb-dark [style*="..."]` 覆盖规则

### 部署
```bash
git add <files> && git commit -m "refactor: xxx 统一CSS变量驱动明暗切换"
git push gitee main
rsync -avz --chmod=Do+rx,Fo+r -e "ssh -o ConnectTimeout=10" <file> ubuntu@111.229.129.146:~/gamt-dashboard/<path>
```

## 注意
- 不推 GitHub（origin），只推 gitee
- rsync 必须带 `--chmod=Do+rx,Fo+r` 防 403
- ECharts 页面用 `window.bbEchartsColors()` helper
