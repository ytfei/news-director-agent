window.Screens = window.Screens || {};

const TODAY_A = '2026-09-19';

window.Screens.annotate = {
  title: '点评工作台',
  step: '⑤⑥',
  stepIdx: 4,

  render({ q }) {
    const st = App.state;
    const f = st.matFilter || (st.matFilter = { date: '', min: 0, topics: [], noAnn: false });

    /* 素材库 = 工作台的唯一数据源 */
    const mats = App.matList(f);
    const nid = q.m ? +q.m : (mats.length ? mats[0].newsId : null);
    if (nid == null) {
      return `<div class="card"><div class="card-b">
        <div class="empty">素材库还是空的 —— 先去资讯中心把感兴趣的资讯「加入素材」</div>
        <div class="row center" style="margin-top:12px">
          <a class="btn btn-primary" href="#/news">${Icon('news')} 去资讯中心挑素材</a>
        </div></div></div>`;
    }
    st.curAnn = 'a' + nid; App.save();

    const cur = App.annOf(nid);
    const n = App.newsById(nid);
    const m = App.mat(nid);
    const withAnn = mats.filter(x => App.hasAnn(x.newsId));

    return `
<div class="card" style="margin-bottom:14px">
  <div class="card-b">
    <div class="row wrap" style="gap:10px">
      <span class="small"><strong>素材库</strong> <span class="faint">· 工作台只处理素材，不直接处理资讯</span></span>
      <div class="fi">日期
        <select onchange="AnnFilter('date',this.value)">
          <option value="">全部日期</option>
          <option value="${TODAY_A}" ${f.date === TODAY_A ? 'selected' : ''}>${TODAY_A}（今天）</option>
          <option value="2026-09-18" ${f.date === '2026-09-18' ? 'selected' : ''}>2026-09-18</option>
        </select>
      </div>
      <div class="fi">评分
        <select onchange="AnnFilter('min',+this.value)">
          <option value="0" ${!f.min ? 'selected' : ''}>全部</option>
          <option value="8" ${f.min === 8 ? 'selected' : ''}>≥ 8</option>
          <option value="6" ${f.min === 6 ? 'selected' : ''}>≥ 6</option>
        </select>
      </div>
      <div class="row wrap">
        ${App.topics().slice(0, 10).map(t =>
          '<span class="chip tiny' + (f.topics.includes(t) ? ' on' : '') + '" onclick="AnnTopic(\'' + t + '\')">' + t + '</span>').join('')}
      </div>
      <label class="row tiny muted" style="cursor:pointer">
        <input type="checkbox" ${f.noAnn ? 'checked' : ''} onchange="AnnFilter('noAnn',this.checked)"> 只看未批注
      </label>
      <div class="spacer"></div>
      <span class="small muted">筛出 <strong>${mats.length}</strong> 条素材 · 其中 <strong>${withAnn.length}</strong> 条已批注</span>
      <a class="btn btn-sm" href="#/news?view=material">${Icon('bookmark')} 管理素材</a>
    </div>
  </div>
</div>

<div class="workbench">
  <div class="pane">
    <div class="pane-h">${Icon('folder')} 素材 ${mats.length} 条<div class="right">评分↓</div></div>
    <div class="pane-b">
      <div class="itemlist">
        ${mats.map(x => {
          const id = x.newsId, nn = App.newsById(id);
          const has = App.hasAnn(id);
          const v = App.verdictOf('a' + id);
          return `
          <div class="itemrow ${id === nid ? 'active' : ''}" data-act="pick" data-id="${id}">
            <div class="row between">
              <div class="t">${nn.title.slice(0, 20)}…</div>
              <span class="tag" style="background:var(--brand);color:#fff;border-color:var(--brand)">${x.m.score}</span>
            </div>
            <div class="m">${x.m.topics.map(t => '<span class="tag">' + t + '</span>').join(' ')}</div>
            <div class="m">${x.m.date} · ${has
              ? '<span class="tag ' + (v === 'passed' ? 'ok' : v === 'blocked' ? 'danger' : 'warn') + '">' + App.verdictLabel[v] + '</span>'
              : '<span class="tag">未批注</span>'}</div>
          </div>`;
        }).join('')}
      </div>
      <div class="sep"></div>
      <div class="small muted" style="padding:0 2px">★ 素材不要求有点评：没写点评的素材照样能进选题，AI 会按素材综述来写。</div>
    </div>
  </div>

  <div class="pane editor">
    <div class="editor-toolbar">
      <button class="iconbtn" title="加粗" onclick="document.execCommand('bold')"><b>B</b></button>
      <button class="iconbtn" title="列表" onclick="App.toast('富文本：列表')">≡</button>
      <button class="iconbtn" title="引用" onclick="App.toast('富文本：引用块')">${Icon('quote')}</button>
      <span class="vsep" style="height:16px;margin:0 4px"></span>
      <button class="btn btn-sm btn-ghost" data-act="ask">${Icon('bulb')} AI 提示问题</button>
      <button class="btn btn-sm btn-ghost" data-act="cite">${Icon('link')} 引用事实</button>
      <div class="spacer"></div>
      <span class="tiny faint" id="saveTip">自动保存 · 3s 防抖</span>
    </div>
    <div class="editor-area" id="editor" contenteditable="true" data-ph="写下你的判断。不是复述新闻，是「你怎么看」——一句也行。"></div>
    <div class="editor-foot">
      <span class="tiny">素材评分 <strong>${m ? m.score : '-'}</strong> · ${m ? m.topics.join('/') : '无主题'}</span>
      <div class="spacer"></div>
      <button class="btn btn-sm" data-act="prev">上一条</button>
      <button class="btn btn-sm" data-act="next">下一条</button>
      <button class="btn btn-primary" data-act="submit">${Icon('shield')} 提交检查 (${withAnn.length})</button>
    </div>
  </div>

  <div class="pane pane-r">
    <div class="pane-h">${Icon('news')} 素材原文<div class="right">常显，不用切页</div></div>
    <div class="pane-b" id="ctx"></div>
  </div>
</div>

<div class="card" style="margin-top:14px">
  <div class="card-h"><h3>这一页的产品判断</h3></div>
  <div class="card-b">
    <div class="grid g3">
      <div class="small muted"><strong>数据来自素材库</strong><br>工作台不做二次筛选资讯：你在资讯中心已经打过评分与主题，这里只按这三个维度取。</div>
      <div class="small muted"><strong>按天归档是默认节奏</strong><br>每天一个素材组，主理人早上挑、上午写，天然对齐日更节奏。</div>
      <div class="small muted"><strong>批注是可选的加深</strong><br>写了点评才有"观点驱动"的写作；没写也能写，只是产出偏综述。</div>
    </div>
  </div>
</div>`;
  },

  mount(root, { q }) {
    const st = App.state;
    const ed = root.querySelector('#editor');

    function paintCtx() {
      const nid = +st.curAnn.slice(1);
      const n = App.newsById(nid);
      const fc = DB.factCards[nid];
      root.querySelector('#ctx').innerHTML = `
        <div class="small"><strong>${n.source}</strong> · ${n.time}</div>
        <div style="font-size:13px;font-weight:600;margin:5px 0 6px;line-height:1.5">${n.title}</div>
        <div class="small muted" style="line-height:1.7">${n.summary}</div>
        ${n.symbols.length ? '<div class="row wrap" style="margin-top:8px">' + n.symbols.map(s => '<span class="tag brand">' + s + '</span>').join('') + '</div>' : ''}
        ${fc ? `<div class="sep"></div>
          <div class="tiny"><strong>FactCard · 可引用事实</strong></div>
          ${fc.facts.slice(0, 4).map(f => `
            <div class="row" style="align-items:flex-start;margin-top:6px">
              <span class="tag ${f.status === 'verified' ? 'ok' : f.status === 'contradicted' ? 'danger' : ''}">${
                { verified: '已验证', contradicted: '有冲突', unverifiable: '无法验证', outdated: '已过时' }[f.status]}</span>
              <div class="tiny" style="flex:1">${f.claim}</div>
            </div>`).join('')}
          <button class="btn btn-sm btn-block" style="margin-top:8px" onclick="App.go('facts',{id:${nid}})">${Icon('file')} 打开完整事实卡片</button>
        ` : '<div class="sep"></div><div class="note warn tiny">该素材暂无 FactCard。</div>'}
        <div class="sep"></div>
        <div class="tiny"><strong>AI 提示问题</strong> <span class="faint">（只提问，不给答案）</span></div>
        ${Ann.questions(n).map(x => '<div class="chip" style="margin-top:6px;display:flex;align-items:flex-start">' + Icon('bulb') + '<span>' + x + '</span></div>').join('')}
      `;
    }

    ed.innerHTML = App.esc(App.annOf(+st.curAnn.slice(1)).text);
    paintCtx();

    let timer = null;
    ed.addEventListener('input', () => {
      clearTimeout(timer);
      root.querySelector('#saveTip').textContent = '编辑中…';
      timer = setTimeout(() => {
        st.annTexts[st.curAnn] = ed.innerText; App.save();
        const d = new Date();
        root.querySelector('#saveTip').textContent =
          '已保存 · ' + String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      }, 900);
    });

    function switchTo(id) {
      st.annTexts[st.curAnn] = ed.innerText;
      st.curAnn = 'a' + id; App.save();
      const page = document.getElementById('page');
      page.innerHTML = window.Screens.annotate.render({ q: App.route.q });
      window.Screens.annotate.mount(page, { q: App.route.q });
    }

    root.addEventListener('click', (e) => {
      const el = e.target.closest('[data-act]');
      if (!el) return;
      const act = el.dataset.act;
      if (act === 'pick') { switchTo(+el.dataset.id); }
      else if (act === 'prev' || act === 'next') {
        const ids = App.matList(st.matFilter).map(x => x.newsId);
        const i = ids.indexOf(+st.curAnn.slice(1));
        const j = act === 'prev' ? Math.max(0, i - 1) : Math.min(ids.length - 1, i + 1);
        switchTo(ids[j]);
      }
      else if (act === 'ask') {
        const n = App.newsById(+st.curAnn.slice(1));
        App.modal({
          title: 'AI 提示问题',
          body: '<div class="small muted" style="margin-bottom:10px">只提问，不代写观点。</div>' +
            Ann.questions(n).map(x => '<div class="chip" style="margin-bottom:6px;display:flex;width:100%">' + Icon('bulb') + '<span>' + x + '</span></div>').join(''),
          footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">关闭</button>'
        });
      }
      else if (act === 'cite') {
        const nid = +st.curAnn.slice(1);
        const fc = DB.factCards[nid];
        if (!fc) { App.toast('该素材暂无 FactCard，可先让 ResearcherAgent 补查'); return; }
        App.modal({
          title: '引用事实',
          body: '<div class="small muted" style="margin-bottom:10px">一键插入，避免手抄错数字。</div>' +
            fc.facts.filter(f => f.status === 'verified').map((f, i) =>
              '<label class="row" style="align-items:flex-start;margin-bottom:9px">' +
                '<input type="radio" name="fc" value="' + i + '" style="margin-top:3px">' +
                '<span class="small">' + f.claim + '<div class="tiny faint">' + f.ev.map(x => x.src + ' · ' + x.date).join('；') + '</div></span>' +
              '</label>').join(''),
          footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">取消</button>' +
            '<button class="btn btn-primary" onclick="Ann.insert(this)">插入到点评</button>'
        });
      }
      else if (act === 'submit') {
        st.annTexts[st.curAnn] = ed.innerText; App.save();
        const ids = App.matList(st.matFilter).map(x => x.newsId).filter(i => App.hasAnn(i));
        if (!ids.length) { App.toast('当前筛选下还没有批注，先在资讯中心或这里写一条'); return; }
        Ann.runCheck(ids);
      }
    });
  }
};

