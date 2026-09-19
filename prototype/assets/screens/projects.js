window.Screens = window.Screens || {};

const STATUS = ['collecting', 'reviewing', 'ready', 'composing', 'drafting', 'completed', 'archived'];
const STATUS_CN = { collecting: '收集素材', reviewing: '检查中', ready: '就绪', composing: '写作中', drafting: '草稿', completed: '已完成', archived: '归档' };

window.Screens.projects = {
  title: '选题',
  step: '⑧',
  stepIdx: 7,

  render({ q }) {
    const st = App.state;

    if (q.new) {
      if (!st.draft) st.draft = {
        id: 'new', title: '', status: 'collecting', platform: '公众号', words: '2500-3000',
        newsIds: (st.projectDraft || []).slice(), promptIds: ['pt1', 'pt4'], require: '', updated: '刚刚'
      };
      st.projectDraft = null; App.save();
    }
    const p = q.new ? st.draft : App.projectById(st.projectId);

    const mats = p.newsIds.map(i => ({ id: i, n: App.newsById(i), m: App.mat(i) })).filter(x => x.n);
    const withAnn = mats.filter(x => App.hasAnn(x.id));
    const blocked = mats.filter(x => App.verdictOf('a' + x.id) === 'blocked');

    return `
<div class="grid" style="grid-template-columns:290px minmax(0,1fr);align-items:start">
  <div class="card">
    <div class="pane-h">${Icon('folder')} 我的选题
      <div class="right"><a class="btn btn-sm btn-ghost" href="#/projects?new=1">${Icon('plus')}</a></div>
    </div>
    <div class="card-b tight">
      ${DB.projects.map(x => {
        const b = x.newsIds.some(i => App.verdictOf('a' + i) === 'blocked');
        return `<div class="itemrow ${!q.new && x.id === st.projectId ? 'active' : ''}" onclick="Projects.open('${x.id}')">
          <div class="row between"><div class="t">${x.title}</div>
            <span class="tag ${b ? 'danger' : x.status === 'ready' ? 'ok' : x.status === 'completed' ? '' : 'brand'}">${
              b ? '有红线' : STATUS_CN[x.status]}</span></div>
          <div class="m">${x.newsIds.length} 条素材 · ${x.newsIds.filter(i => App.hasAnn(i)).length} 条带点评</div>
        </div>`;
      }).join('')}
      ${q.new ? '<div class="itemrow active"><div class="t">（新建选题）</div><div class="m">从素材库挑素材</div></div>' : ''}
    </div>
    <div class="card-b tight" style="border-top:1px solid var(--line-2)">
      <a class="btn btn-sm btn-block" href="#/projects?new=1">${Icon('plus')} 新建选题</a>
    </div>
  </div>

  <div>
    <div class="card">
      <div class="card-h">
        <h3>${q.new ? '新建选题' : p.title}</h3>
        <div class="sub">${p.platform} · ${p.words} 字</div>
      </div>
      <div class="card-b">
        ${q.new
          ? '<div class="field"><label class="lb">选题标题（可以先空着，AI 会给候选）</label>' +
            '<input class="inp" id="ptitle" placeholder="例：中芯扩产：一场被误读的抢跑" value="' + App.esc(p.title) + '" oninput="Projects.setTitle(this.value)"></div>'
          : '<div class="row"><h3 style="margin:0;font-size:15px">' + p.title + '</h3><div class="spacer"></div><span class="small muted">更新于 ' + p.updated + '</span></div>'}
        <div class="row" style="gap:0;margin-top:${q.new ? '4px' : '12px'}">
          ${STATUS.map((s, i) => {
            const ci = STATUS.indexOf(p.status);
            const on = i <= ci;
            return '<div style="flex:1;text-align:center">' +
              '<div style="height:3px;background:' + (on ? 'var(--brand)' : 'var(--line)') + ';border-radius:2px"></div>' +
              '<div class="tiny" style="margin-top:4px;color:' + (on ? 'var(--brand-ink)' : 'var(--faint)') + ';font-weight:' + (i === ci ? 600 : 400) + '">' + STATUS_CN[s] + '</div>' +
              '</div>';
          }).join('')}
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>素材 · ${mats.length} 条</h3>
        <div class="sub">选题的唯一原料；带点评 ${withAnn.length} 条</div>
        <div class="right">
          <button class="btn btn-sm btn-primary" onclick="Projects.picker()">${Icon('plus')} 从素材库添加</button>
        </div>
      </div>
      <div class="card-b tight">
        ${mats.length ? mats.map(x => {
          const v = App.hasAnn(x.id) ? App.verdictOf('a' + x.id) : null;
          return `<div class="row" style="align-items:flex-start;padding:9px 4px;border-bottom:1px solid var(--line-2)">
            <span class="tag" style="background:var(--brand);color:#fff;border-color:var(--brand)">${x.m ? x.m.score : '-'}</span>
            <div class="small" style="flex:1">
              <strong>${x.n.title.slice(0, 34)}…</strong>
              <div class="tiny faint">${x.n.source} · ${x.n.time}${x.m ? ' · ' + x.m.topics.join('/') : ''}</div>
              ${App.hasAnn(x.id)
                ? '<div class="tiny muted" style="margin-top:4px">' + App.esc(App.annTextOf(x.id)).slice(0, 60) + '…</div>'
                : '<div class="tiny faint" style="margin-top:4px">无点评 · 将作为背景素材参与写作</div>'}
            </div>
            ${v ? '<span class="tag ' + (v === 'passed' ? 'ok' : v === 'blocked' ? 'danger' : 'warn') + '">' + App.verdictLabel[v] + '</span>'
                : '<span class="tag">未批注</span>'}
            <button class="iconbtn" onclick="Projects.rm(${x.id})">${Icon('x')}</button>
          </div>`;
        }).join('') : '<div class="empty">还没有素材 —— 去素材库挑，或在资讯中心勾选后「用这些建选题」</div>'}
      </div>
      <div class="card-b" style="border-top:1px solid var(--line-2)">
        <div class="row wrap">
          <span class="tiny faint">快捷：</span>
          <span class="chip tiny" onclick="Projects.quick(8)">${Icon('spark')} 拉入评分 ≥8 的今日素材</span>
          <span class="chip tiny" onclick="Projects.quick(0)">拉入全部今日素材</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>写作配置</h3></div>
      <div class="card-b">
        <div class="grid g3">
          <div class="field"><label class="lb">目标平台</label>
            <select class="inp"><option>公众号</option><option>雪球</option><option>微博</option><option>小红书</option></select></div>
          <div class="field"><label class="lb">字数</label><input class="inp" value="${p.words}"></div>
          <div class="field"><label class="lb">读者对象</label><input class="inp" value="有持仓的散户与同行"></div>
        </div>
        <div class="field"><label class="lb">提示词组合（人格 + 结构 + 禁忌）</label>
          <div class="row wrap">
            ${DB.prompts.map(pt => `
              <span class="chip ${p.promptIds.includes(pt.id) ? 'on' : ''}" onclick="App.toast('${pt.name} · ${pt.version}')">
                ${Icon(pt.cat === '禁忌' ? 'ban' : pt.cat === '人格' ? 'user' : pt.cat === '结构' ? 'layers' : 'quote')}
                ${pt.name} <span class="tiny faint">${pt.version}</span></span>`).join('')}
          </div>
        </div>
        <div class="field"><label class="lb">写作要求</label>
          <textarea class="inp" rows="3">${App.esc(p.require || '')}</textarea></div>
      </div>
    </div>

    <div class="card">
      <div class="card-b">
        <div class="row between">
          <div style="flex:1">
            ${blocked.length
              ? '<div class="small"><strong>有 ' + blocked.length + ' 条素材的点评命中合规红线</strong>，需先处理才能写出安全的稿子</div>'
              : withAnn.length
                ? '<div class="small"><strong>可以开始写作</strong> · ' + withAnn.length + ' 条带点评（观点驱动） + ' + (mats.length - withAnn.length) + ' 条纯素材（背景事实）</div>'
                : '<div class="small"><strong>可以开始写作 · 素材综述模式</strong></div>' +
                  '<div class="tiny muted">这组素材还没有点评，AI 会按素材本身组织成文（偏综述，缺观点）。随时可以回素材补点评再重写。</div>'}
          </div>
          ${blocked.length
            ? '<button class="btn btn-lg" disabled>' + Icon('ban') + ' 先解决红线</button>'
            : (mats.length
              ? '<button class="btn btn-primary btn-lg" onclick="Projects.write()">' + Icon('wand') + ' 开始写作</button>'
              : '<button class="btn btn-lg" disabled>先挑素材</button>')}
        </div>
        ${!blocked.length && !withAnn.length && mats.length ? `
        <div class="note warn small" style="margin-top:10px">
          ★ 无点评也能写，但产出会偏"资讯综述"：有事实、有结构，缺你的判断。
          观点是这个产品的燃料 —— 建议至少给其中 1~2 条素材写一句判断。
        </div>` : ''}
      </div>
    </div>
  </div>
</div>`;
  }
};

