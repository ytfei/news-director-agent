window.Screens = window.Screens || {};

window.Screens.connectors = {
  title: '数据源管理',
  step: '①',
  stepIdx: 0,

  render() {
    const c = DB.connectors[0];
    return `
<div class="note" style="margin-bottom:14px">
  步骤 ① 是<strong>无人值守</strong>的后台流程：定时同步 → 归一化 → 两级去重 → 打标聚类 → 异步预生成 FactCard → 兴趣召回。
  这一页是它唯一的用户可见入口。
</div>

<div class="grid g2">
  <div class="card">
    <div class="card-h"><h3>${c.name}</h3><div class="sub">${c.type}</div>
      <div class="right">
        <span class="tag ${c.status === 'partial' ? 'warn' : 'ok'}">${c.status === 'partial' ? '部分成功' : '正常'}</span>
        <button class="btn btn-sm btn-primary" onclick="Connectors.sync()">${Icon('refresh')} 立即同步</button>
      </div>
    </div>
    <div class="card-b">
      <div class="grid g3">
        <div><div class="tiny muted">上次同步</div><div class="small"><strong>${c.last}</strong></div></div>
        <div><div class="tiny muted">下次同步</div><div class="small"><strong>${c.next}</strong></div></div>
        <div><div class="tiny muted">计划</div><div class="small"><strong>交易日每 30 分钟</strong></div></div>
      </div>
      <div class="sep"></div>
      <div class="grid g3">
        <div><div class="tiny muted">抓取</div><div class="small"><strong>${c.stats.fetched}</strong></div></div>
        <div><div class="tiny muted">入库</div><div class="small"><strong>${c.stats.inserted}</strong></div></div>
        <div><div class="tiny muted">重复</div><div class="small"><strong>${c.stats.duplicated}</strong> <span class="tag warn">3.1%</span></div></div>
      </div>
      <div class="sep"></div>
      <div class="note warn small">重复率 3.1%（50/1628）> M1 验收要求的 2%。根因是事件簇没真正聚起来（TODO · P0-1），
      与归簇/去重改进一起解决。</div>
    </div>
  </div>

  <div class="card">
    <div class="card-h"><h3>接口权限探测</h3><div class="sub">probe 结果必须在 UI 上说人话</div></div>
    <div class="card-b tight">
      <table class="tbl">
        <thead><tr><th style="width:190px">接口</th><th style="width:70px">权限</th><th>说明</th></tr></thead>
        <tbody>
          ${c.caps.map(x => `<tr>
            <td class="mono small">${x.api}</td>
            <td class="${x.perm === 'ok' ? 'perm-ok' : x.perm === 'no' ? 'perm-no' : 'perm-part'} small">${x.perm === 'ok' ? '可用' : '无权限'}</td>
            <td class="small muted">${x.note}</td>
          </tr>`).join('')}
        </tbody>
      </table>
      <div class="small muted" style="padding:8px 4px 4px">
        ★ 最危险的是 <span class="mono">news</span>：返回 0 行<strong>且不报错</strong>，会造成"同步成功但 0 条"的假象。
      </div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-h"><h3>同步日志</h3><div class="sub">sync_runs</div></div>
  <div class="card-b tight">
    <table class="tbl">
      <thead><tr><th style="width:120px">时间</th><th style="width:130px">连接器</th><th style="width:90px">状态</th>
        <th style="width:80px">抓取</th><th style="width:80px">入库</th><th style="width:80px">重复</th><th>说明</th></tr></thead>
      <tbody>
        ${DB.syncLogs.map(l => `<tr>
          <td class="small">${l.t}</td>
          <td class="small">${l.conn}</td>
          <td><span class="tag ${l.status === 'success' ? 'ok' : l.status === 'partial' ? 'warn' : 'danger'}">${
            { success: '成功', partial: '部分', failed: '失败' }[l.status]}</span></td>
          <td class="small mono">${l.fetched}</td>
          <td class="small mono">${l.ins}</td>
          <td class="small mono">${l.dup}</td>
          <td class="small muted">${l.msg || '—'}</td>
        </tr>`).join('')}
      </tbody>
    </table>
  </div>
</div>

<div class="grid g2">
  <div class="card">
    <div class="card-h"><h3>其他连接器</h3><div class="sub">数据源必须可插拔</div></div>
    <div class="card-b">
      ${DB.connectors.slice(1).map(x => `
        <div class="row between" style="padding:9px 0;border-bottom:1px solid var(--line-2)">
          <div>
            <div class="small"><strong>${x.name}</strong> <span class="tag">${x.type}</span></div>
            <div class="tiny muted">${x.note}</div>
          </div>
          <button class="btn btn-sm" disabled>${Icon('plus')} 接入</button>
        </div>`).join('')}
      <div class="sep"></div>
      <div class="small muted">P1 科技博主的信息源在 X / arXiv / 公司博客，
      没有 <span class="mono">web_probe</span> 与 RSS，事实核查就被锁死在 tushare 覆盖范围里。</div>
    </div>
  </div>

  <div class="card">
    <div class="card-h"><h3>失败处理约定</h3></div>
    <div class="card-b">
      <table class="tbl">
        <tbody>
          <tr><td style="width:130px" class="small">部分分段失败</td><td class="small muted">status=partial，下次从断点续拉，UI 提示"部分数据延迟"</td></tr>
          <tr><td class="small">接口限流 429</td><td class="small muted">指数退避重试，最多 3 次，仍失败则跳过并在下次补偿</td></tr>
          <tr><td class="small">权限 / 积分不足</td><td class="small muted">status=failed，在本页高亮"当前 token 无 XX 接口权限"</td></tr>
          <tr><td class="small">全文为空</td><td class="small muted">区分「非交易日 / 区间无数据 / 权限不足」，给人口语化说明</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>`;
  }
};

window.Connectors = {
  sync() {
    const mask = App.modal({
      title: '正在同步 · Tushare Pro',
      body: `<div class="small muted" style="margin-bottom:12px">
          读取启用连接器 → 建 sync_run → 抓取 → 归一化 → content_hash 精确去重 → 近似去重/聚类 → 打标 → 落库 → 入队 FactCard
        </div>
        <div class="progress" id="sp"><i style="width:0%"></i></div>
        <div class="small muted" style="margin-top:10px" id="spt">抓取中…</div>
        <div class="sep"></div>
        <div id="splog" class="tiny mono muted" style="line-height:1.9"></div>`,
      footer: '<button class="btn" onclick="App.closeModal(this.closest(\'.mask\'))">后台继续</button>'
    });
    const bar = mask.querySelector('#sp > i');
    const txt = mask.querySelector('#spt');
    const log = mask.querySelector('#splog');
    const seq = [
      ['major_news 抓取 402 条', 25],
      ['cctv_news 抓取 96 条', 40],
      ['content_hash 去重：重复 6 条', 60],
      ['simhash 近似去重 + 事件聚类', 80],
      ['打标 / 实体 / 关联标的 / 重要度', 92],
      ['入队 FactCard 预生成（异步）', 100]
    ];
    let i = 0;
    const t = setInterval(() => {
      if (i >= seq.length) {
        clearInterval(t);
        txt.innerHTML = '<strong>同步完成</strong> · fetched 498 / inserted 492 / duplicated 6';
        setTimeout(() => { App.closeModal(mask); App.toast('已同步 · 收件箱新增 12 条'); }, 700);
        return;
      }
      bar.style.width = seq[i][1] + '%';
      txt.textContent = seq[i][0];
      log.innerHTML += 'sync.progress · ' + seq[i][0] + '<br>';
      i++;
    }, 560);
  }
};
