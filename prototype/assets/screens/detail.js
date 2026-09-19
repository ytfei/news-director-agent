window.Screens = window.Screens || {};

/* 资讯详情：既作为抽屉（从列表打开），也可直接访问 #/detail?id=1 */
(function () {
  function body(id) {
    const n = App.newsById(id);
    if (!n) return '<div class="empty">未找到该资讯</div>';
    const cl = n.cluster;
    const fc = DB.factCards[id];

    const spark = [38, 44, 41, 52, 60, 55, 68, 74, 70, 82, 88, 84];

    return `
<div class="drawer-h">
  <div style="flex:1">
    <div class="row small muted" style="margin-bottom:5px">
      <span class="src"><strong>${n.source}</strong></span>·<span>${n.time}</span>·
      <span class="tag">${n.sourceType}</span>
      ${n.symbols.map(s => '<span class="tag brand">' + s + '</span>').join('')}
      <span class="tag ${n.imp === 'high' ? 'danger' : n.imp === 'mid' ? 'warn' : ''}">${n.imp === 'high' ? '重要' : n.imp === 'mid' ? '一般' : '参考'}</span>
    </div>
    <h2>${n.title}</h2>
  </div>
  <button class="iconbtn" onclick="this.closest('.drawer-mask').remove()">${Icon('x')}</button>
</div>

<div class="drawer-b">
  <div class="row" style="margin-bottom:14px">
    <button class="btn btn-sm">${Icon('star')} 评级</button>
    <button class="btn btn-sm">${Icon('bookmark')} 收藏</button>
    <button class="btn btn-sm">${Icon('eyeOff')} 隐藏</button>
    <div class="spacer"></div>
    <button class="btn btn-sm">${Icon('link')} 原文</button>
    <button class="btn btn-sm ${App.isMat(n.id) ? '' : 'btn-primary'}" onclick="this.closest('.drawer-mask').remove();App.go('news')">
      ${Icon('bookmark')} ${App.isMat(n.id) ? '已在素材库' : '加入素材'}</button>
    <button class="btn btn-primary btn-sm" onclick="this.closest('.drawer-mask').remove();App.go('annotate',{m:${n.id}})">
      ${Icon('pen')} 批注</button>
  </div>

  ${n.summary ? '<div class="note" style="margin-bottom:16px">' + n.summary + '</div>' : ''}

  ${n.symbols.length ? `
  <div class="card" style="margin-bottom:16px">
    <div class="card-h"><h3>关联标的 · ${n.symbols[0]}</h3><div class="sub">近 12 个交易日</div></div>
    <div class="card-b">
      <div class="spark">${spark.map((v, i) => '<i class="' + (i && v < spark[i - 1] ? 'dn' : 'up') + '" style="height:' + v + '%"></i>').join('')}</div>
      <div class="row small muted" style="margin-top:6px"><span>区间 +12.4%</span><span>·</span><span>换手 3.1%</span><span>·</span><span>主力净流入 +2.3 亿</span></div>
    </div>
  </div>` : ''}

  ${cl ? `
  <div class="card" style="margin-bottom:16px">
    <div class="card-h"><h3>事件簇 · ${cl.count} 家报道</h3>
      <div class="sub">同一事件的多源口径，差异处已标红</div></div>
    <div class="card-b tight">
      <table class="tbl">
        <thead><tr><th style="width:110px">来源</th><th style="width:80px">时间</th><th>标题 / 口径</th><th style="width:190px">差异</th></tr></thead>
        <tbody>
          ${cl.items.map(it => `<tr>
            <td><strong>${it.source}</strong></td>
            <td class="small muted">${it.time}</td>
            <td>${it.title}</td>
            <td class="small">${it.diff ? '<span class="diff">' + it.diff + '</span>' : '<span class="faint">—</span>'}</td>
          </tr>`).join('')}
        </tbody>
      </table>
      <div class="small muted" style="padding:0 4px 6px">★ 差异本身就是信息：多源交叉验证是「事实可信度」的来源，而不是让模型自己猜。</div>
    </div>
  </div>` : ''}

  <div class="card" style="margin-bottom:16px">
    <div class="card-h"><h3>全文</h3><div class="sub">${n.source}</div></div>
    <div class="card-b">${n.body.split('\n\n').map(p => '<p style="margin:0 0 12px">' + p + '</p>').join('')}</div>
  </div>

  ${fc ? `
  <div class="card" style="margin-bottom:16px">
    <div class="card-h"><h3>事实卡片 · FactCard</h3>
      <div class="sub">ingest 阶段异步预生成，review 时只读缓存（这是「检查 &lt; 8s」的前提）</div>
      <div class="right"><button class="btn btn-sm" onclick="this.closest('.drawer-mask').remove();App.go('facts',{id:${id}})">查看全部</button></div>
    </div>
    <div class="card-b">
      ${fc.facts.slice(0, 3).map(f => `
        <div class="row" style="align-items:flex-start;margin-bottom:9px">
          <span class="tag ${f.status === 'verified' ? 'ok' : f.status === 'contradicted' ? 'danger' : ''}">${
            { verified: '已验证', contradicted: '有冲突', unverifiable: '无法验证', outdated: '已过时' }[f.status]}</span>
          <div style="flex:1" class="small">${f.claim}
            <div class="tiny faint">${f.ev.length ? f.ev.map(e => e.src + ' · ' + e.date).join('；') : '无 evidence —— 不允许标 verified'}</div>
          </div>
          <span class="tiny mono muted">${f.conf}</span>
        </div>`).join('')}
    </div>
  </div>` : '<div class="note warn" style="margin-bottom:16px">该资讯尚未生成 FactCard（队列未完成）。没有事实基线时，fact 轨道的检查会退化为"无法验证"。</div>'}

  <div class="card">
    <div class="card-h"><h3>相关历史资讯 · 时间线</h3></div>
    <div class="card-b">
      <div class="timeline">
        <div class="tl-item"><div class="t">今天 ${n.time}</div><div class="c">${n.title.slice(0, 28)}…</div></div>
        <div class="tl-item"><div class="t">2026-08-28</div><div class="c">公司披露 2026Q2 财报，毛利率环比 +1.1pct</div></div>
        <div class="tl-item"><div class="t">2026-07-15</div><div class="c">行业媒体：成熟制程产能利用率回升至 85%</div></div>
        <div class="tl-item"><div class="t">2026-05-06</div><div class="c">上一轮扩产公告：投资 42 亿美元，月产能 2 万片</div></div>
      </div>
    </div>
  </div>
</div>`;
  }

  window.Detail = {
    open(id) { return App.drawer(body(id)); }
  };

  window.Screens.detail = {
    title: '资讯详情',
    render({ q }) {
      const id = q.id || 1;
      const n = App.newsById(id);
      return '<div class="card"><div class="card-h"><h3>' + App.esc(n.title) +
        '</h3><div class="right"><button class="btn btn-sm" id="openDrawer">打开详情抽屉</button>' +
        '<a class="btn btn-sm" href="#/news">返回资讯流</a></div></div>' +
        '<div class="card-b"><div class="empty">详情页在原型中以<strong>抽屉</strong>形态呈现（点下方按钮）。' +
        '真实实现里，列表点击标题 → 右侧抽屉，不打断浏览节奏。</div></div></div>';
    },
    mount(root) {
      const b = root.querySelector('#openDrawer');
      if (b) b.onclick = () => Detail.open(+App.route.q.id || 1);
      const id = +App.route.q.id || 1;
      setTimeout(() => Detail.open(id), 60);
    }
  };
})();
