window.Screens = window.Screens || {};

/* 演示用大纲与成稿（对应选题 p1：中芯扩产） */
const DEMO_OUTLINE = [
  { h: '一、先说结论：这不是抢跑，是被迫应战', note: '把"被动应对"的判断放在最前面' },
  { h: '二、被误读的地方：75 亿美元不是重点', note: '重点是国产设备占比，用各家口径差异做证据' },
  { h: '三、如果 2027 年汽车电子不兑现', note: '给边界条件，避免绝对化' },
  { h: '四、反方：也有人认为这是提前卡位', note: '必须真实存在的反方观点' },
  { h: '五、值得跟踪的三个指标', note: '可验证、可跟踪' }
];

const DEMO_SECTIONS = [
  { h: '一、先说结论：这不是抢跑，是被迫应战',
    p: '我倾向于把这次扩产读成一次被动应对，而不是主动抢跑。<span class="cite" data-ev="公告 · anns_d 2026-09-19：拟投资 75 亿美元，月产能 4 万片，2027Q2 投产">75 亿美元、月产能 4 万片、2027Q2 投产</span>这三个数字是公告给的，但真正的信息在别处：成熟制程的价格竞争仍在（公司 Q2 毛利率 20.4%，环比 +1.1pct），往上抬产能更像是在押注 2027 年汽车电子需求兑现这一前提。' },
  { h: '二、被误读的地方：75 亿美元不是重点',
    p: '市场把注意力放在投资额上，我认为这轮扩产里最有增量信息的地方是国产设备占比。财联社写"有望接近五成"，第一财经写"已超五成"，<span class="cite" data-ev="事件簇对比：财联社 09:42 vs 第一财经 10:31，口径不一致">两者口径不一致</span>——这个差异本身就是值得写的点，而不是需要抹平的矛盾。' },
  { h: '三、如果 2027 年汽车电子不兑现',
    p: '这是我给这个判断设的边界条件：若汽车电子与工控需求不及预期，新增产能会面临利用率压力，届时折旧对毛利的侵蚀会先于收入兑现出现。换句话说，这个判断成立的<strong>前提</strong>是需求兑现，不是产能落地。' },
  { h: '四、反方：也有人认为这是提前卡位',
    p: '反方观点确实存在，且理由不弱：在周期底部扩产、锁定设备与土地成本，等到需求起来时产能就是壁垒。<span class="cite" data-ev="券商研报·中金 2026-09-19：扩产落地节奏符合预期，维持跑赢行业">中金维持跑赢行业评级</span>。我的回应是：卡位逻辑成立的前提是需求终会来，而这一条无法被当下的证据证实——所以它与我的判断不是对错之争，是时间假设之争。' },
  { h: '五、值得跟踪的三个指标',
    p: '① 国产设备中标名单是否公开、占比口径能否统一；② 2027Q1 汽车电子订单的能见度（看公告里的长期协议）；③ 产能利用率的季度披露值。这三个指标在未来两三个季度内会陆续出现可验证数据。' }
];

