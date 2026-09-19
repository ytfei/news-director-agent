window.Screens = window.Screens || {};

window.Screens.inbox = {
  title: '今日收件箱',
  step: '②',
  stepIdx: 1,

  render() {
    const recalled = [1, 3, 2, 9, 6].map(i => App.newsById(i));
    const blocked = DB.annotations.filter(a => App.verdictOf(a.id) === 'blocked');

    return `
<div class="hero" style="background:linear-gradient(135deg,#111827,#1f2937)">
  <h2>早上好，${DB.profile.name}</h2>
  <p>今天有 <strong>37 条</strong>命中你的兴趣画像。按真实节奏，你应该花 <strong>15 分钟</strong>读完并写下 5 条判断，
  剩下的交给系统 —— 这是这个产品唯一希望你养成的习惯。</p>
  <div class="row">
    <a class="btn btn-primary" href="#/news">${Icon('news')} 去资讯中心挑素材</a>
    <a class="btn btn-ghost" style="color:#9ca3af" href="#/annotate">${Icon('pen')} 继续上次的点评</a>
  </div>
</div>

<div class="grid g4" style="margin-bottom:14px">
  <div class="card stat"><div class="k">今日新增</div><div class="v">128<small>条</small></div><div class="d up">↑ 较昨日 +18%</div></div>
  <div class="card stat"><div class="k">命中兴趣</div><div class="v">37<small>条</small></div><div class="d">画像召回率 28.9%</div></div>
  <div class="card stat"><div class="k">今日素材</div><div class="v">${App.matList({ date: '2026-09-19' }).length}<small>条</small></div><div class="d">${App.matList({ date: '2026-09-19' }).filter(x => !App.hasAnn(x.newsId)).length} 条还没批注</div></div>
  <div class="card stat"><div class="k">本周已产出</div><div class="v">3<small>篇</small></div><div class="d up">目标 5 篇/周</div></div>
</div>

<div class="grid g2">
  <div class="card">
    <div class="card-h"><h3>今日待办</h3><div class="sub">按最省时间的顺序排</div></div>
    <div class="card-b tight">
      <div class="itemrow" onclick="App.go('news',{view:'todo'})">
        <div class="row between"><div class="t">${Icon('bookmark')} 给今日素材补批注</div><span class="tag brand">${App.matList({ date: '2026-09-19', noAnn: true }).length} 条待批注</span></div>
        <div class="m">素材组 2026-09-19 · 就地在资讯中心写，不用跳页</div>
        <div class="snip">评分最高的还没写：${(App.matList({ date: '2026-09-19', noAnn: true })[0] ? App.newsById(App.matList({ date: '2026-09-19', noAnn: true })[0].newsId).title.slice(0, 24) : '（已全部批注）')}…</div>
      </div>
      <div class="itemrow" onclick="App.go('annotate')">
        <div class="row between"><div class="t">${Icon('pen')} 在工作台深化点评</div><span class="tag">按素材筛选</span></div>
        <div class="m">素材库 ${Object.keys(App.state.materials).length} 条 · 已批注 ${Object.keys(App.state.materials).map(Number).filter(i => App.hasAnn(i)).length} 条</div>
        <div class="snip">按日期 / 评分 / 主题筛出今天最值得写的那几条</div>
      </div>
      ${blocked.length ? `
      <div class="itemrow" onclick="App.go('review')">
        <div class="row between"><div class="t">${Icon('shield')} 处理体检报告红线</div><span class="tag danger">${blocked.length} 条 blocked</span></div>
        <div class="m">批次 #12 · 今天 14:20 完成</div>
        <div class="snip">「这家公司的估值体系就是骗局」命中的是未证实指控，必须改掉才能写作</div>
      </div>` : ''}
      <div class="itemrow" onclick="App.go('compose')">
        <div class="row between"><div class="t">${Icon('wand')} 确认大纲</div><span class="tag brand">等待你</span></div>
        <div class="m">选题「中芯扩产：一场被误读的抢跑」· 暂停在 outline_approval</div>
        <div class="snip">★ 超过 24h 未响应会自动取消，别拖</div>
      </div>
      <div class="itemrow" onclick="App.go('article')">
        <div class="row between"><div class="t">${Icon('file')} 定稿与导出</div><span class="tag ok">可导出</span></div>
        <div class="m">「算力新政：真正的约束是 PUE」· 2860 字 · 改动率 14.4%</div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-h"><h3>为你召回</h3><div class="sub">兴趣画像命中 · 按重要度与你的历史偏好排序</div>
      <div class="right"><a class="btn btn-sm" href="#/news">全部</a></div></div>
    <div class="card-b tight">
      ${recalled.map(n => `
        <div class="itemrow" onclick="Detail.open(${n.id})">
          <div class="row between"><div class="t">${n.title.slice(0, 30)}…</div>
            <span class="tag ${n.imp === 'high' ? 'danger' : n.imp === 'mid' ? 'warn' : ''}">${n.imp === 'high' ? '重要' : n.imp === 'mid' ? '一般' : '参考'}</span></div>
          <div class="m">${n.source} · ${n.time} ${n.cluster ? '· <span class="tag">簇 ' + n.cluster.count + '</span>' : ''}</div>
          <div class="snip">${n.summary}</div>
        </div>`).join('')}
    </div>
    <div class="card-b tight" style="border-top:1px solid var(--line-2)">
      <div class="small muted">命中依据：关注行业（半导体 / 电力设备 / 食品饮料）+ 类型（公告 / 政策）+ 关键词（产能利用率 / 渠道结构 / PUE）</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>这周你已经产出了什么</h3><div class="sub">沉淀视图的雏形：观点 → 稿件 → 成本</div></div>
  <div class="card-b">
    <div class="timeline">
      <div class="tl-item on"><div class="t">今天 15:02</div><div class="c">选题「中芯扩产：一场被误读的抢跑」就绪，等待写作 · 已聚合 2 条点评 + 3 条资讯</div></div>
      <div class="tl-item on"><div class="t">今天 14:45</div><div class="c">完成批次 #12 检查：5 条点评 → 1 通过 / 3 需修改 / 1 有红线</div></div>
      <div class="tl-item on"><div class="t">昨天 18:20</div><div class="c">稿件「算力新政：真正的约束是 PUE」定稿 · 2860 字 · 成本 ¥2.86 · 人工改动 14.4%</div></div>
      <div class="tl-item on"><div class="t">昨天 09:30</div><div class="c">写下 5 条点评（中芯 / 茅台 / 算力 / 宁德 / 美联储）· 用时 14 分钟</div></div>
      <div class="tl-item"><div class="t">周一</div><div class="c">观点入库 5 条；「茅台渠道结构」观点被复用 1 次</div></div>
    </div>
  </div>
</div>

<div class="grid g2">
  <div class="card">
    <div class="card-h"><h3>首日冷启动怎么办</h3></div>
    <div class="card-b">
      <div class="small muted">
        <p style="margin:0 0 8px">新用户不知道看什么 → 默认预置「沪深300 成分 + 宏观 + 政策」画像，并给热门榜。</p>
        <p style="margin:0 0 8px">面对空白点评框发呆 → 编辑器里给「AI 提示问题」（只提问，不给答案）。</p>
        <p style="margin:0">没有历史文章 → 支持粘贴 3~5 篇旧作，自动提取风格画像生成初始提示词。</p>
      </div>
      <div class="sep"></div>
      <a class="btn btn-sm" href="#/onboarding">${Icon('user')} 看首次使用引导</a>
    </div>
  </div>
  <div class="card">
    <div class="card-h"><h3>这一页的产品判断</h3></div>
    <div class="card-b">
      <div class="note small">
        收件箱 = <strong>命中兴趣的召回结果</strong>，不是全量资讯流。全量在「资讯中心」。
        如果首页就是全量，用户会重新陷入刷 RSS 的老路 —— 那就没有产品价值了。
      </div>
      <div class="sep"></div>
      <div class="small muted">排序信号：重要度打分 × 画像匹配度 × 同类历史互动（★评级 / 收藏 / 隐藏）。</div>
    </div>
  </div>
</div>`;
  }
};
