/* ============================================================
   原型外壳：路由 / 导航 / 全局状态 / 通用交互
   ============================================================ */

(function () {
  const S = window.Screens || (window.Screens = {});

  /* ---------- 全局状态（可跨页保留，模拟一次真实会话） ---------- */
  const KEY = 'nda-proto-state';
  const defaults = {
    sel: [1, 3, 4],              // 资讯流已勾选
    materials: JSON.parse(JSON.stringify(DB.materials)), // 素材库：{ newsId: {date, score, topics} }
    customTopics: [],            // 用户自建主题
    annTexts: {},                // 点评正文（覆盖 mock），键为 'a' + newsId
    fstates: {},                 // finding 处置状态
    reasons: {},                 // 驳回理由
    curAnn: 'a1',
    newsView: 'all',             // all | material | todo
    matFilter: { date: '', min: 0, topics: [], noAnn: false },
    checked: false,              // 是否已跑过检查
    projectId: 'p1',
    outline: null,
    composeStage: 'idle',        // idle | outline | writing | done
    starred: { 1: 0, 2: 4, 3: 0, 9: 5 },
    saved: { 2: true, 9: true },
    hidden: {}
  };

  const App = window.App = {
    state: Object.assign({}, defaults, load()),
    route: { name: 'overview', q: {} },

    save() { try { localStorage.setItem(KEY, JSON.stringify(App.state)); } catch (e) {} },
    reset() { App.state = Object.assign({}, defaults); App.save(); App.go('overview'); },

    go(name, q) {
      let h = '#/' + name;
      if (q) {
        const p = Object.keys(q).map(k => k + '=' + encodeURIComponent(q[k])).join('&');
        if (p) h += '?' + p;
      }
      if (location.hash === h) { render(); } else { location.hash = h; }
    },

    /* ---------- 工具 ---------- */
    esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
      ));
    },
    /* 高亮片段：把 quote 包成 span（用于体检报告的划词定位） */
    mark(text, quote, sev) {
      if (!quote) return App.esc(text);
      const i = text.indexOf(quote);
      if (i < 0) return App.esc(text);
      return App.esc(text.slice(0, i))
        + '<span class="hl ' + sev + '">' + App.esc(quote) + '</span>'
        + App.esc(text.slice(i + quote.length));
    },
    toast(msg, ms) {
      const old = document.querySelector('.toast'); if (old) old.remove();
      const el = document.createElement('div');
      el.className = 'toast'; el.innerHTML = msg;
      document.body.appendChild(el);
      setTimeout(() => el.remove(), ms || 1900);
    },
    modal(opt) {
      const mask = document.createElement('div');
      mask.className = 'mask';
      mask.innerHTML =
        '<div class="modal">' +
          '<div class="modal-h"><h3>' + opt.title + '</h3>' +
            '<div class="spacer"></div>' +
            '<button class="iconbtn" data-close>' + Icon('x') + '</button>' +
          '</div>' +
          '<div class="modal-b">' + opt.body + '</div>' +
          (opt.footer ? '<div class="modal-f">' + opt.footer + '</div>' : '') +
        '</div>';
      mask.addEventListener('click', e => {
        if (e.target === mask || e.target.closest('[data-close]')) mask.remove();
      });
      document.body.appendChild(mask);
      return mask;
    },
    closeModal(el) { if (el) el.remove(); else { const m = document.querySelector('.mask'); if (m) m.remove(); } },
    drawer(html) {
      const mask = document.createElement('div');
      mask.className = 'drawer-mask';
      mask.innerHTML = '<div class="drawer">' + html + '</div>';
      mask.addEventListener('click', e => { if (e.target === mask) mask.remove(); });
      document.body.appendChild(mask);
      return mask;
    },
    /* ---------- 素材库 ---------- */
    annKey(nid) { return 'a' + nid; },
    mat(nid) { return App.state.materials[nid]; },
    isMat(nid) { return !!App.state.materials[nid]; },
    setMat(nid, m) { App.state.materials[nid] = m; App.save(); },
    delMat(nid) { delete App.state.materials[nid]; App.save(); },
    topics() { return DB.topics.concat(App.state.customTopics || []); },
    /* 素材列表：按日期降序 → 评分降序 */
    matList(filter) {
      const f = filter || {};
      return Object.keys(App.state.materials).map(k => ({ newsId: +k, m: App.state.materials[k] }))
        .filter(x => (!f.date || x.m.date === f.date))
        .filter(x => (!f.min || x.m.score >= f.min))
        .filter(x => (!f.max || x.m.score <= f.max))
        .filter(x => (!f.topics || !f.topics.length || f.topics.some(t => x.m.topics.includes(t))))
        .filter(x => (!f.noAnn || !App.hasAnn(x.newsId)))
        .sort((a, b) => (a.m.date < b.m.date ? 1 : a.m.date > b.m.date ? -1 : b.m.score - a.m.score));
    },
    hasAnn(nid) {
      const t = App.state.annTexts['a' + nid];
      if (t != null && String(t).trim()) return true;
      const a = App.annOf(nid);
      return !!(a && a.text);
    },
    /* 素材的点评对象（可能不存在） */
    annOf(nid) {
      const id = 'a' + nid;
      const base = DB.annotations.find(a => a.id === id) || { id, newsId: +nid, text: '', status: 'draft' };
      const t = App.state.annTexts[id];
      return t != null ? Object.assign({}, base, { text: t, status: 'checked' }) : base;
    },

    newsById(id) { return DB.news.find(n => n.id === +id); },
    annById(id) { return DB.annotations.find(a => a.id === id); },
    annText(a) { return App.state.annTexts[a.id] != null ? App.state.annTexts[a.id] : a.text; },
    annTextOf(nid) { return App.annOf(nid).text; },
    projectById(id) { return DB.projects.find(p => p.id === id); },
    verdictOf(aid) {
      const fs = DB.findings[aid] || [];
      let v = 'passed';
      fs.forEach(f => {
        if (App.state.fstates[f.id]) return;
        if (f.severity === 'blocker') v = 'blocked';
        else if ((f.severity === 'high' || f.severity === 'medium') && v !== 'blocked') v = 'needs_revision';
      });
      return v;
    },
    verdictLabel: { passed: '通过', needs_revision: '需修改', blocked: '有红线' },
    trackLabel: { fact: '事实', logic: '逻辑', compliance: '合规', tone: '语气' },
    sevLabel: { blocker: '红线', high: '严重', medium: '中等', low: '轻微', info: '提示' }
  };

  function load() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } }

  /* ---------- 导航配置 ---------- */
  const NAV = [
    { label: '原型总览', items: [{ k: 'overview', n: '原型地图 · 流程', i: 'layers' }] },
    { label: '第一层 · 资讯台', lv: 'L1', items: [
      { k: 'inbox', n: '今日收件箱', i: 'inbox', c: 37 },
      { k: 'news', n: '资讯中心', i: 'news', q: 'all' },
      { k: 'news', n: '素材库', i: 'bookmark', q: 'material' },
      { k: 'interests', n: '兴趣画像', i: 'spark' },
      { k: 'connectors', n: '数据源管理', i: 'db' }
    ] },
    { label: '第二层 · 观点室', lv: 'L2', items: [
      { k: 'annotate', n: '点评工作台', i: 'pen' },
      { k: 'review', n: 'AI 体检报告', i: 'shield', c: 2 },
      { k: 'facts', n: '事实卡片', i: 'file' }
    ] },
    { label: '第三层 · 写作台', lv: 'L3', items: [
      { k: 'projects', n: '选题', i: 'folder', c: 3 },
      { k: 'compose', n: 'AI 写作', i: 'wand' },
      { k: 'article', n: '稿件', i: 'file' },
      { k: 'prompts', n: '提示词管理', i: 'quote' }
    ] },
    { label: '其他', items: [
      { k: 'onboarding', n: '首次使用引导', i: 'user' },
      { k: 'usage', n: '用量与配额', i: 'chart' }
    ] }
  ];

  /* ---------- 主流程 11 步 ---------- */
  const STEPS = [
    ['①', '后台同步', 'connectors'],
    ['②', '浏览资讯', 'inbox'],
    ['③', '标记素材', 'news'],
    ['④', '就地批注', 'news'],
    ['⑤', '深化点评', 'annotate'],
    ['⑥', '提交检查', 'annotate'],
    ['⑦', '体检报告', 'review'],
    ['⑧', '创建选题', 'projects'],
    ['⑨', 'AI 写作', 'compose'],
    ['⑩', '编辑定稿', 'article'],
    ['⑪', '沉淀归档', 'usage']
  ];

  /* ---------- 渲染 ---------- */
  function navHtml(active) {
    const view = App.route.q.view || '';
    return NAV.map(g =>
      '<div class="nav-group">' +
        '<div class="nav-group-label">' + (g.lv ? '<span class="lv">' + g.lv + '</span>' : '') + g.label + '</div>' +
        g.items.map(it => {
          const on = it.k === active && (it.q ? view === it.q : view !== 'material');
          const cnt = it.k === 'news' && it.q === 'material'
            ? Object.keys(App.state.materials).length
            : (it.k === 'annotate' ? App.matList({}).filter(x => App.hasAnn(x.newsId)).length : it.c);
          return '<a class="nav-item' + (on ? ' active' : '') + '" href="#/' + it.k +
            (it.q ? '?view=' + it.q : '') + '">' +
            Icon(it.i) + '<span>' + it.n + '</span>' +
            (cnt ? '<span class="count">' + cnt + '</span>' : '') +
          '</a>';
        }).join('') +
      '</div>'
    ).join('');
  }

  function stepsHtml(active, step) {
    const ci = STEPS.findIndex(s => s[2] === active);
    const cur = step != null ? step : (ci >= 0 ? ci : -1);
    return STEPS.map((s, i) =>
      '<a class="s' + (i === cur ? ' cur' : (cur > i ? ' done' : '')) + '" href="#/' + s[2] + '">' +
        '<span class="n">' + s[0] + '</span>' + s[1] +
      '</a>' + (i < STEPS.length - 1 ? '<span class="sep">›</span>' : '')
    ).join('');
  }

  function render() {
    const hash = location.hash.replace(/^#\/?/, '') || 'overview';
    const [name, qs] = hash.split('?');
    const q = {};
    (qs || '').split('&').filter(Boolean).forEach(p => {
      const [k, v] = p.split('='); q[k] = decodeURIComponent(v || '');
    });
    App.route = { name, q };

    const sc = S[name] || S.overview;

    document.getElementById('root').innerHTML =
      '<div class="shell">' +
        '<aside class="nav">' +
          '<div class="nav-brand">' +
            '<div class="nav-logo">主</div>' +
            '<div><div class="nav-title">主理人 Agent</div><div class="nav-sub">交互原型 v0.1</div></div>' +
          '</div>' +
          navHtml(name) +
          '<div class="nav-foot">' +
            '<div class="nav-user"><div class="nav-avatar">张</div>' +
              '<div><div class="n">' + DB.profile.name + '</div><div class="p">专业版 · 剩余 128 次检查</div></div></div>' +
            '<div class="row" style="margin-top:10px">' +
              '<a class="btn btn-sm btn-ghost" style="color:#8b98ad" href="#/overview">原型说明</a>' +
              '<button class="btn btn-sm btn-ghost" style="color:#8b98ad" id="resetBtn">重置</button>' +
            '</div>' +
          '</div>' +
        '</aside>' +
        '<div class="main">' +
          '<div class="topbar">' +
            '<h1>' + sc.title + (sc.step ? '<span class="stepno">主流程 ' + sc.step + '</span>' : '') + '</h1>' +
            '<div class="search">' + Icon('search') + '<input placeholder="搜索资讯 / 点评 / 选题…" /></div>' +
            '<div class="sync-pill"><i class="dot pulse"></i>刚刚更新 · 新增 128 条</div>' +
            '<button class="iconbtn" title="同步" onclick="App.toast(\'已在 09:40 完成同步，下次 10:10\')">' + Icon('refresh') + '</button>' +
          '</div>' +
          '<div class="steps">' + stepsHtml(name, sc.stepIdx) + '</div>' +
          '<div class="content"><div class="page" id="page"></div></div>' +
        '</div>' +
      '</div>';

    document.getElementById('resetBtn').onclick = () => { App.reset(); App.toast('原型状态已重置'); };

    const page = document.getElementById('page');
    page.innerHTML = sc.render({ q, App }) || '';
    if (sc.mount) sc.mount(page, { q, App });
    window.scrollTo(0, 0);
    document.querySelector('.content').scrollTop = 0;
  }

  window.addEventListener('hashchange', render);
  window.addEventListener('DOMContentLoaded', render);
  if (document.readyState !== 'loading') render();
})();
