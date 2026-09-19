window.Screens = window.Screens || {};

window.Screens.article = {
  title: '稿件',
  step: '⑩⑪',
  stepIdx: 9,

  render() {
    const A = DB.article;
    return `
<div class="row between" style="margin-bottom:12px">
  <div class="row">
    <span class="tag ok">${Icon('check')} 已定稿</span>
    <span class="tag">${A.platform}</span>
    <span class="tag">${A.words} 字</span>
    <span class="tag">成本 ¥${A.cost}</span>
    <span class="tag">用时 ${A.minutes} 分钟</span>
    <span class="tag brand">人工改动 ${A.stats.rate}</span>
  </div>
  <div class="row">
    <button class="btn btn-sm" onclick="App.toast('与上一版本对比')">${Icon('copy')} 版本对比</button>
    <button class="btn btn-sm" onclick="App.go('projects')">${Icon('folder')} 所属选题</button>
    <button class="btn btn-primary btn-sm" onclick="Article.exportBox()">${Icon('download')} 导出</button>
  </div>
</div>

<div class="compose-grid">
  <div>
    <div class="card" style="margin-bottom:14px">
      <div class="card-h"><h3>标题候选</h3><div class="sub">AI 给 4 个，用户选或自己写</div></div>
      <div class="card-b">
        ${A.alts.map((t, i) => `
          <label class="row" style="align-items:flex-start;margin-bottom:8px;cursor:pointer">
            <input type="radio" name="tt" ${i === 0 ? 'checked' : ''} style="margin-top:3px">
            <span class="small" style="flex:1">${t}</span>
          </label>`).join('')}
        <div class="row"><input class="inp" placeholder="或者自己写一个…"><button class="btn btn-sm">使用</button></div>
      </div>
    </div>

    <div class="stream" style="min-height:auto">
      ${A.sections.map((s, i) => `
        <h2>${s.h} <button class="btn btn-sm btn-ghost" onclick="Article.regen(${i})">${Icon('refresh')} 重写这段</button></h2>
        <p>${s.p}</p>`).join('')}
    </div>

    <div class="card" style="margin-top:14px">
      <div class="card-h"><h3>可追溯 · citation_map</h3>
        <div class="sub">段落 → 资讯 / 证据 → run，悬停正文里的角标也能看</div></div>
      <div class="card-b tight">
        <table class="tbl">
          <thead><tr><th style="width:170px">段落</th><th style="width:200px">来源</th><th>原文片段</th><th style="width:80px">run</th></tr></thead>
          <tbody>
            <tr><td>一、先说结论</td><td>《若干措施》第三条</td><td class="small muted">新建大型及以上数据中心 PUE 不高于 1.25</td><td class="mono small">r_8f21</td></tr>
            <tr><td>三、被逼出来的存量改造</td><td>界面新闻 2026-09-19</td><td class="small muted">部分地区出现补贴—采购—回流空转链条</td><td class="mono small">r_8f21</td></tr>
            <tr><td>五、我的分歧点</td><td>点评 a3（用户观点）</td><td class="small muted">增速 25% 是结果不是手段</td><td class="mono small">—</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="card-h"><h3>版本对比 · AI 稿 vs 人工稿</h3>
        <div class="sub">改动 ${A.stats.edited} / ${A.stats.total} 字 = ${A.stats.rate}（目标 ≤ 30%）</div></div>
      <div class="card-b tight" style="padding:10px 0">
        ${A.diff.map(d => '<div class="diff-line ' + d.t + '">' +
          (d.t === 'del' ? '- ' : d.t === 'add' ? '+ ' : '  ') + App.esc(d.a || d.b) + '</div>').join('')}
      </div>
      <div class="card-b" style="border-top:1px solid var(--line-2)">
        <div class="small muted">★ 人工 diff 是 M4「风格自学习」的训练信号：从改动里提取偏好，反哺提示词。</div>
      </div>
    </div>
  </div>

  <div class="col">
    <div class="card">
      <div class="card-h"><h3>本篇统计</h3></div>
      <div class="card-b">
        <div class="row between small"><span class="muted">字数</span><strong>${A.words}</strong></div>
        <div class="row between small"><span class="muted">从选题到定稿</span><strong>${A.minutes} 分钟</strong></div>
        <div class="row between small"><span class="muted">AI 成本</span><strong>¥${A.cost}</strong></div>
        <div class="row between small"><span class="muted">人工改动率</span><strong>${A.stats.rate}</strong></div>
        <div class="row between small"><span class="muted">引用数</span><strong>6（零编造）</strong></div>
        <div class="row between small"><span class="muted">合规</span><span class="tag ok">无红线命中</span></div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>配图建议</h3></div>
      <div class="card-b">
        <div class="row" style="align-items:flex-start;margin-bottom:8px">
          <span class="tag brand">封面</span>
          <div class="small muted" style="flex:1">冷色调机房俯拍 + 大字"1.25"</div>
        </div>
        <div class="row" style="align-items:flex-start;margin-bottom:8px">
          <span class="tag">图表</span>
          <div class="small muted" style="flex:1">全国算力规模增速 vs 智能算力占比（双轴）</div>
        </div>
        <div class="row" style="align-items:flex-start">
          <span class="tag">图表</span>
          <div class="small muted" style="flex:1">存量机房 PUE 分布（改造前后对比）</div>
        </div>
        <div class="sep"></div>
        <div class="tiny faint">生成配图为 M4。</div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>沉淀（这一步在做什么）</h3></div>
      <div class="card-b small muted">
        <p style="margin:0 0 6px">· 文章入 <span class="mono">articles</span>，观点入<strong>观点库</strong>（供复用与 uniqueness 检查）</p>
        <p style="margin:0 0 6px">· 记录本次使用的<strong>提示词版本</strong>（v4 + v7）</p>
        <p style="margin:0">· 统计耗时 / 成本 / 改动率 → 用量看板</p>
      </div>
    </div>
  </div>
</div>`;
  }
};

