window.Screens = window.Screens || {};

window.Screens.review = {
  title: 'AI 体检报告',
  step: '⑦',
  stepIdx: 6,

  render() {
    const st = App.state;
    /* 体检报告的输入 = 素材库里「写过点评」的那些素材 */
    const anns = Object.keys(st.materials).map(Number).filter(i => App.hasAnn(i)).map(i => App.annOf(i));
    const cur = anns.find(a => a.id === st.curAnn) || anns[0] || App.annOf(1);

    const tally = { passed: 0, needs_revision: 0, blocked: 0 };
    anns.forEach(a => tally[App.verdictOf(a.id)]++);
    const openBlockers = anns.reduce((s, a) =>
      s + (DB.findings[a.id] || []).filter(f => f.severity === 'blocker' && !st.fstates[f.id]).length, 0);
    const openFindings = anns.reduce((s, a) =>
      s + (DB.findings[a.id] || []).filter(f => !st.fstates[f.id]).length, 0);
    const overall = openBlockers ? 'blocked' : (tally.needs_revision || tally.passed < anns.length ? 'needs_revision' : 'passed');

    const vIcon = { passed: 'checkCircle', needs_revision: 'alert', blocked: 'ban' };

    return `
<div class="verdict-bar ${overall}">
  ${Icon(vIcon[overall], 'ico')}
  <div>
    <div class="big">${App.verdictLabel[overall]}</div>
    <div class="small muted">${anns.length} 条点评 · ${tally.passed} 通过 / ${tally.needs_revision} 需修改 / ${tally.blocked} 有红线 · 待处理 ${openFindings} 项</div>
  </div>
  <div class="spacer"></div>
  <button class="btn btn-sm" onclick="App.toast('只复检变更条目（增量），不必全量重跑')">${Icon('refresh')} 复检变更</button>
  <button class="btn btn-sm" onclick="App.go('annotate')">${Icon('pen')} 回去改点评</button>
  ${openBlockers
    ? '<button class="btn btn-primary" disabled title="存在未处理的合规红线">⛔ 先解决红线</button>'
    : '<button class="btn btn-primary" onclick="App.go(\'projects\')">' + Icon('folder') + ' 创建选题并写作</button>'}
</div>

<div class="workbench" style="grid-template-columns:236px minmax(0,1fr)">
  <div class="pane">
    <div class="pane-h">${Icon('pen')} 点评 ${anns.length} 条</div>
    <div class="pane-b">
      <div class="itemlist">
        ${anns.map(a => {
          const v = App.verdictOf(a.id);
          const fs = DB.findings[a.id] || [];
          const open = fs.filter(f => !st.fstates[f.id]).length;
          const m = App.mat(a.newsId);
          return `<div class="itemrow ${a.id === cur.id ? 'active' : ''}" data-act="pick" data-id="${a.id}">
            <div class="row between">
              <div class="t">${App.newsById(a.newsId).title.slice(0, 20)}…</div>
              <span class="tag ${v === 'passed' ? 'ok' : v === 'blocked' ? 'danger' : 'warn'}">${App.verdictLabel[v]}</span>
            </div>
            <div class="m">${m ? '<span class="tag" style="background:var(--brand);color:#fff;border-color:var(--brand)">' + m.score + '</span> ' + m.topics.map(t => '<span class="tag">' + t + '</span>').join(' ') : ''}</div>
            <div class="m">${fs.length} 项发现 · 待处理 ${open}</div>
            <div class="snip">${App.esc(App.annText(a)).slice(0, 60)}…</div>
          </div>`;
        }).join('')}
      </div>
      <div class="sep"></div>
      <div class="tiny muted" style="padding:0 2px">项目级一致性检查：跨条比对「对 A 乐观、对同类 B 悲观但理由相同」这类矛盾，报 medium。</div>
    </div>
  </div>

  <div>
    <div class="card">
      <div class="card-h">
        <h3>点评原文</h3>
        <div class="sub">${App.newsById(cur.newsId).title.slice(0, 24)}…</div>
        <div class="right"><span class="tag">版本 v4</span></div>
      </div>
      <div class="card-b" style="font-size:14px;line-height:1.9">
        ${Review.renderText(cur)}
      </div>
    </div>

    <div class="card">
      <div class="card-h">
        <h3>体检发现 · ${(DB.findings[cur.id] || []).length} 项</h3>
        <div class="sub">三轨并行产生，severity 排序</div>
        <div class="right">
          <button class="btn btn-sm btn-ghost" data-act="fold">收起 提示级</button>
        </div>
      </div>
      <div class="card-b" id="findings">
        ${(DB.findings[cur.id] || []).map(f => Review.findingCard(f)).join('') ||
          '<div class="empty">这条点评没有发现问题</div>'}
      </div>
    </div>
  </div>
</div>

<div class="grid g2" style="margin-top:14px">
  <div class="card">
    <div class="card-h"><h3>处置规则</h3></div>
    <div class="card-b">
      <table class="tbl">
        <tbody>
          <tr><td style="width:88px"><span class="tag ok">采纳</span></td><td class="small muted">用 suggestion 替换原文 → 生成新的 annotation_version，finding 标 accepted</td></tr>
          <tr><td><span class="tag danger">驳回</span></td><td class="small muted">必填理由 → 记入历史用于降低误报；同一问题不再重复报</td></tr>
          <tr><td><span class="tag">忽略</span></td><td class="small muted">不改正文，仅关闭该 finding</td></tr>
          <tr><td><span class="tag solid">blocker</span></td><td class="small muted">必须解决才能进入写作；其余 severity 可带提醒继续</td></tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="card">
    <div class="card-h"><h3>为什么阈值必须分轨道</h3></div>
    <div class="card-b">
      <div class="note small">验收指标里「事实误报率 &lt; 15%」要高精度，「合规召回率 &gt; 95%」要高召回 ——
      <strong>统一阈值下两者互斥</strong>。所以 fact 走高阈值、compliance 走低阈值 + 红线词库优先命中。</div>
      <div class="sep"></div>
      <div class="small muted">★ 硬约束：<strong>没有 evidence 的 claim 不允许标 verified</strong>，只能标 unverifiable。</div>
    </div>
  </div>
</div>`;
  },

  mount(root) {
    root.addEventListener('click', (e) => {
      const el = e.target.closest('[data-act]');
      if (!el) return;
      const act = el.dataset.act;
      const id = el.dataset.id;

      if (act === 'pick') {
        App.state.curAnn = id; App.save();
        const page = document.getElementById('page');
        page.innerHTML = window.Screens.review.render();
        window.Screens.review.mount(page);
      } else if (act === 'fold') {
        App.toast('提示级（info）默认折叠 —— 避免报告太啰嗦');
      } else if (act === 'adopt') {
        Review.adopt(id);
      } else if (act === 'dismiss') {
        Review.dismiss(id);
      } else if (act === 'ignore') {
        App.state.fstates[id] = 'ignored'; App.save();
        App.toast('已忽略（不改正文）'); Review.refresh();
      } else if (act === 'evidence') {
        Review.evidence(id);
      }
    });
  }
};

