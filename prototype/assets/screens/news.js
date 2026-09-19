window.Screens = window.Screens || {};

const TODAY = '2026-09-19';

/* 素材面板的临时草稿（评分/主题选择），不落 state 直到保存 */
const MatDraft = { open: {}, annOpen: {} };

window.Screens.news = {
  title: '资讯中心',
  step: '②③④',
  stepIdx: 2,

  render({ q }) {
    const st = App.state;
    const view = q.view || st.newsView || 'all';
    st.newsView = view;
    const f = st.matFilter || (st.matFilter = { date: '', min: 0, topics: [], noAnn: false });

    let list;
    if (view === 'material') list = App.matList(f).map(x => App.newsById(x.newsId));
    else if (view === 'todo') list = App.matList({ noAnn: true }).map(x => App.newsById(x.newsId));
    else list = DB.news.filter(n => !st.hidden[n.id]);

    const matCount = Object.keys(st.materials).length;
    const todoCount = App.matList({ noAnn: true }).length;
    const todayCount = App.matList({ date: TODAY }).length;

    const card = (n) => {
      const id = n.id;
      const sel = st.sel.includes(id);
      const rating = st.starred[id] || 0;
      const saved = !!st.saved[id];
      const m = App.mat(id);
      const hasAnn = App.hasAnn(id);
      const annTxt = App.annTextOf(id);
      const d = MatDraft.open[id] || (m ? { score: m.score, topics: m.topics.slice(), date: m.date }
                                       : { score: 7, topics: [], date: TODAY });
      MatDraft.open[id] = d;

      return `
<div class="news ${sel ? 'sel' : ''} ${m ? 'is-mat' : ''}" data-id="${id}" style="margin-bottom:10px">
  <div class="imp ${n.imp === 'high' ? 'high' : n.imp === 'mid' ? 'mid' : 'low'}"></div>
  <div class="pick"><input type="checkbox" ${sel ? 'checked' : ''} data-act="pick" data-id="${id}"></div>
  <div class="body">
    <div class="meta">
      <span class="src">${n.source}</span><span>·</span><span>${n.time}</span>
      <span class="tag">${n.sourceType}</span>
      <span class="tag ${n.imp === 'high' ? 'danger' : n.imp === 'mid' ? 'warn' : ''}">${n.imp === 'high' ? '重要' : n.imp === 'mid' ? '一般' : '参考'}</span>
      ${n.symbols.map(s => '<span class="tag brand">' + s + '</span>').join('')}
      ${m ? '<span class="tag ok">' + Icon('bookmark') + ' 素材</span>' : ''}
      ${hasAnn ? '<span class="tag brand">' + Icon('pen') + ' 已批注</span>' : ''}
    </div>
    <h4><a href="javascript:;" data-act="open" data-id="${id}">${n.title}</a></h4>
    <div class="sum">${n.summary}</div>

    ${m ? `
    <div class="mat-badge">
      <span class="score" title="素材评分">${m.score}<small>/10</small></span>
      ${m.topics.map(t => '<span class="tag brand">' + t + '</span>').join('')}
      <span class="tag">${m.date}</span>
      <div class="spacer"></div>
      <button class="btn btn-sm btn-ghost" data-act="matEdit" data-id="${id}">${Icon('pen')} 改评分/主题</button>
      <button class="btn btn-sm btn-ghost" data-act="matDel" data-id="${id}">${Icon('x')} 移出素材</button>
    </div>` : ''}

    <div class="foot">
      ${n.tags.map(t => '<span class="tag">' + t + '</span>').join('')}
      <div class="acts">
        ${m ? '' : '<button class="btn btn-sm" data-act="matAdd" data-id="' + id + '">' + Icon('bookmark') + ' 加入素材</button>'}
        <button class="btn btn-sm ${hasAnn ? '' : 'btn-primary'}" data-act="annToggle" data-id="${id}">
          ${Icon('pen')} ${hasAnn ? '查看/改批注' : '批注'}</button>
        <div class="stars" data-act="rate" data-id="${id}">
          ${[1, 2, 3, 4, 5].map(i => '<span class="ico ' + (i <= rating ? 'on' : '') + '" data-v="' + i + '">' + Icon('star') + '</span>').join('')}
        </div>
        <button class="iconbtn ${saved ? 'saved' : ''}" data-act="save" data-id="${id}" title="收藏 (s)">${Icon('bookmark')}</button>
        <button class="iconbtn" data-act="hide" data-id="${id}" title="隐藏">${Icon('eyeOff')}</button>
      </div>
    </div>

    <div class="mat-panel ${MatDraft.open[id] && MatDraft.open[id].editing ? 'open' : ''}" id="mp${id}">
      <div class="small muted" style="margin-bottom:8px">
        <strong>标记为素材</strong> · 默认归入「${TODAY}」这一天，可改。素材是后面点评与选题的唯一原料。
      </div>
      <div class="field">
        <label class="lb">评分（1~10，越高越想写）</label>
        <div class="row wrap" id="sc${id}">
          ${[1,2,3,4,5,6,7,8,9,10].map(v =>
            '<span class="chip sc' + (d.score === v ? ' on' : '') + '" data-act="score" data-id="' + id + '" data-v="' + v + '">' + v + '</span>').join('')}
        </div>
      </div>
      <div class="field">
        <label class="lb">主题（可多选，类似标签）</label>
        <div class="row wrap">
          ${App.topics().map(t =>
            '<span class="chip' + (d.topics.includes(t) ? ' on' : '') + '" data-act="topic" data-id="' + id + '" data-t="' + t + '">' + t + '</span>').join('')}
        </div>
        <div class="row" style="margin-top:6px">
          <input class="inp" id="nt${id}" placeholder="新建主题…" style="max-width:180px">
          <button class="btn btn-sm" data-act="newTopic" data-id="${id}">${Icon('plus')} 新建</button>
        </div>
      </div>
      <div class="field">
        <label class="lb">归入日期</label>
        <input class="inp" type="date" id="md${id}" value="${d.date}" style="max-width:180px">
      </div>
      <div class="row">
        <button class="btn btn-sm" data-act="matCancel" data-id="${id}">取消</button>
        <button class="btn btn-primary btn-sm" data-act="matSave" data-id="${id}">${Icon('check')} 保存素材</button>
        <span class="tiny faint">保存后可直接在这一页批注，无需跳页</span>
      </div>
    </div>

    <div class="ann-panel ${MatDraft.annOpen[id] ? 'open' : ''}" id="ap${id}">
      <div class="row" style="margin-bottom:6px">
        <span class="tiny muted">批注 · 不是复述新闻，是「你怎么看」</span>
        <div class="spacer"></div>
        <button class="btn btn-sm btn-ghost" data-act="ask" data-id="${id}">${Icon('bulb')} AI 提示问题</button>
        <span class="tiny faint" id="as${id}"></span>
      </div>
      <textarea class="inp" rows="3" id="at${id}" placeholder="写下你的判断…（自动保存）">${App.esc(annTxt)}</textarea>
      <div class="row" style="margin-top:6px">
        <span class="tiny faint">${hasAnn ? '已有批注 · 可在工作台做深度点评并提交检查' : '保存后进入素材库，可在工作台筛选与检查'}</span>
        <div class="spacer"></div>
        <button class="btn btn-sm" data-act="annClose" data-id="${id}">收起</button>
        <a class="btn btn-sm" href="#/annotate?m=${id}">${Icon('pen')} 去工作台深化</a>
      </div>
      <div id="aq${id}"></div>
    </div>
  </div>
</div>`;
    };

    return `
<div class="grid" style="grid-template-columns:minmax(0,1fr) 250px;align-items:start">
  <div>
    <div class="row" style="margin-bottom:12px">
      <div class="row" style="border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--panel)">
        <a class="btn btn-sm" style="border:0;border-radius:0;${view === 'all' ? 'background:var(--brand-soft);color:var(--brand-ink)' : ''}" href="#/news?view=all">全部资讯</a>
        <a class="btn btn-sm btn-ghost" style="border:0;border-radius:0;${view === 'material' ? 'background:var(--brand-soft);color:var(--brand-ink)' : ''}" href="#/news?view=material">我的素材 <span class="tag" style="margin-left:4px">${matCount}</span></a>
        <a class="btn btn-sm btn-ghost" style="border:0;border-radius:0;${view === 'todo' ? 'background:var(--brand-soft);color:var(--brand-ink)' : ''}" href="#/news?view=todo">待批注 <span class="tag" style="margin-left:4px">${todoCount}</span></a>
      </div>
      <div class="spacer"></div>
      <span class="small muted">${list.length} 条</span>
    </div>

    <div class="filters">
      <div class="fi">${Icon('clock')}<select><option>今日</option><option>近 3 天</option><option>本周</option></select></div>
      <div class="fi">类型 <select><option>全部</option><option>快讯</option><option>公告</option><option>政策</option><option>研报</option></select></div>
      <div class="fi">市场 <select><option>全部</option><option>A股</option><option>港股</option><option>美股</option><option>宏观</option></select></div>
      <div class="fi">行业 <select><option>全部</option><option>半导体</option><option>食品饮料</option><option>电力设备</option><option>计算机</option></select></div>
      <div class="fi">来源 <select><option>全部</option><option>财联社</option><option>交易所公告</option><option>券商研报</option></select></div>
      <div class="fi"><input placeholder="关键词 / 标的…" style="width:120px"></div>
      <div class="spacer"></div>
      <button class="btn btn-sm" onclick="App.toast('已保存为「每日盘前筛选」')">${Icon('bookmark')} 存为常用筛选</button>
    </div>

    ${view !== 'all' ? `
    <div class="filters" style="background:var(--brand-soft);border-color:#dfe4ff">
      <span class="small"><strong>素材筛选</strong></span>
      <div class="fi">日期
        <select onchange="News.setF('date',this.value)">
          <option value="">全部日期</option>
          <option value="${TODAY}" ${f.date === TODAY ? 'selected' : ''}>${TODAY}（今天）</option>
          <option value="2026-09-18" ${f.date === '2026-09-18' ? 'selected' : ''}>2026-09-18</option>
        </select>
      </div>
      <div class="fi">评分
        <select onchange="News.setF('min',+this.value)">
          <option value="0" ${!f.min ? 'selected' : ''}>全部</option>
          <option value="8" ${f.min === 8 ? 'selected' : ''}>≥ 8（最想写）</option>
          <option value="6" ${f.min === 6 ? 'selected' : ''}>≥ 6</option>
          <option value="4" ${f.min === 4 ? 'selected' : ''}>≥ 4</option>
        </select>
      </div>
      <div class="row wrap">
        ${App.topics().slice(0, 8).map(t =>
          '<span class="chip' + (f.topics.includes(t) ? ' on' : '') + '" onclick="News.toggleTopic(\'' + t + '\')">' + t + '</span>').join('')}
      </div>
      ${(f.date || f.min || f.topics.length) ? '<button class="btn btn-sm btn-ghost" onclick="News.clearF()">清空筛选</button>' : ''}
    </div>` : ''}

    <div id="list">${list.map(card).join('') || '<div class="empty">这个筛选下还没有素材</div>'}</div>
  </div>

  <div class="col">
    <div class="card">
      <div class="card-h"><h3>今日素材</h3><div class="sub">${TODAY}</div></div>
      <div class="card-b">
        <div class="row between"><span class="small muted">条数</span><strong>${todayCount}</strong></div>
        <div class="row between"><span class="small muted">已批注</span><strong>${App.matList({ date: TODAY }).filter(x => App.hasAnn(x.newsId)).length}</strong></div>
        <div class="row between"><span class="small muted">平均评分</span><strong>${(App.matList({ date: TODAY }).reduce((s, x) => s + x.m.score, 0) / (todayCount || 1)).toFixed(1)}</strong></div>
        <div class="sep"></div>
        <div class="tiny faint" style="margin-bottom:6px">按评分</div>
        ${[['≥ 8', 8], ['6~7', 6], ['≤ 5', 1]].map(([lb, mn]) => {
          const c = App.matList({ date: TODAY, min: mn, max: mn === 6 ? 7 : mn === 1 ? 5 : 10 }).length;
          return '<div class="row" style="margin-bottom:5px"><span class="tiny" style="width:40px">' + lb + '</span>' +
            '<div class="progress" style="flex:1"><i style="width:' + (todayCount ? c / todayCount * 100 : 0) + '%"></i></div>' +
            '<span class="tiny mono muted" style="width:20px;text-align:right">' + c + '</span></div>';
        }).join('')}
        <div class="sep"></div>
        <div class="tiny faint" style="margin-bottom:6px">按主题</div>
        <div class="row wrap">
          ${Object.keys(App.matList({ date: TODAY }).reduce((o, x) => {
              x.m.topics.forEach(t => o[t] = (o[t] || 0) + 1); return o; }, {}))
            .map(t => '<span class="chip tiny" onclick="News.pickTopic(\'' + t + '\')">' + t + '</span>').join('')}
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>快捷键</h3></div>
      <div class="card-b small">
        <div class="row between"><span class="muted">上下移动</span><span><span class="kbd">j</span> <span class="kbd">k</span></span></div>
        <div class="row between"><span class="muted">加入素材</span><span><span class="kbd">m</span></span></div>
        <div class="row between"><span class="muted">批注</span><span><span class="kbd">a</span></span></div>
        <div class="row between"><span class="muted">选中 / 收藏</span><span><span class="kbd">space</span> / <span class="kbd">s</span></span></div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>这一页的产品判断</h3></div>
      <div class="card-b small muted">
        <p style="margin:0 0 8px"><strong>筛选与批注都在这一页完成</strong>：不跳页是硬要求——主理人的工作流是"边刷边记"，一次跳转就丢一次想法。</p>
        <p style="margin:0 0 8px"><strong>素材 = 打过标的资讯</strong>：评分（想写的程度）+ 主题（多维标签）+ 日期（默认当天，天然按天归档）。</p>
        <p style="margin:0"><strong>素材不要求有点评</strong>：标一组素材、定好选题就能直接交给 AI 写。</p>
      </div>
    </div>
  </div>
</div>

${App.state.sel.length ? `
<div class="dock">
  <div class="t">已选 <b>${App.state.sel.length}</b> 条</div>
  <button class="btn btn-ghost btn-sm" data-act="clear">清空</button>
  <button class="btn btn-ghost btn-sm" data-act="annAll">${Icon('pen')} 批量批注</button>
  <button class="btn btn-ghost btn-sm" data-act="matAll">${Icon('bookmark')} 加入素材</button>
  <button class="btn btn-primary" data-act="toProject">${Icon('folder')} 用这些建选题</button>
</div>` : ''}`;
  },

  mount(root) {
    const st = App.state;

    /* 批注自动保存 */
    let t = null;
    root.addEventListener('input', (e) => {
      const ta = e.target.closest('textarea[id^=at]');
      if (!ta) return;
      const id = ta.id.slice(2);
      clearTimeout(t);
      t = setTimeout(() => {
        st.annTexts['a' + id] = ta.value;
        App.save();
        const tip = root.querySelector('#as' + id);
        if (tip) tip.textContent = '已保存 · ' + new Date().toTimeString().slice(0, 5);
      }, 800);
    });

    root.addEventListener('click', (e) => {
      const el = e.target.closest('[data-act]');
      if (!el) return;
      const act = el.dataset.act;
      const id = +el.dataset.id;

      if (act === 'pick') {
        const i = st.sel.indexOf(id);
        if (i >= 0) st.sel.splice(i, 1); else st.sel.push(id);
        App.save(); News.rerender();
      } else if (act === 'open') {
        Detail.open(id);
      } else if (act === 'rate') {
        const ico = e.target.closest('.ico'); if (!ico) return;
        const v = +ico.dataset.v;
        st.starred[id] = (st.starred[id] === v) ? 0 : v;
        App.save(); App.toast('已评级 ' + v + ' ★'); News.rerender();
      } else if (act === 'save') {
        st.saved[id] = !st.saved[id]; App.save();
        App.toast(st.saved[id] ? '已收藏' : '已取消收藏'); News.rerender();
      } else if (act === 'hide') {
        st.hidden[id] = true; App.save(); App.toast('已隐藏'); News.rerender();
      }

      /* ---- 素材 ---- */
      else if (act === 'matAdd' || act === 'matEdit') {
        const cur = App.mat(id);
        MatDraft.open[id] = cur
          ? { score: cur.score, topics: cur.topics.slice(), date: cur.date, editing: true }
          : { score: 7, topics: [], date: TODAY, editing: true };
        News.rerender();
      } else if (act === 'matCancel') {
        delete MatDraft.open[id].editing; News.rerender();
      } else if (act === 'score') {
        MatDraft.open[id].score = +el.dataset.v; News.rerenderPanel(id);
      } else if (act === 'topic') {
        const tp = el.dataset.t, d = MatDraft.open[id], i = d.topics.indexOf(tp);
        if (i >= 0) d.topics.splice(i, 1); else d.topics.push(tp);
        News.rerenderPanel(id);
      } else if (act === 'newTopic') {
        const inp = root.querySelector('#nt' + id);
        const v = (inp.value || '').trim();
        if (!v) return;
        if (!App.topics().includes(v)) { st.customTopics.push(v); App.save(); }
        if (!MatDraft.open[id].topics.includes(v)) MatDraft.open[id].topics.push(v);
        News.rerender();
      } else if (act === 'matSave') {
        const d = MatDraft.open[id];
        const date = (root.querySelector('#md' + id).value || TODAY);
        App.setMat(id, { score: d.score, topics: d.topics.slice(), date });
        App.toast('已加入素材 · 评分 ' + d.score + ' · ' + (d.topics.join('/') || '无主题'));
        News.rerender();
      } else if (act === 'matDel') {
        App.delMat(id); App.toast('已移出素材库'); News.rerender();
      }

      /* ---- 批注 ---- */
      else if (act === 'annToggle') {
        MatDraft.annOpen[id] = !MatDraft.annOpen[id]; News.rerender();
      } else if (act === 'annClose') {
        MatDraft.annOpen[id] = false;
        const ta = root.querySelector('#at' + id);
        if (ta) { st.annTexts['a' + id] = ta.value; App.save(); }
        News.rerender();
      } else if (act === 'ask') {
        const n = App.newsById(id);
        root.querySelector('#aq' + id).innerHTML =
          '<div class="note small" style="margin-top:8px">AI 只提问，不代写观点：<br>' +
          Ann.questions(n).map(x => '· ' + x).join('<br>') + '</div>';
      }

      /* ---- 批量 ---- */
      else if (act === 'clear') { st.sel = []; App.save(); News.rerender(); }
      else if (act === 'annAll') {
        st.sel.forEach(i => MatDraft.annOpen[i] = true);
        News.rerender(); App.toast('已展开 ' + st.sel.length + ' 条批注框，逐条填写即可（自动保存）');
      }
      else if (act === 'matAll') { News.batchMat(st.sel.slice()); }
      else if (act === 'toProject') {
        News.batchMat(st.sel.slice(), true);
      }
    });
  }
};

