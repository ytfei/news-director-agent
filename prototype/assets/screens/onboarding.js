window.Screens = window.Screens || {};

window.Screens.onboarding = {
  title: '首次使用引导',

  render() {
    const s = Onboard.step;
    const W = ['兴趣画像', '数据源', '风格资产', '确认', '完成'];
    const allInd = ['半导体', '电力设备', '食品饮料', '计算机', '机械设备', '医药', '银行', '汽车'];

    let body = '';
    if (s === 0) {
      body = `
        <div class="small muted" style="margin-bottom:12px">第 1 步：你关注什么？决定收件箱里有什么。不知道就先按默认。</div>
        <div class="field"><label class="lb">市场</label>
          <div class="row wrap">${['A股', '港股', '美股', '宏观'].map(m =>
            '<span class="chip' + (DB.profile.markets.includes(m) ? ' on' : '') + '" onclick="this.classList.toggle(\'on\')">' + m + '</span>').join('')}</div></div>
        <div class="field"><label class="lb">行业 / 板块</label>
          <div class="row wrap">${allInd.map(m =>
            '<span class="chip' + (DB.profile.industries.includes(m) ? ' on' : '') + '" onclick="this.classList.toggle(\'on\')">' + m + '</span>').join('')}</div></div>
        <div class="field"><label class="lb">内容类型</label>
          <div class="row wrap">${['快讯', '长文', '公告', '政策', '研报'].map(m =>
            '<span class="chip' + (DB.profile.types.includes(m) ? ' on' : '') + '" onclick="this.classList.toggle(\'on\')">' + m + '</span>').join('')}</div></div>
        <div class="field"><label class="lb">屏蔽词</label>
          <div class="row wrap">${DB.profile.blocked.map(m => '<span class="chip on">' + m + '</span>').join('')}
          <span class="chip">${Icon('plus')} 添加</span></div></div>`;
    } else if (s === 1) {
      body = `
        <div class="small muted" style="margin-bottom:12px">第 2 步：数据源。默认已启用平台 token，也可以填自己的。</div>
        <div class="card" style="margin-bottom:12px">
          <div class="card-b">
            <div class="row between"><div class="small"><strong>Tushare Pro</strong> <span class="tag ok">默认启用</span></div>
              <span class="small muted">平台 token</span></div>
            <div class="sep"></div>
            <div class="tiny faint" style="margin-bottom:6px">权限探测结果（填自己的 token 可解锁更多）</div>
            <div class="row wrap">
              <span class="tag ok">major_news</span><span class="tag ok">cctv_news</span>
              <span class="tag danger">news（快讯）</span><span class="tag danger">anns_d（公告）</span>
              <span class="tag danger">npr（政策）</span><span class="tag danger">research_report</span>
            </div>
            <div class="note warn small" style="margin-top:10px">当前 token 拿不到<strong>快讯 / 公告 / 政策 / 研报</strong>。
            公告与政策是主理人的高价值素材，建议填自己的 token 或等第二数据源接入。</div>
          </div>
        </div>
        <div class="field"><label class="lb">我自己的 token（可选）</label>
          <input class="inp" placeholder="粘贴 token，保存后立即探测权限"></div>`;
    } else if (s === 2) {
      body = `
        <div class="small muted" style="margin-bottom:12px">第 3 步：建立风格资产（二选一）。这决定"写出来的像不像你"。</div>
        <div class="grid g2">
          <div class="ia-card" onclick="Onboard.pick(this)" style="border-color:var(--brand)">
            <div class="lv">快速</div><h4>从官方模板库选一套</h4>
            <ul><li>雪球短评体</li><li>公众号深度复盘体</li><li>政策解读体</li></ul>
          </div>
          <div class="ia-card" onclick="Onboard.pick(this)">
            <div class="lv">进阶</div><h4>粘贴 3~5 篇历史文章</h4>
            <ul><li>系统提取风格画像</li><li>生成初始提示词草稿</li><li>约 1 分钟</li></ul>
          </div>
        </div>
        <div class="field" style="margin-top:12px"><label class="lb">或粘贴一篇旧作</label>
          <textarea class="inp" rows="4" placeholder="把以前写过的一段粘进来…"></textarea></div>
        <button class="btn btn-sm" onclick="App.toast('已提取 12 条用词偏好 → 生成提示词草稿 v1')">${Icon('spark')} 提取风格</button>`;
    } else if (s === 3) {
      body = `
        <div class="small muted" style="margin-bottom:12px">第 4 步：确认一下。</div>
        <table class="tbl">
          <tbody>
            <tr><td style="width:110px" class="small muted">市场</td><td class="small">${DB.profile.markets.join(' / ')}</td></tr>
            <tr><td class="small muted">行业</td><td class="small">${DB.profile.industries.join(' / ')}</td></tr>
            <tr><td class="small muted">类型</td><td class="small">${DB.profile.types.join(' / ')}</td></tr>
            <tr><td class="small muted">数据源</td><td class="small">Tushare Pro（平台 token）· 2/6 接口可用</td></tr>
            <tr><td class="small muted">风格资产</td><td class="small">公众号深度复盘体 v4 + 人格 v7</td></tr>
          </tbody>
        </table>
        <div class="sep"></div>
        <div class="small muted">完成后系统会立即触发一次<strong>近 7 天历史资讯回填</strong>，所以第一次打开就有东西可看。</div>`;
    } else {
      body = `
        <div class="center" style="padding:20px 0">
          <div style="font-size:40px;line-height:1">${Icon('checkCircle')}</div>
          <h3 style="margin:12px 0 6px">设置完成</h3>
          <div class="small muted">正在回填近 7 天资讯…</div>
          <div class="progress" style="margin:16px auto 6px;max-width:320px"><i style="width:78%"></i></div>
          <div class="tiny faint">已命中 214 条 · 预计 20 秒</div>
        </div>
        <div class="sep"></div>
        <div class="note small">整个引导目标 <strong>&lt; 5 分钟</strong>。超过这个时间，用户会先怀疑产品而不是怀疑自己。</div>`;
    }

    return `
<div class="card">
  <div class="card-b">
    <div class="wizard-steps">
      ${W.map((w, i) => '<div class="w ' + (i === s ? 'on' : i < s ? 'done' : '') + '">' + (i + 1) + '. ' + w + '</div>').join('')}
    </div>
    ${body}
    <div class="sep"></div>
    <div class="row between">
      <button class="btn" ${s === 0 ? 'disabled' : ''} onclick="Onboard.go(${s - 1})">上一步</button>
      <div class="row">
        <button class="btn btn-ghost" onclick="App.go('inbox')">跳过引导</button>
        ${s < W.length - 1
          ? '<button class="btn btn-primary" onclick="Onboard.go(' + (s + 1) + ')">下一步</button>'
          : '<button class="btn btn-primary" onclick="App.toast(\'回填完成\');App.go(\'inbox\')">' + Icon('bolt') + ' 进入收件箱</button>'}
      </div>
    </div>
  </div>
</div>

<div class="grid g3" style="margin-top:14px">
  <div class="card"><div class="card-b small muted"><strong>为什么先配画像</strong><br>没有画像，收件箱就是另一个 RSS 阅读器，冷启动当天就会流失。</div></div>
  <div class="card"><div class="card-b small muted"><strong>为什么要风格资产</strong><br>"AI 味"是用户不认领作品的第一原因。风格必须在第一次写作前就位。</div></div>
  <div class="card"><div class="card-b small muted"><strong>为什么立刻回填</strong><br>新用户打开不能看到空白页。近 7 天回填是最低成本的"有东西可看"。</div></div>
</div>`;
  }
};

window.Onboard = {
  step: 0,
  go(i) {
    if (i < 0 || i > 4) return;
    Onboard.step = i;
    const page = document.getElementById('page');
    page.innerHTML = window.Screens.onboarding.render();
  },
  pick(el) {
    document.querySelectorAll('.ia-card').forEach(x => x.style.borderColor = '');
    el.style.borderColor = 'var(--brand)';
    App.toast('已选择：' + el.querySelector('h4').textContent);
  }
};
