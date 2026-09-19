window.Screens = window.Screens || {};

window.Screens.facts = {
  title: '事实卡片',
  step: '⑦',
  stepIdx: 6,

  render({ q }) {
    const id = +(q.id || 2);
    const fc = DB.factCards[id];
    const n = App.newsById(id);
    const stLabel = { verified: '已验证', contradicted: '有冲突', unverifiable: '无法验证', outdated: '已过时' };

    if (!fc) {
      return `<div class="card"><div class="card-b">
        <div class="empty">该资讯暂无 FactCard</div>
        <div class="row center" style="margin-top:10px">
          ${[1, 2].map(i => '<a class="btn btn-sm" href="#/facts?id=' + i + '">' + App.newsById(i).title.slice(0, 18) + '…</a>').join('')}
        </div></div></div>`;
    }

    return `
<div class="row" style="margin-bottom:12px">
  ${Object.keys(DB.factCards).map(k => `
    <a class="chip ${+k === id ? 'on' : ''}" href="#/facts?id=${k}">${App.newsById(k).title.slice(0, 16)}…</a>`).join('')}
  <div class="spacer"></div>
  <button class="btn btn-sm" onclick="App.toast('ResearcherAgent 重新补查（增量，只查未覆盖的断言）')">${Icon('refresh')} 重新补查</button>
</div>

<div class="card">
  <div class="card-h">
    <h3>${n.title.slice(0, 30)}…</h3>
    <div class="sub">FactCard · 资讯级事实基线</div>
    <div class="right"><span class="tag">${n.source}</span><span class="tag">${n.time}</span></div>
  </div>
  <div class="card-b">
    <div class="note small">由 <strong>ResearcherAgent</strong> 在 ingest 阶段<strong>异步预生成</strong>，review 时只读缓存。
    输入是「一条资讯」，<strong>不含用户点评</strong> —— 所以它能跨用户复用，这是成本模型里最大的一项优化。</div>
    <div class="sep"></div>
    <div class="small muted"><strong>背景脉络</strong><br>${fc.context}</div>
    <div class="row wrap" style="margin-top:10px">
      ${fc.symbols.map(s => '<span class="tag brand">' + s + '</span>').join('')}
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>事实断言 · ${fc.facts.length} 条</h3>
    <div class="sub">原子化 claim + 状态 + 证据 + 置信度</div></div>
  <div class="card-b tight">
    <table class="tbl">
      <thead><tr><th style="width:80px">状态</th><th>断言</th><th style="width:280px">证据</th><th style="width:70px">置信度</th></tr></thead>
      <tbody>
        ${fc.facts.map(f => `
        <tr>
          <td><span class="tag ${f.status === 'verified' ? 'ok' : f.status === 'contradicted' ? 'danger' : 'warn'}">${stLabel[f.status]}</span></td>
          <td>${f.claim}</td>
          <td class="small muted">${f.ev.length
            ? f.ev.map(e => '<div>' + e.src + ' · ' + e.date + '<div class="tiny faint">「' + e.snip + '」</div></div>').join('')
            : '<span class="faint">无 —— 按硬约束不得标 verified</span>'}</td>
          <td class="mono small">${f.conf}</td>
        </tr>`).join('')}
      </tbody>
    </table>
    <div class="sep"></div>
    <div class="row">
      <button class="btn btn-sm" onclick="App.toast('补充证据：粘贴来源链接 / 上传公告 PDF')">${Icon('plus')} 手动补充证据</button>
      <button class="btn btn-sm" onclick="App.toast('该卡片已被 3 个选题复用，节省约 ¥0.9')">${Icon('chart')} 复用情况</button>
    </div>
  </div>
</div>

<div class="grid g2">
  <div class="card">
    <div class="card-h"><h3>还没查清的（open_questions）</h3></div>
    <div class="card-b">
      ${fc.open.map(x => '<div class="row" style="align-items:flex-start;margin-bottom:7px">' +
        Icon('alert') + '<span class="small muted">' + x + '</span></div>').join('')}
      <div class="sep"></div>
      <div class="tiny muted">开放问题不写进文章；它们决定「哪些话不能说死」。</div>
    </div>
  </div>
  <div class="card">
    <div class="card-h"><h3>子代理分工</h3></div>
    <div class="card-b">
      <table class="tbl">
        <tbody>
          <tr><td style="width:130px" class="mono small">market_probe</td><td class="small muted">行情与资金流</td></tr>
          <tr><td class="mono small">filing_probe</td><td class="small muted">公告 / 财报 / 互动问答</td></tr>
          <tr><td class="mono small">policy_probe</td><td class="small muted">政策原文与宏观数据</td></tr>
          <tr><td class="mono small">timeline_probe</td><td class="small muted">事件时间线还原</td></tr>
          <tr><td class="mono small">web_probe ★</td><td class="small muted">网页检索 + 正文抓取（覆盖 tushare 之外的海外源）</td></tr>
        </tbody>
      </table>
      <div class="sep"></div>
      <div class="note warn small">点评里特有的断言不在资讯级基线里，由 fact 轨道在 review 时<strong>按需补查</strong>，
      结果写 <span class="mono">review_finding_evidence</span>，<strong>不写回</strong> fact_cards —— 避免污染可复用基线。</div>
    </div>
  </div>
</div>`;
  }
};
