window.Screens = window.Screens || {};

window.Screens.prompts = {
  title: '提示词管理',

  render() {
    const cats = ['风格', '结构', '人格', '禁忌'];
    const cur = DB.prompts[0];
    return `
<div class="note" style="margin-bottom:14px">
  用户的提示词不是一串字符，是一份<strong>可版本化、可复用、可加载进 Agent 的技能包</strong>（SKILL.md + 结构化约束）。
  写作时按栏目 / 平台<strong>按需加载</strong>，可多套叠加（人格 + 结构 + 禁忌）。
</div>

<div class="grid" style="grid-template-columns:280px minmax(0,1fr);align-items:start">
  <div class="card">
    <div class="pane-h">${Icon('quote')} 我的提示词
      <div class="right"><button class="btn btn-sm btn-ghost" onclick="App.toast('新建提示词')">${Icon('plus')}</button></div></div>
    <div class="card-b tight">
      ${cats.map(c => `
        <div class="tiny faint" style="padding:6px 2px">${c}</div>
        ${DB.prompts.filter(p => p.cat === c).map(p => `
          <div class="itemrow active" style="margin-bottom:5px">
            <div class="row between"><div class="t">${p.name}</div>
              <span class="tag">${p.version}</span></div>
            <div class="m">${p.official ? '官方模板' : '从我 5 篇旧作提取'} · 被 3 个选题使用</div>
          </div>`).join('')}`).join('')}
      <div class="sep"></div>
      <div class="tiny faint" style="padding:0 2px 6px">官方模板库</div>
      ${['雪球短评体', '公众号深度复盘体', '政策解读体', '晨会纪要体', '视频口播稿体'].map((n, i) =>
        '<div class="chip" style="margin:0 4px 4px 0" onclick="App.toast(\'已复制官方模板：' + n + '\')">' + n + '</div>').join('')}
    </div>
  </div>

  <div>
    <div class="card">
      <div class="card-h"><h3>${cur.name}</h3><div class="sub">${cur.cat} · ${cur.version}</div>
        <div class="right">
          <button class="btn btn-sm" onclick="App.toast('版本历史：v1 → v4，可回滚')">${Icon('clock')} 版本历史</button>
          <button class="btn btn-sm" onclick="App.toast('用一段示例资讯试写 200 字预览')">${Icon('spark')} 测试预览</button>
          <button class="btn btn-primary btn-sm" onclick="App.toast('已保存为 v5')">保存新版本</button>
        </div>
      </div>
      <div class="card-b">
        <div class="small muted" style="margin-bottom:8px">${cur.desc}</div>
        <textarea class="inp mono" rows="10" style="line-height:1.8">${App.esc(cur.body)}</textarea>
        <div class="row wrap" style="margin-top:8px">
          <span class="tiny faint">变量：</span>
          ${['{作者名}', '{字数}', '{读者对象}'].map(v =>
            '<span class="tag brand">' + v + '</span>').join('')}
          <span class="tiny faint">提交前校验，缺失变量高亮且不允许提交。</span>
        </div>
      </div>
    </div>

    <div class="grid g2">
      <div class="card">
        <div class="card-h"><h3>提示词 → Skill 包编译</h3></div>
        <div class="card-b">
          <div class="fs-tree">
            <span class="dir">skills/public-deep-review/</span><br>
            ├─ <span class="f">SKILL.md</span>　人格 + 结构 + 禁忌<br>
            ├─ <span class="f">constraints.json</span>　禁用词表 / 必含要素<br>
            └─ <span class="f">fewshot.md</span>　3 篇用户历史成稿
          </div>
          <div class="sep"></div>
          <div class="small muted">WriterAgent 写作前按需加载对应 Skill 包，而不是把全部提示词塞进一次上下文。</div>
        </div>
      </div>
      <div class="card">
        <div class="card-h"><h3>冷启动：没有历史文章怎么办</h3></div>
        <div class="card-b">
          <div class="small muted">
            <p style="margin:0 0 8px">两条路：① 从官方模板库选一套先用；② 粘贴 3~5 篇旧作 → 提取风格画像 → 生成初始提示词草稿。</p>
            <div class="row"><textarea class="inp" rows="2" placeholder="粘贴一篇旧作…"></textarea>
            <button class="btn">提取</button></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>`;
  }
};
