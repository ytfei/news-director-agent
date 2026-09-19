window.Screens = window.Screens || {};

window.Screens.overview = {
  title: '原型地图',
  group: '总览',

  render() {
    const ia = [
      { lv: 'L1', name: '资讯台 · Curate', go: 'news', icon: 'news',
        pts: ['多源同步与归一化', '事件簇折叠（另 N 家报道）', '筛选 / 搜索 / 详情',
              '★ 加入素材（评分 1~10 + 主题 + 日期）', '★ 就地批注，不跳页'] },
      { lv: 'L2', name: '观点室 · Review', go: 'annotate', icon: 'pen',
        pts: ['数据源 = 素材库（按日期/评分/主题筛）', '富文本 + 自动保存 + 版本',
              'AI 三轨检查（事实/逻辑/合规）', '划词高亮 · 采纳 · 驳回'] },
      { lv: 'L3', name: '写作台 · Compose', go: 'compose', icon: 'wand',
        pts: ['选题 = 一组素材（+可选点评）', '提示词 = 可加载技能包', '大纲 interrupt 确认', '流式写作 · 段落重写 · 导出'] },
      { lv: '·', name: '支撑模块', go: 'connectors', icon: 'db',
        pts: ['数据源管理与权限探测', '兴趣画像与召回', '提示词 / 模板库', '用量与硬配额'] }
    ];

    const flow = [
      ['①', '后台同步', 'connectors', '无人值守。数据源 → 归一化 → 两级去重 → 打标聚类 → 异步预生成 FactCard'],
      ['②', '浏览资讯台', 'inbox', '收件箱是"命中兴趣"的召回结果，不是全量资讯'],
      ['③', '标记素材', 'news', '感兴趣的资讯 → 加入素材：评分 1~10 + 主题 + 日期（默认每天一组）'],
      ['④', '就地批注', 'news', '在资讯中心直接写，不跳页；也可勾选后批量展开批注'],
      ['⑤', '深化点评', 'annotate', '工作台只处理素材，按日期/评分/主题筛；自动保存'],
      ['⑥', '提交检查', 'annotate', '异步三轨并行，并发 ≤ 5，进度条按条目推进'],
      ['⑦', '体检报告', 'review', 'blocker 禁止进入写作；建议可一键采纳；驳回需填理由'],
      ['⑧', '创建选题', 'projects', '从素材库挑一组素材（不要求有点评）+ 提示词组合'],
      ['⑨', 'AI 写作', 'compose', '大纲 HITL 断点 → 分段流式 → 事实复核 → 风格统一'],
      ['⑩', '编辑定稿', 'article', '版本 diff、段落重写、引用可悬停、导出含 AI 标识'],
      ['⑪', '沉淀归档', 'usage', '观点入库、提示词版本留档、成本与改动率统计']
    ];

    return `
<div class="hero">
  <h2>主理人 Agent · 交互原型 v0.1</h2>
  <p>这是一个<strong>纯静态、可点击</strong>的原型，用来先理清「用户怎么用这个产品」：交互、流程、功能结构。
  所有数据为 mock，所有按钮都有反馈（部分仅提示）。核心链路
  <strong>资讯 → 点评 → 检查 → 选题 → 写作 → 定稿</strong> 已打通，可完整走一遍。</p>
  <div class="row">
    <a class="btn btn-primary" href="#/inbox">从 ② 今日收件箱开始走流程</a>
    <a class="btn btn-ghost" style="color:#c7d2fe" href="#/annotate">直接看 ⑤ 点评工作台</a>
    <a class="btn btn-ghost" style="color:#c7d2fe" href="#/compose">直接看 ⑨ 写作台</a>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>一句话定位</h3></div>
  <div class="card-b">
    <div class="note">
      用户每天只做一件事：<strong>对感兴趣的资讯写下碎片化判断</strong>；
      系统负责另外四件：<strong>补齐事实、查错纠偏、按风格成文、留下审计</strong>。
      系统不替用户"想"，只帮用户"说清楚"——这是所有交互设计的原点。
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>素材 · 整个产品的中枢对象</h3><div class="sub">资讯 → 素材 → 点评 → 选题 → 稿件</div></div>
  <div class="card-b">
    <div class="grid g2">
      <div>
        <div class="note small">
          素材 = <strong>一条被你标记的资讯</strong> + 三个维度：<br>
          ① <strong>评分 1~10</strong>（有多想写它）　② <strong>主题</strong>（多维标签，可多选）　③ <strong>日期</strong>（默认归入当天，天然按天成组）
        </div>
        <div class="sep"></div>
        <table class="tbl">
          <tbody>
            <tr><td style="width:120px" class="small muted">在哪产生</td><td class="small">资讯中心，就地操作，<strong>不跳页</strong></td></tr>
            <tr><td class="small muted">谁消费它</td><td class="small">点评工作台（按三维筛选）、选题（挑一组素材）</td></tr>
            <tr><td class="small muted">是否必须有点评</td><td class="small"><strong>否</strong> —— 标一组素材、定好选题就能直接让 AI 写</td></tr>
            <tr><td class="small muted">有无点评的差别</td><td class="small">有点评 = 观点驱动（有你的判断）；无点评 = 素材综述（有事实有结构，缺判断）</td></tr>
          </tbody>
        </table>
      </div>
      <div>
        <div class="fs-tree" style="font-size:13px">
          资讯流（全量）<br>
          │<br>
          ├─ ▸ <span class="f">加入素材</span>　评分 8 · 主题[扩产,半导体] · 日期 2026-09-19<br>
          │　　├─ 就地批注（可选）──▶ 点评<br>
          │　　└─ 提交检查（可选）──▶ 体检报告<br>
          │<br>
          └─ 不标记 ──▶ 读过即走，不进入后续链路
        </div>
        <div class="sep"></div>
        <div class="small muted">
          <p style="margin:0 0 8px"><strong>为什么默认按天分组</strong>：主理人是日更节奏 —— 早上挑素材、上午写判断、下午成文。日期组天然对齐这个节奏，也是"今天该写什么"的默认答案。</p>
          <p style="margin:0"><strong>为什么用 1~10 而不是 ★1~5</strong>：5 级区分度不够，主理人实际只会在 7~10 之间打分；10 级能把"最想写的那条"挑出来。</p>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>功能结构 · 三层 × 四个模块组</h3><div class="sub">点卡片进入对应页面</div></div>
  <div class="card-b">
    <div class="grid g4">
      ${ia.map(x => `
        <div class="ia-card" onclick="App.go('${x.go}')">
          <div class="lv">${x.lv}</div>
          <h4>${x.name}</h4>
          <ul>${x.pts.map(p => '<li>' + p + '</li>').join('')}</ul>
        </div>`).join('')}
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>主流程 11 步</h3><div class="sub">对应 docs/03-user-flow.md §2；顶部步骤条可全程跳转</div></div>
  <div class="card-b">
    <table class="tbl">
      <thead><tr><th style="width:36px"></th><th style="width:110px">步骤</th><th style="width:110px">页面</th><th>这一步在解决什么</th></tr></thead>
      <tbody>
        ${flow.map(f => `<tr>
          <td><a class="tag solid" href="#/${f[2]}">${f[0]}</a></td>
          <td><strong>${f[1]}</strong></td>
          <td><a href="#/${f[2]}">${f[2]}</a></td>
          <td class="muted">${f[3]}</td>
        </tr>`).join('')}
      </tbody>
    </table>
  </div>
</div>

<div class="grid g2">
  <div class="card">
    <div class="card-h"><h3>状态机 · 点评（Annotation）</h3></div>
    <div class="card-b">
      <div class="fs-tree">
        draft ──自动保存(新版本)──▶ draft<br>
        draft ──提交检查──▶ checking<br>
        checking ──有 high/medium──▶ needs_revision<br>
        checking ──有 blocker──▶ blocked<br>
        checking ──无 high 以上──▶ passed<br>
        blocked / needs_revision ──用户修改──▶ draft<br>
        passed / needs_revision ──锁定(留审计)──▶ locked ──▶ 进入选题
      </div>
      <div class="sep"></div>
      <div class="small muted">verdict 规则：<span class="tag ok">passed</span> 无 blocker/high ·
        <span class="tag warn">needs_revision</span> 有 high/medium（可写作但强提示）·
        <span class="tag danger">blocked</span> 有 blocker（<strong>禁止进入写作</strong>）</div>
    </div>
  </div>

  <div class="card">
    <div class="card-h"><h3>状态机 · 选题（Project）</h3></div>
    <div class="card-b">
      <div class="fs-tree">
        collecting ──提交检查──▶ reviewing ──全部通过──▶ ready<br>
        reviewing ──需修改──▶ collecting<br>
        ready ──触发写作──▶ composing ──大纲确认──▶ drafting<br>
        composing ──放弃大纲──▶ ready　　composing ──24h 超时──▶ cancelled<br>
        drafting ──段落重写──▶ drafting ──定稿──▶ completed ──▶ archived
      </div>
      <div class="sep"></div>
      <div class="small muted">★ M3 起：<strong>至少 1 条 passed 点评</strong>才允许触发写作。
      空的"资讯综述模式"必产出 AI 味内容，与"观点驱动"直接冲突。</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>三条检查轨道 · 阈值取向不同（不能共用一个阈值）</h3></div>
  <div class="card-b">
    <table class="tbl">
      <thead><tr><th style="width:110px">轨道</th><th style="width:90px">取向</th><th style="width:150px">策略</th><th>典型 finding</th></tr></thead>
      <tbody>
        <tr><td><span class="tag info">fact</span> 事实</td><td>高精度<br><span class="tiny muted">宁可漏报</span></td><td>高阈值；blocker/high <strong>必须带 evidence</strong></td><td class="muted">"你写营收增长 30%，最新财报是 12.4%，疑似混淆口径"</td></tr>
        <tr><td><span class="tag danger">compliance</span> 合规</td><td>高召回<br><span class="tiny muted">宁可误报</span></td><td>低阈值；红线词库优先命中</td><td class="muted">"'就是骗局'属未证实指控，有法律风险，建议改为…"</td></tr>
        <tr><td><span class="tag brand">logic</span> 逻辑</td><td>折中</td><td>中阈值；info 默认折叠</td><td class="muted">"'因此必然上涨'属绝对化断言，建议改为条件句"</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="grid g2">
  <div class="card">
    <div class="card-h"><h3>交互约定（原型内已实现）</h3></div>
    <div class="card-b">
      <table class="tbl">
        <tbody>
          <tr><td style="width:120px"><span class="kbd">j</span> <span class="kbd">k</span></td><td class="muted">资讯流上下移动</td></tr>
          <tr><td><span class="kbd">1</span>–<span class="kbd">5</span></td><td class="muted">★评级</td></tr>
          <tr><td><span class="kbd">s</span> / <span class="kbd">space</span></td><td class="muted">收藏 / 选中</td></tr>
          <tr><td>事件簇展开</td><td class="muted">点「另 N 家报道」横排对比各源差异（交叉验证）</td></tr>
          <tr><td>划词高亮</td><td class="muted">severity 决定颜色：红=红线 橙=严重 黄=中等 青=轻微 灰=提示</td></tr>
          <tr><td>采纳建议</td><td class="muted">用 suggestion 替换原文，生成新的 annotation_version</td></tr>
          <tr><td>驳回</td><td class="muted">必填理由 → 记入历史，用于后续降低误报</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <div class="card-h"><h3>HITL 断点（用户必须能在中途插手）</h3></div>
    <div class="card-b">
      <table class="tbl">
        <thead><tr><th style="width:140px">断点</th><th style="width:90px">时机</th><th>用户可做</th></tr></thead>
        <tbody>
          <tr><td>outline_approval</td><td>大纲生成后</td><td class="muted">确认 / 增删章节 / 调整顺序 / 补充要点</td></tr>
          <tr><td>mid_write_instruction</td><td>写作过程中</td><td class="muted">发指令："第二段压缩一半"、"加一段反方观点"</td></tr>
          <tr><td>section_regenerate</td><td>成稿后</td><td class="muted">对任意段落点"重写"</td></tr>
          <tr><td>finding 处置</td><td>体检报告</td><td class="muted">采纳 / 驳回（写理由）/ 忽略</td></tr>
        </tbody>
      </table>
      <div class="sep"></div>
      <div class="note warn">大纲确认若 <strong>24h</strong> 无响应 → run 置 cancelled 并通知，否则中断的 run 会永久堆积。</div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>原型页面清单</h3><div class="sub">左侧导航按三层分组，与 docs/01 §3.1 一致</div></div>
  <div class="card-b">
    <table class="tbl">
      <thead><tr><th style="width:150px">页面</th><th style="width:80px">层</th><th style="width:70px">流程</th><th>原型里能试什么</th></tr></thead>
      <tbody>
        <tr><td><a href="#/inbox">今日收件箱</a></td><td>L1</td><td>②</td><td class="muted">今日概览、待办、兴趣召回</td></tr>
        <tr><td><a href="#/news">资讯中心</a></td><td>L1</td><td>②③④</td><td class="muted">筛选、事件簇展开、★评级、<strong>加入素材（评分/主题/日期）</strong>、就地批注</td></tr>
        <tr><td><a href="#/news?view=material">素材库</a></td><td>L1</td><td>③</td><td class="muted">资讯中心的素材视图：按日期 / 评分 / 主题多维筛选</td></tr>
        <tr><td><a href="#/detail">资讯详情</a></td><td>L1</td><td>②</td><td class="muted">从资讯卡片标题点开（抽屉）：全文 + 簇内差异 + 时间线</td></tr>
        <tr><td><a href="#/interests">兴趣画像</a></td><td>L1</td><td>—</td><td class="muted">市场 / 行业 / 类型 / 关键词 / 屏蔽词</td></tr>
        <tr><td><a href="#/connectors">数据源管理</a></td><td>L1</td><td>①</td><td class="muted">权限探测结果、手动同步、同步日志</td></tr>
        <tr><td><a href="#/annotate">点评工作台</a></td><td>L2</td><td>⑤⑥</td><td class="muted">按日期/评分/主题筛素材 → 深化点评、AI 提示问题、引用事实、提交检查</td></tr>
        <tr><td><a href="#/review">AI 体检报告</a></td><td>L2</td><td>⑦</td><td class="muted">采纳 / 驳回（写理由）/ 复检 → verdict 实时变化</td></tr>
        <tr><td><a href="#/facts">事实卡片</a></td><td>L2</td><td>⑦</td><td class="muted">claim + status + evidence + 置信度 + 未查清项</td></tr>
        <tr><td><a href="#/projects">选题</a></td><td>L2/L3</td><td>⑧</td><td class="muted">从素材库挑素材建选题、选提示词组合；<strong>无点评也能直接写作</strong></td></tr>
        <tr><td><a href="#/compose">AI 写作</a></td><td>L3</td><td>⑨</td><td class="muted">大纲 HITL 编辑 → 流式写作 → 中途指令 → 事实复核</td></tr>
        <tr><td><a href="#/article">稿件</a></td><td>L3</td><td>⑩⑪</td><td class="muted">标题候选、引用悬停、版本 diff、导出（含 AI 标识）</td></tr>
        <tr><td><a href="#/prompts">提示词管理</a></td><td>L3</td><td>—</td><td class="muted">分类、变量、版本、官方模板库</td></tr>
        <tr><td><a href="#/usage">用量与配额</a></td><td>全部</td><td>⑪</td><td class="muted">成本看板、硬配额（超额直接拒绝）</td></tr>
        <tr><td><a href="#/onboarding">首次使用引导</a></td><td>—</td><td>—</td><td class="muted">5 步 &lt; 5 分钟：兴趣 → 数据源 → 风格资产</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>原型与文档的映射</h3></div>
  <div class="card-b">
    <div class="row wrap">
      <span class="tag">docs/01 §3 三层产品结构</span>
      <span class="tag">docs/01 §5 功能模块清单（16 项）</span>
      <span class="tag">docs/03 §2 主流程 11 步</span>
      <span class="tag">docs/03 §4 状态机</span>
      <span class="tag">docs/03 §5 异常与边界</span>
      <span class="tag brand">本报告页 ≈ 原型索引</span>
    </div>
    <div class="sep"></div>
    <div class="small muted">
      原型只覆盖 M1~M3 主链路；M4 的「观点库 / 多平台改写 / 发布对接」在导航中以灰态预留，未画页面。
      已知缺口：事件簇当前后端几乎一对一（P0-1），原型按<strong>理想态</strong>展示折叠效果。
    </div>
  </div>
</div>`;
  }
};
