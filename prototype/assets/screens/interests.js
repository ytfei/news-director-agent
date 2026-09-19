window.Screens = window.Screens || {};

window.Screens.interests = {
  title: '兴趣画像',

  render() {
    const p = DB.profile;
    const allMarkets = ['A股', '港股', '美股', '宏观'];
    const allTypes = ['快讯', '长文', '公告', '政策', '研报'];
    const allInd = ['半导体', '电力设备', '食品饮料', '计算机', '机械设备', '医药', '银行', '汽车', '农林牧渔'];

    const heat = [
      ['半导体', 92], ['计算机', 78], ['电力设备', 64], ['食品饮料', 58],
      ['机械设备', 41], ['宏观', 88], ['医药', 22], ['汽车', 19]
    ];

    return `
<div class="grid" style="grid-template-columns:minmax(0,1fr) 300px;align-items:start">
  <div>
    <div class="card">
      <div class="card-h"><h3>关注的市场</h3></div>
      <div class="card-b">
        <div class="row wrap">
          ${allMarkets.map(m => '<span class="chip' + (p.markets.includes(m) ? ' on' : '') + '" onclick="this.classList.toggle(\'on\')">' + m + '</span>').join('')}
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>关注行业 / 板块</h3><div class="sub">可点选，影响收件箱召回</div></div>
      <div class="card-b">
        <div class="row wrap">
          ${allInd.map(m => '<span class="chip' + (p.industries.includes(m) ? ' on' : '') + '" onclick="this.classList.toggle(\'on\')">' + m + '</span>').join('')}
          <span class="chip">${Icon('plus')} 添加</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>内容类型</h3></div>
      <div class="card-b">
        <div class="row wrap">
          ${allTypes.map(m => '<span class="chip' + (p.types.includes(m) ? ' on' : '') + '" onclick="this.classList.toggle(\'on\')">' + m + '</span>').join('')}
        </div>
        <div class="sep"></div>
        <div class="note warn small">当前 token 无 <strong>公告 / 政策 / 研报</strong>接口权限（TODO · P0-3），
        勾选这三类也拿不到数据 —— 需要在数据源页接第二个源。</div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>关键词</h3><div class="sub">命中即加权</div></div>
      <div class="card-b">
        <div class="row wrap">
          ${p.keywords.map(k => '<span class="chip on">' + k + ' <span class="x">×</span></span>').join('')}
          <span class="chip">${Icon('plus')} 添加关键词</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>屏蔽词</h3><div class="sub">命中即不进收件箱</div></div>
      <div class="card-b">
        <div class="row wrap">
          ${p.blocked.map(k => '<span class="chip" style="border-color:#f0c8c8;color:#b91c1c;background:#fff5f5">' + Icon('ban') + k + ' <span class="x">×</span></span>').join('')}
          <span class="chip">${Icon('plus')} 添加屏蔽词</span>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-h"><h3>来源偏好</h3><div class="sub">同源多报时决定代表条</div></div>
      <div class="card-b">
        <div class="row wrap">
          ${p.sources.map(k => '<span class="chip on">' + k + '</span>').join('')}
          ${['彭博', '路透', '公司博客', 'X'].map(k => '<span class="chip">' + k + '</span>').join('')}
        </div>
      </div>
    </div>

    <div class="row" style="margin-top:14px">
      <button class="btn btn-primary" onclick="App.toast('画像已保存 · 收件箱将在下次同步后生效')">保存画像</button>
      <button class="btn" onclick="App.go('onboarding')">重跑首次引导</button>
    </div>
  </div>

  <div class="col">
    <div class="card">
      <div class="card-h"><h3>画像热度</h3><div class="sub">由 ★评级 / 收藏 / 隐藏反哺</div></div>
      <div class="card-b">
        ${heat.map(h => `
          <div class="row" style="margin-bottom:7px">
            <span class="small" style="width:66px">${h[0]}</span>
            <div class="progress" style="flex:1"><i style="width:${h[1]}%"></i></div>
            <span class="tiny mono muted" style="width:26px;text-align:right">${h[1]}</span>
          </div>`).join('')}
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h3>冷启动默认值</h3></div>
      <div class="card-b small muted">
        新用户不知道看什么 → 预置「沪深300 成分 + 宏观 + 政策」，并给热门榜。
        画像在用户产生 20 次互动后开始接管排序。
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h3>画像的两个用途</h3></div>
      <div class="card-b small muted">
        <p style="margin:0 0 6px"><strong>即时</strong>：影响收件箱排序与重要度打分；</p>
        <p style="margin:0"><strong>长期（M4）</strong>：作为自学习训练信号，也是 uniqueness 轨道（观点是否有增量）的比对素材。</p>
      </div>
    </div>
  </div>
</div>`;
  }
};