/* ---------- 工具 ---------- */
window.Ann = {
  get(nid) { return App.annOf(nid); },
  questions(n) {
    const map = {
      1: ['这轮扩产里，真正有增量信息的是哪一项？',
          '如果 2027 年汽车电子需求不及预期，公司还有哪些缓冲？',
          '国产设备占比的口径，各家报道为什么不一致？'],
      2: ['直销占比上行，谁在让渡利润？',
          '渠道结构变化会怎样影响估值锚？',
          '12.4% 这个增速，放在过去五年是什么位置？'],
      3: ['文件里哪些是可被"卡住"的硬条件，哪些只是预期？',
          'PUE 门槛最先影响新建还是存量？',
          '补贴锚点从"用了多少"转向"用得多省"，谁会受损？'],
      4: ['锁量不锁价，风险到底落在哪一边？',
          '框架性协议与实际订单之间的落差通常有多大？',
          '这单对 2027 年的利润意味着什么？'],
      9: ['删除"通胀风险偏上行"这句话，分量有多重？',
          '市场定价与点阵图的分歧，历史上通常如何收敛？',
          '美元走弱对哪些新兴市场才是真利好？']
    };
    return map[n.id] || ['这条素材里，最有信息增量的是哪一点？',
      '如果反向成立，需要什么条件？',
      '你的判断与市场共识的分歧在哪？'];
  },
  insert(btn) {
    const mask = btn.closest('.mask');
    const r = mask.querySelector('input[name=fc]:checked');
    if (!r) { App.toast('先选一条'); return; }
    const nid = +App.state.curAnn.slice(1);
    const f = DB.factCards[nid].facts.filter(x => x.status === 'verified')[+r.value];
    const ed = document.getElementById('editor');
    ed.innerText = ed.innerText.replace(/\s+$/, '') + '（' + f.claim + '，' + f.ev[0].src + '）';
    App.state.annTexts[App.state.curAnn] = ed.innerText; App.save();
    App.closeModal(mask);
    App.toast('已插入引用 · 来源：' + f.ev[0].src);
  },
  runCheck(ids) {
    const mask = App.modal({
      title: '正在检查 · ' + ids.length + ' 条批注',
      body: `
        <div class="small muted" style="margin-bottom:12px">
          三轨并行（fact / logic / compliance），并发上限 5 条。
          FactCard 已在 ingest 阶段预生成，此处只读缓存 —— 这是「单条 &lt; 8s」的前提。
        </div>
        <div class="progress" id="pg"><i style="width:0%"></i></div>
        <div class="small muted" style="margin-top:10px" id="pgt">排队中…</div>
        <div class="sep"></div>
        <div id="pglog" class="tiny mono muted" style="line-height:1.9"></div>`,
      footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">后台继续</button>'
    });
    const bar = mask.querySelector('#pg > i');
    const txt = mask.querySelector('#pgt');
    const log = mask.querySelector('#pglog');
    let i = 0;
    const tick = setInterval(() => {
      if (i >= ids.length) {
        clearInterval(tick);
        txt.innerHTML = '<strong>检查完成</strong> · 生成 ' + ids.length + ' 份报告';
        setTimeout(() => { App.closeModal(mask); App.state.checked = true; App.save(); App.go('review'); }, 500);
        return;
      }
      i++;
      bar.style.width = (i / ids.length * 100) + '%';
      const v = App.verdictOf('a' + ids[i - 1]);
      txt.textContent = '已完成 ' + i + ' / ' + ids.length + ' 条';
      log.innerHTML += 'review.item_done · a' + ids[i - 1] + ' → ' + v + '<br>';
    }, 620);
  }
};

function AnnFilter(k, v) { App.state.matFilter[k] = v; App.save(); AnnRefresh(); }
function AnnTopic(t) {
  const f = App.state.matFilter, i = f.topics.indexOf(t);
  if (i >= 0) f.topics.splice(i, 1); else f.topics.push(t);
  App.save(); AnnRefresh();
}
function AnnRefresh() {
  const page = document.getElementById('page');
  page.innerHTML = window.Screens.annotate.render({ q: App.route.q });
  window.Screens.annotate.mount(page, { q: App.route.q });
}