window.Projects = {
  refresh() {
    const page = document.getElementById('page');
    page.innerHTML = window.Screens.projects.render({ q: App.route.q });
  },
  open(id) {
    App.state.projectId = id; App.state.draft = null; App.save();
    App.go('projects');
  },
  setTitle(v) { if (App.state.draft) { App.state.draft.title = v; App.save(); } },
  draft() { return App.route.q.new ? App.state.draft : App.projectById(App.state.projectId); },
  add(ids) {
    const p = Projects.draft();
    ids.forEach(i => { if (!p.newsIds.includes(i)) p.newsIds.push(i); });
    App.save(); Projects.refresh();
    App.toast('已加入 ' + ids.length + ' 条素材');
  },
  rm(id) {
    const p = Projects.draft();
    const i = p.newsIds.indexOf(id);
    if (i >= 0) p.newsIds.splice(i, 1);
    App.save(); Projects.refresh();
  },
  quick(min) {
    const ids = App.matList({ date: '2026-09-19', min }).map(x => x.newsId);
    Projects.add(ids);
  },
  picker() {
    const f = { date: '', min: 0, topics: [] };
    const mask = App.modal({
      title: '从素材库挑素材',
      body: `
        <div class="row wrap" style="gap:8px;margin-bottom:10px">
          <div class="fi">日期 <select id="pf_d" onchange="Projects.repick()">
            <option value="">全部</option><option value="2026-09-19">2026-09-19</option>
            <option value="2026-09-18">2026-09-18</option></select></div>
          <div class="fi">评分 <select id="pf_s" onchange="Projects.repick()">
            <option value="0">全部</option><option value="8">≥8</option><option value="6">≥6</option></select></div>
        </div>
        <div class="row wrap" style="margin-bottom:10px">
          ${App.topics().map(t => '<span class="chip tiny" onclick="this.classList.toggle(\'on\');Projects.repick()">' + t + '</span>').join('')}
        </div>
        <div id="plist"></div>`,
      footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">取消</button>' +
        '<button class="btn btn-primary" onclick="Projects.addPick(this)">' + Icon('check') + ' 加入选题</button>'
    });
    mask._m = mask;
    Projects.repick();
  },
  repick() {
    const mask = document.querySelector('.mask'); if (!mask) return;
    const d = mask.querySelector('#pf_d').value;
    const s = +mask.querySelector('#pf_s').value;
    const tp = Array.from(mask.querySelectorAll('.chip.on')).map(c => c.textContent.trim());
    const list = App.matList({ date: d, min: s, topics: tp });
    mask.querySelector('#plist').innerHTML = list.length
      ? list.map(x => {
          const n = App.newsById(x.newsId);
          return '<label class="row" style="align-items:flex-start;padding:7px 0;border-bottom:1px solid var(--line-2);cursor:pointer">' +
            '<input type="checkbox" class="pck" value="' + x.newsId + '" style="margin-top:3px">' +
            '<span class="small" style="flex:1"><strong>' + n.title.slice(0, 30) + '…</strong>' +
            '<div class="tiny faint">' + n.source + ' · 评分 ' + x.m.score + ' · ' + x.m.topics.join('/') +
            (App.hasAnn(x.newsId) ? ' · 已批注' : '') + '</div></span></label>';
        }).join('')
      : '<div class="empty">这个筛选下没有素材</div>';
  },
  addPick(btn) {
    const mask = btn.closest('.mask');
    const ids = Array.from(mask.querySelectorAll('.pck:checked')).map(c => +c.value);
    if (!ids.length) { App.toast('先勾选素材'); return; }
    App.closeModal(mask);
    Projects.add(ids);
  },
  write() {
    const p = Projects.draft();
    if (App.route.q.new) {
      if (!p.title.trim()) { App.toast('先给选题起个标题'); return; }
      p.id = 'p' + (DB.projects.length + 1);
      p.status = 'ready';
      p.updated = '刚刚';
      DB.projects.push(p);
      App.state.projectId = p.id;
      App.state.draft = null;
      App.save();
      App.toast('选题已创建');
    }
    App.state.composeStage = 'idle';
    App.save();
    App.go('compose');
  }
};