window.Screens.compose = {
  title: 'AI 写作',
  step: '⑨',
  stepIdx: 8,

  render() {
    const st = App.state;
    const p = App.projectById(st.projectId);
    const stage = st.composeStage || 'idle';
    st.outline = st.outline || DEMO_OUTLINE.map(x => Object.assign({}, x));

    const todos = [
      ['装载素材（brief / facts / style-guide）', stage !== 'idle'],
      ['生成写作计划与大纲', stage === 'outline' || stage === 'writing' || stage === 'done'],
      ['HITL：等待用户确认大纲', stage === 'writing' || stage === 'done'],
      ['分段并行写作（section_writer）', stage === 'writing' || stage === 'done'],
      ['事实复核（对照 FactCard）', stage === 'done'],
      ['风格统一（style_editor）', stage === 'done'],
      ['标题 / 摘要候选', stage === 'done'],
      ['落库 article + citation_map', stage === 'done']
    ];

    let left = '';
    if (stage === 'idle') {
      const wAnn = p.newsIds.filter(i => App.hasAnn(i));
      const wFc = p.newsIds.filter(i => DB.factCards[i]);
      left = `
      <div class="card">
        <div class="card-h"><h3>素材装载</h3><div class="sub">写进虚拟文件系统，供子代理按需读取</div></div>
        <div class="card-b">
          <div class="fs-tree">
            <span class="dir">/</span><br>
            ├─ <span class="f">brief.md</span>　选题简报（${p.newsIds.length} 条素材，其中 ${wAnn.length} 条带点评）<br>
            ├─ <span class="dir">facts/</span><br>
            ${wFc.length
              ? wFc.map(i => '│　├─ <span class="f">fact_' + i + '.md</span>　' +
                  App.newsById(i).title.slice(0, 12) + '…·' + DB.factCards[i].facts.length + ' 条断言<br>').join('')
              : '│　└─ <span class="faint">（无 FactCard）</span><br>'}
            ├─ <span class="f">style-guide.md</span>　公众号深度复盘体 v4 + 人格 v7<br>
            └─ <span class="dir">draft/</span>　（待写入）
          </div>
          <div class="sep"></div>
          <div class="small muted"><strong>Brief 摘要：</strong>${p.require || '（未填写写作要求）'}</div>
          ${wAnn.length
            ? '<div class="sep"></div><div class="small muted">观点来源：' +
              wAnn.map(i => '<span class="tag brand">素材 ' + i + ' 的点评</span>').join(' ') + '</div>'
            : '<div class="sep"></div><div class="note warn small">这组素材<strong>没有点评</strong>，将走<strong>素材综述模式</strong>：'
              + '有事实、有结构，但没有你的判断。随时可以回素材补点评再重写。</div>'}
          <div class="sep"></div>
          <div class="row">
            <button class="btn btn-primary" onclick="Compose.genOutline()">${Icon('wand')} 生成大纲</button>
            <button class="btn" onclick="App.toast('先调整提示词组合再生成')">${Icon('quote')} 换一套提示词</button>
            <a class="btn" href="#/projects">${Icon('bookmark')} 调整素材</a>
          </div>
        </div>
      </div>`;
    } else if (stage === 'outline') {
      left = `
      <div class="note" style="margin-bottom:14px">
        <strong>⏸ 已暂停 · interrupt：outline_approval</strong><br>
        大纲已生成，流程停在这里等你确认。这是 HITL 主线的第一个断点——
        如果直接写完再让用户改，用户面对的是 3000 字而不是 5 个标题。
      </div>
      <div class="card">
        <div class="card-h"><h3>大纲</h3><div class="sub">可增删 / 调序 / 补要点</div>
          <div class="right"><button class="btn btn-sm" onclick="Compose.regen()">${Icon('refresh')} 重新生成</button></div>
        </div>
        <div class="card-b">
          ${st.outline.map((o, i) => `
            <div class="outline-item">
              <div class="idx">${i + 1}</div>
              <div class="oi">
                <input class="inp" value="${App.esc(o.h)}" onchange="Compose.edit(${i},'h',this.value)" style="margin-bottom:5px">
                <input class="inp" value="${App.esc(o.note)}" placeholder="要点提示" onchange="Compose.edit(${i},'note',this.value)">
              </div>
              <div class="col">
                <button class="iconbtn" onclick="Compose.move(${i},-1)">${Icon('chevronUp')}</button>
                <button class="iconbtn" onclick="Compose.move(${i},1)">${Icon('chevronDown')}</button>
                <button class="iconbtn" onclick="Compose.del(${i})">${Icon('trash')}</button>
              </div>
            </div>`).join('')}
          <div class="row" style="margin-top:8px">
            <input class="inp" id="newSec" placeholder="补充一个章节或要点…">
            <button class="btn" onclick="Compose.add()">${Icon('plus')} 添加</button>
          </div>
        </div>
        <div class="card-b" style="border-top:1px solid var(--line-2)">
          <div class="row between">
            <span class="small muted">确认后开始分段写作；放弃则回到 ready 状态</span>
            <div class="row">
              <button class="btn" onclick="Compose.cancel()">放弃大纲</button>
              <button class="btn btn-primary" onclick="Compose.startWrite()">${Icon('bolt')} 确认并开始写作</button>
            </div>
          </div>
        </div>
      </div>`;
    } else {
      left = `
      <div class="stream" id="stream">${stage === 'done' ? Compose.fullHtml() : '<span class="ph">等待 WriterAgent…</span>'}</div>
      ${stage === 'done' ? `
      <div class="row" style="margin-top:14px">
        <button class="btn btn-primary btn-lg" onclick="App.go('article')">${Icon('file')} 去编辑定稿</button>
        <button class="btn" onclick="Compose.reset()">${Icon('refresh')} 重新写作</button>
        <div class="spacer"></div>
        <span class="small muted">2860 字 · 用时 68s · 成本 ¥2.86 · 引用 6 处（全部映射到 FactCard）</span>
      </div>` : ''}`;
    }

    return `
<div class="row between" style="margin-bottom:12px">
  <div class="small muted">选题：<strong>${p.title}</strong> · ${p.platform} · ${p.words} 字</div>
  <div class="row">
    ${['idle', 'outline', 'writing', 'done'].map((s, i) =>
      '<span class="tag ' + (stage === s ? 'brand' : '') + '">' + ['装载', '大纲', '写作', '成稿'][i] + '</span>').join('')}
  </div>
</div>

<div class="compose-grid">
  <div>${left}</div>
  <div class="col">
    <div class="card">
      <div class="card-h"><h3>Agent 在做什么</h3><div class="sub">让用户理解"它在干啥"而不是干等</div></div>
      <div class="card-b">
        ${todos.map(t => `<div class="todo-item ${t[1] ? 'done' : ''}">
          ${Icon(t[1] ? 'checkCircle' : 'clock')}<span>${t[0]}</span></div>`).join('')}
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>中途指令</h3><div class="sub">写作过程中可直接插话</div></div>
      <div class="card-b">
        <div class="row">
          <input class="inp" id="cmd" placeholder="例：第二段压缩一半 / 加一段反方观点">
          <button class="btn" onclick="Compose.cmd()">发送</button>
        </div>
        <div class="row wrap" style="margin-top:8px">
          ${['第二段压缩一半', '加一段反方观点', '语气再硬一点', '把数据都补上口径'].map(c =>
            '<span class="chip tiny" onclick="document.getElementById(\'cmd\').value=\'' + c + '\'">' + c + '</span>').join('')}
        </div>
      </div>
    </div>

    ${stage === 'done' ? `
    <div class="card">
      <div class="card-h"><h3>事实复核</h3><div class="sub">对照 FactCard，禁止编造引用</div></div>
      <div class="card-b small">
        <div class="row"><span class="tag ok">${Icon('check')}</span><span class="muted">6 处事实句全部映射到 FactCard</span></div>
        <div class="row" style="margin-top:6px"><span class="tag warn">${Icon('alert')}</span><span class="muted">1 处"超五成"存在口径冲突 → 已降级为观点句并标注</span></div>
        <div class="row" style="margin-top:6px"><span class="tag danger">${Icon('ban')}</span><span class="muted">0 处编造引用</span></div>
      </div>
    </div>` : ''}

    <div class="card">
      <div class="card-h"><h3>护栏（硬约束）</h3></div>
      <div class="card-b small muted">
        <p style="margin:0 0 6px">1. 每个事实句必须能映射到 FactCard 的某个 FactItem，否则降级为观点句或删除；</p>
        <p style="margin:0 0 6px">2. 不生成 FactCard 中不存在的数字、日期、人名、机构名；</p>
        <p style="margin:0">3. 输出附 <span class="mono">citation_map</span>：段落 → 资讯/证据，供"可追溯"要求。</p>
      </div>
    </div>
  </div>
</div>`;
  },

  mount(root) {
    if (App.state.composeStage === 'writing') Compose.runStream(root);
  }
};