window.Article = {
  regen(i) {
    App.modal({
      title: '重写这一段',
      body: '<div class="small muted" style="margin-bottom:10px">复用 section_writer 子代理，只重写选中段落，其余不变。</div>' +
        '<div class="field"><label class="lb">补充指令（可选）</label>' +
        '<textarea class="inp" rows="3" placeholder="例：更短一点，把数据挪到段首"></textarea></div>' +
        '<div class="row wrap"><span class="chip tiny">更短</span><span class="chip tiny">更像我</span><span class="chip tiny">补上口径</span></div>',
      footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">取消</button>' +
        '<button class="btn btn-primary" onclick="App.closeModal(this.closest(\'.mask\'));App.toast(\'段落重写中…（约 12s）\')">重写</button>'
    });
  },
  exportBox() {
    App.modal({
      title: '导出',
      body: '<div class="small muted" style="margin-bottom:10px">M3 只做导出，不做发布对接（M4）。</div>' +
        '<div class="row wrap">' +
        ['Markdown', 'HTML（公众号可粘贴）', 'Word', 'PDF'].map((f, i) =>
          '<span class="chip' + (i === 1 ? ' on' : '') + '">' + f + '</span>').join('') + '</div>' +
        '<div class="sep"></div>' +
        '<label class="row" style="align-items:flex-start;cursor:pointer">' +
        '<input type="checkbox" checked style="margin-top:3px">' +
        '<span class="small">附加「本文由 AI 辅助撰写」标识<span class="tiny faint"><br>合规要求：AI 生成内容可标识、可追责。默认勾选。</span></span></label>',
      footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">取消</button>' +
        '<button class="btn btn-primary" onclick="App.closeModal(this.closest(\'.mask\'));App.toast(\'已导出 HTML（公众号格式）\')">' + Icon('download') + ' 导出</button>'
    });
  }
};