window.News = {
  rerender() {
    const page = document.getElementById('page');
    page.innerHTML = window.Screens.news.render({ q: App.route.q, App });
    window.Screens.news.mount(page);
  },
  /* 只重画单个素材面板，避免整页重绘丢失输入 */
  rerenderPanel(id) {
    const d = MatDraft.open[id];
    const box = document.querySelector('#mp' + id);
    if (!box) return;
    box.querySelectorAll('[data-act=score]').forEach(c => {
      c.classList.toggle('on', +c.dataset.v === d.score);
    });
    box.querySelectorAll('[data-act=topic]').forEach(c => {
      c.classList.toggle('on', d.topics.includes(c.dataset.t));
    });
  },
  setF(k, v) { App.state.matFilter[k] = v; App.save(); News.rerender(); },
  clearF() {
    App.state.matFilter = { date: '', min: 0, topics: [], noAnn: false };
    App.save(); News.rerender();
  },
  toggleTopic(t) {
    const f = App.state.matFilter, i = f.topics.indexOf(t);
    if (i >= 0) f.topics.splice(i, 1); else f.topics.push(t);
    App.save(); News.rerender();
  },
  pickTopic(t) {
    App.state.newsView = 'material';
    App.state.matFilter = { date: TODAY, min: 0, topics: [t], noAnn: false };
    App.save(); App.go('news', { view: 'material' });
  },
  /* 批量标记素材 */
  batchMat(ids, thenProject) {
    const draft = { score: 7, topics: [], date: TODAY };
    const mask = App.modal({
      title: '把 ' + ids.length + ' 条加入素材',
      body: `
        <div class="small muted" style="margin-bottom:10px">统一设定评分与主题；归入日期默认「${TODAY}」，也就是<strong>每天一个素材组</strong>。</div>
        <div class="field"><label class="lb">评分（1~10）</label>
          <div class="row wrap" id="bsc">
            ${[1,2,3,4,5,6,7,8,9,10].map(v => '<span class="chip sc' + (v === 7 ? ' on' : '') + '" onclick="News.bpick(this,' + v + ')">' + v + '</span>').join('')}
          </div></div>
        <div class="field"><label class="lb">主题（可多选）</label>
          <div class="row wrap" id="btp">
            ${App.topics().map(t => '<span class="chip" onclick="News.btopic(this,\'' + t + '\')">' + t + '</span>').join('')}
          </div></div>
        <div class="field"><label class="lb">归入日期</label>
          <input class="inp" type="date" id="bdt" value="${TODAY}" style="max-width:180px"></div>
        <div class="small muted">${ids.map(i => '· ' + App.newsById(i).title.slice(0, 24) + '…').join('<br>')}</div>`,
      footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">取消</button>' +
        '<button class="btn btn-primary" onclick="News.batchSave([' + ids + '],' + (thenProject ? 'true' : 'false') + ',this)">' +
        Icon('check') + ' 保存</button>'
    });
    mask._draft = draft;
  },
  bpick(el, v) {
    el.closest('#bsc').querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c === el));
  },
  btopic(el, t) { el.classList.toggle('on'); },
  batchSave(ids, thenProject, btn) {
    const mask = btn.closest('.mask');
    const score = +(mask.querySelector('#bsc .chip.on') || {}).textContent || 7;
    const topics = Array.from(mask.querySelectorAll('#btp .chip.on')).map(c => c.textContent);
    const date = mask.querySelector('#bdt').value || TODAY;
    ids.forEach(i => App.setMat(i, { score, topics: topics.slice(), date }));
    App.closeModal(mask);
    App.toast(ids.length + ' 条已加入素材 · 评分 ' + score + ' · ' + (topics.join('/') || '无主题'));
    if (thenProject) {
      App.state.projectDraft = ids;
      App.save();
      setTimeout(() => App.go('projects', { new: 1 }), 300);
    } else News.rerender();
  }
};