window.Compose = {
  refresh() {
    const page = document.getElementById('page');
    page.innerHTML = window.Screens.compose.render();
    window.Screens.compose.mount(page);
  },
  genOutline() {
    App.state.composeStage = 'outline';
    App.state.outline = DEMO_OUTLINE.map(x => Object.assign({}, x));
    App.save(); Compose.refresh();
    App.toast('大纲已生成 · 流程暂停等待确认');
  },
  regen() { App.toast('重新生成大纲（保留你已修改的章节）'); },
  cancel() {
    App.state.composeStage = 'idle'; App.save(); Compose.refresh();
    App.toast('已放弃大纲 · 选题回到 ready');
  },
  edit(i, k, v) { App.state.outline[i][k] = v; App.save(); },
  move(i, d) {
    const o = App.state.outline, j = i + d;
    if (j < 0 || j >= o.length) return;
    const t = o[i]; o[i] = o[j]; o[j] = t; App.save(); Compose.refresh();
  },
  del(i) { App.state.outline.splice(i, 1); App.save(); Compose.refresh(); },
  add() {
    const v = document.getElementById('newSec').value.trim();
    if (!v) return;
    App.state.outline.push({ h: v, note: '' }); App.save(); Compose.refresh();
  },
  cmd() {
    const v = document.getElementById('cmd').value.trim();
    if (!v) return;
    document.getElementById('cmd').value = '';
    App.toast('指令已注入：' + v + '（走 update_state 续跑，不打断已完成段落）');
  },
  startWrite() {
    App.state.composeStage = 'writing'; App.save(); Compose.refresh();
  },
  reset() {
    App.state.composeStage = 'idle'; App.save(); Compose.refresh();
  },
  fullHtml() {
    return '<h2>' + App.projectById(App.state.projectId).title + '</h2>' +
      DEMO_SECTIONS.map(s => '<h2>' + s.h + '</h2><p>' + s.p + '</p>').join('');
  },
  runStream(root) {
    const box = root.querySelector('#stream');
    if (!box) return;
    box.innerHTML = '<h2>' + App.projectById(App.state.projectId).title + '</h2>';
    let i = 0;
    const typeSec = () => {
      if (i >= DEMO_SECTIONS.length) {
        App.state.composeStage = 'done'; App.save();
        setTimeout(() => { Compose.refresh(); App.toast('成稿完成 · 6 处引用已映射到 FactCard'); }, 300);
        return;
      }
      const s = DEMO_SECTIONS[i];
      const h = document.createElement('h2'); h.textContent = s.h; box.appendChild(h);
      const p = document.createElement('p'); box.appendChild(p);
      // 富文本段落：按 HTML 标签分段逐字输出
      const raw = s.p;
      let buf = '', k = 0;
      const caret = document.createElement('span'); caret.className = 'caret'; box.appendChild(caret);
      const timer = setInterval(() => {
        k += 6;
        p.innerHTML = raw.slice(0, k);
        if (k >= raw.length) {
          clearInterval(timer); caret.remove(); i++;
          setTimeout(typeSec, 320);
        }
      }, 26);
    };
    setTimeout(typeSec, 400);
  }
};
