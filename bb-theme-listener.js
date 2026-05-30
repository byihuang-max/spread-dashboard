// bb-theme-listener.js — iframe 子页面监听主页面主题切换
// 用法：在子页面 </body> 前加 <script src="../../bb-theme-listener.js"></script>
// 或者直接内联此逻辑
(function(){
  window.addEventListener("message",function(e){
    if(!e.data||e.data.type!=="bb-theme")return;
    var mode=e.data.mode;
    if(mode!=="dark"&&mode!=="light")return;
    window.__bbMode=mode;

    // 切换 body class
    if(mode==="light"){
      document.body.classList.add("bb-light");
    }else{
      document.body.classList.remove("bb-light");
    }

    // 切换 bloomberg-light.css link（如果存在）
    var lightLinks=document.querySelectorAll('link[href*="bloomberg-light"]');
    lightLinks.forEach(function(l){l.disabled=(mode!=="light");});
    // 如果 light 模式但没有 light css link，创建一个
    if(mode==="light"&&lightLinks.length===0){
      // 找到 bloomberg-override 的路径前缀
      var overrideLink=document.querySelector('link[href*="bloomberg-override"]');
      var prefix="";
      if(overrideLink){
        var href=overrideLink.getAttribute("href");
        prefix=href.substring(0,href.lastIndexOf("/")+1);
      }
      var l2=document.createElement("link");
      l2.rel="stylesheet";l2.href=prefix+"bloomberg-light.css?v="+Date.now();
      document.head.appendChild(l2);
    }

    // 更新 Chart.js 图表
    if(typeof Chart!=="undefined"){
      Chart.defaults.color=mode==="light"?"#475569":"#888";
      Chart.defaults.borderColor=mode==="light"?"#e2e8f0":"#2a2a2a";
      Object.values(Chart.instances||{}).forEach(function(c){
        try{c.update();}catch(_e){}
      });
    }
  });

  // 过渡动画
  var s=document.createElement("style");
  s.textContent="body,.card,table,th,td,.chart-container{transition:background-color .35s ease,color .35s ease,border-color .35s ease;}";
  document.head.appendChild(s);
})();
