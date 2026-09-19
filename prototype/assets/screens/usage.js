window.Screens = window.Screens || {};

window.Screens.usage = {
  title: '用量与配额',
  step: '⑪',
  stepIdx: 10,

  render() {
    const u = DB.usage;
    const pct = (a, b) => Math.min(100, Math.round(a / b * 100));
    const bar = (a, b, label) => `
      <div style="margin-bottom:12px">
        <div class="row between small"><span class="muted">${label}</span>
          <span><strong>${a}</strong> <span class="faint">/ ${b}</span></span></div>
        <div class="progress ${a / b > .8 ? 'warn' : ''}" style="margin-top:5px"><i style="width:${pct(a, b)}%"></i></div>
      </div>`;

    return `
<div class="grid g4" style="margin-bottom:14px">
  <div class="card stat"><div class="k">本月 token</div><div class="v">${(u.tokens / 1e6).toFixed(1)}<small>M</small></div><div class="d">—</div></div>
  <div class="card stat"><div class="k">本月成本</div><div class="v">¥${u.cost}</div><div class="d ${u.cost / u.quotaCost > .5 ? 'down' : ''}">硬上限 ¥${u.quotaCost}</div></div>
  <div class="card stat"><div class="k">单篇成本</div><div class="v">¥${u.perArticle}</div><div class="d">目标 ≤ ¥3</div></div>
  <div class="card stat"><div class="k">单次检查</div><div class="v">¥${u.perCheck}</div><div class="d">20 条批量</div></div>
</div>

<div class="grid g2">
  <div class="card">
    <div class="card-h"><h3>配额</h3><div class="sub">${u.plan} · ${u.month}</div></div>
    <div class="card-b">
      ${bar(u.cost, u.quotaCost, '成本')}
      ${bar(u.checks, u.quotaChecks, '检查次数')}
      ${bar(u.articles, u.quotaArticles, '写作篇数')}
      <div class="note danger small">超额<strong>直接拒绝</strong>，不是软提示。
      任务前置校验，拒绝时给出剩余额度与充值入口。</div>
    </div>
  </div>

  <div class="card">
    <div class="card-h"><h3>成本结构</h3></div>
    <div class="card-b tight">
      <table class="tbl">
        <thead><tr><th>环节</th><th style="width:70px">次数</th><th style="width:80px">token</th><th style="width:80px">成本</th></tr></thead>
        <tbody>
          ${u.rows.map(r => `<tr><td>${r.k}</td><td class="mono small">${r.n}</td>
            <td class="mono small">${r.tok}</td><td class="small"><strong>¥${r.cost}</strong></td></tr>`).join('')}
        </tbody>
      </table>
      <div class="small muted" style="padding:8px 4px 4px">
        最大的一项优化是 <strong>FactCard 按资讯预生成并跨用户复用</strong>：512 次预生成摊薄了 148 次检查 + 12 篇写作的事实成本。
      </div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>单位经济性</h3><div class="sub">★ 卖一单亏一单是最危险的风险</div></div>
  <div class="card-b">
    <table class="tbl">
      <thead><tr><th style="width:200px">项</th><th>说明</th></tr></thead>
      <tbody>
        <tr><td>现状测算</td><td class="small muted">日更用户月成本量级 ¥100~400，专业版 ¥199/月 —— <strong>若"无限检查 + 写作"，是亏损的</strong></td></tr>
        <tr><td>M1 已做</td><td class="small muted"><span class="mono">usage_records</span> 台账已建，但<strong>尚无累计逻辑与硬上限</strong>（TODO · P2-8）</td></tr>
        <tr><td>M3 前必须做</td><td class="small muted">Spike #7 实测单次 compose 与单次检查成本，回填定价模型</td></tr>
        <tr><td>若不达标</td><td class="small muted">改为次数分档（如 30 次检查 + 8 篇写作/月），而不是继续"无限"</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>这一页与「沉淀」的关系</h3></div>
  <div class="card-b small muted">
    步骤 ⑪ 沉淀：文章入 articles、观点入观点库、记录提示词版本，并把<strong>耗时 / 成本 / 人工改动率</strong>送到这一页。
    人工改动率是判断"这篇到底像不像我"的唯一可量化指标（目标 ≤ 30%）。
  </div>
</div>`;
  }
};