window.Review = {
  /* 原文 + 待处理 finding 的划词高亮 */
  renderText(a) {
    const txt = App.annText(a);
    let out = App.esc(txt);
    (DB.findings[a.id] || []).filter(f => !App.state.fstates[f.id] && f.quote).forEach(f => {
      out = out.split(App.esc(f.quote)).join(
        '<span class="hl ' + f.severity + '">' + App.esc(f.quote) + '</span>');
    });
    return out || '<span class="faint">（空）</span>';
  },

  findingCard(f) {
    const s = App.state.fstates[f.id];
    const tIcon = { fact: 'search', logic: 'bulb', compliance: 'shield', tone: 'user' }[f.track];
    return `
<div class="finding ${f.severity} ${s ? 'done' : ''}">
  <div class="fh">
    <span class="tag ${f.track === 'compliance' ? 'danger' : f.track === 'fact' ? 'info' : 'brand'}">
      ${Icon(tIcon)} ${App.trackLabel[f.track]}</span>
    <span class="tag ${f.severity === 'blocker' ? 'danger' : f.severity === 'high' ? 'warn' : ''}">${App.sevLabel[f.severity]}</span>
    ${f.evidence && f.evidence.length ? '<span class="tag ok">' + Icon('check') + ' 带证据</span>' : ''}
    <div class="spacer"></div>
    <span class="tiny faint mono">span ${f.quote ? App.esc(f.quote).length : 0} 字符</span>
  </div>
  <div class="quote">${App.esc(f.quote || '（整条点评）')}</div>
  <div class="msg">${f.message}</div>
  ${f.suggestion ? `<div class="sug"><strong>建议替换为：</strong>${f.suggestion}</div>` : ''}
  ${f.evidence && f.evidence.length ? `
    <div class="ev">${Icon('link')}<div>
      ${f.evidence.map(x => '<div>' + x.src + ' · ' + x.date + ' · 置信度 ' + x.conf +
        '<div class="tiny faint">「' + x.snippet + '」</div></div>').join('')}
    </div>
    <button class="btn btn-sm btn-ghost" data-act="evidence" data-id="${f.id}">证据面板</button>
  </div>` : ''}
  <div class="acts">
    ${f.suggestion ? '<button class="btn btn-sm btn-primary" data-act="adopt" data-id="' + f.id + '">' + Icon('check') + ' 采纳建议</button>' : ''}
    <button class="btn btn-sm" data-act="dismiss" data-id="${f.id}">${Icon('x')} 驳回</button>
    <button class="btn btn-sm btn-ghost" data-act="ignore" data-id="${f.id}">忽略</button>
    ${s ? '<span class="tag ' + (s === 'accepted' ? 'ok' : s === 'dismissed' ? 'danger' : '') + '">已' +
      ({ accepted: '采纳', dismissed: '驳回', ignored: '忽略' }[s]) + '</span>' : ''}
  </div>
  ${s === 'accepted' ? '<div class="res">已采纳 · 生成 annotation_version v5</div>' : ''}
  ${s === 'dismissed' ? '<div class="res">已驳回 · 理由：' + App.esc(App.state.reasons[f.id] || '') + '（记为"已确认"，不再重复报）</div>' : ''}
</div>`;
  },

  adopt(fid) {
    const st = App.state;
    const a = DB.annotations.find(x => (DB.findings[x.id] || []).some(f => f.id === fid));
    const f = DB.findings[a.id].find(x => x.id === fid);
    const txt = App.annText(a);
    st.annTexts[a.id] = f.quote ? txt.replace(f.quote, f.suggestion) : txt;
    st.fstates[fid] = 'accepted';
    App.save();
    App.toast('已采纳 · 原文已替换，生成新版本');
    Review.refresh();
  },

  dismiss(fid) {
    App.modal({
      title: '驳回这条发现',
      body: '<div class="small muted" style="margin-bottom:10px">必填理由。理由会进入历史，用于后续降低同类误报；驳回后该问题不再重复报。</div>' +
        '<div class="field"><label class="lb">理由</label><textarea class="inp" id="rsn" rows="3" placeholder="例：这里的 30% 指的是单季度含税口径，我已核实过来源"></textarea></div>' +
        '<div class="row wrap"><span class="chip" onclick="document.getElementById(\'rsn\').value=\'口径不同，我指的是单季度\'">口径不同</span>' +
        '<span class="chip" onclick="document.getElementById(\'rsn\').value=\'这是我的判断，不是事实断言\'">这是判断不是事实</span>' +
        '<span class="chip" onclick="document.getElementById(\'rsn\').value=\'我有未在文中的一手信息\'">有一手信息</span></div>',
      footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">取消</button>' +
        '<button class="btn btn-danger" onclick="Review.doDismiss(\'' + fid + '\',this)">确认驳回</button>'
    });
  },

  doDismiss(fid, btn) {
    const mask = btn.closest('.mask');
    const r = mask.querySelector('#rsn').value.trim();
    if (!r) { App.toast('驳回必须填理由'); return; }
    App.state.reasons[fid] = r;
    App.state.fstates[fid] = 'dismissed';
    App.save(); App.closeModal(mask);
    App.toast('已驳回 · 已记住，不再重复报');
    Review.refresh();
  },

  evidence(fid) {
    const a = DB.annotations.find(x => (DB.findings[x.id] || []).some(f => f.id === fid));
    const f = DB.findings[a.id].find(x => x.id === fid);
    App.modal({
      title: '证据面板',
      body: (f.evidence.length ? f.evidence.map(x => `
        <div class="card" style="margin-bottom:10px">
          <div class="card-b">
            <div class="row between"><strong class="small">${x.src}</strong><span class="tiny muted">${x.date}</span></div>
            <div class="small muted" style="margin-top:6px;line-height:1.7">「${x.snippet}」</div>
            <div class="row" style="margin-top:8px"><span class="tag ok">置信度 ${x.conf}</span>
              <button class="btn btn-sm btn-ghost" onclick="App.toast('打开原文链接')">${Icon('link')} 原文</button></div>
          </div>
        </div>`).join('')
        : '<div class="note warn">这条发现没有绑定 evidence —— 按硬约束，没有证据的 claim 只能标 unverifiable，不能标 verified。</div>') +
        '<div class="small muted">证据来源：公告 / 财报 / 行情 / 政策原文 / 网页检索（web_probe）。</div>',
      footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">关闭</button>'
    });
  },

  refresh() {
    const page = document.getElementById('page');
    page.innerHTML = window.Screens.review.render();
    window.Screens.review.mount(page);
  }
};
