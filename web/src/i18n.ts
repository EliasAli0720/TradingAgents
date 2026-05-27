// Minimal i18n. Keys mirror tradingbot/dashboard/i18n.py so wording is 1:1.
// Default zh, en kept for future toggle.

type Lang = 'zh' | 'en';

const DICT: Record<string, { zh: string; en: string }> = {
  'app.page_title':           { zh: 'TradingAgents 仪表盘', en: 'TradingAgents Dashboard' },
  'app.title':                { zh: '📈 TradingAgents 自动交易仪表盘', en: '📈 TradingAgents Auto-Trading Dashboard' },
  'app.sidebar.title':        { zh: 'TradingAgents 机器人', en: 'TradingAgents Bot' },
  'app.sidebar.last_refresh': { zh: '最近刷新：{time}', en: 'Last refresh: {time}' },
  'app.sidebar.mode_paper':   { zh: '模拟', en: 'PAPER' },
  'app.sidebar.mode_live':    { zh: '实盘', en: 'LIVE' },
  'app.sidebar.navigate':     { zh: '导航', en: 'Navigate' },
  'app.sidebar.watchlist':    { zh: '自选股', en: 'Watchlist' },
  'app.sidebar.refresh':      { zh: '刷新数据', en: 'Refresh Data' },
  'app.sidebar.language':     { zh: '语言', en: 'Language' },
  'app.sidebar.signed_in':    { zh: '已登录：{name}', en: 'Signed in as {name}' },
  'app.sidebar.logout':       { zh: '登出', en: 'Logout' },

  'nav.analysis':             { zh: '智能体推理', en: 'Agent Reasoning' },
  'nav.analysis_new':         { zh: '新建分析', en: 'New Analysis' },
  'nav.portfolio':            { zh: '持仓', en: 'Portfolio' },
  'nav.performance':          { zh: '业绩', en: 'Performance' },
  'nav.trades':               { zh: '交易记录', en: 'Trade History' },
  'nav.risk':                 { zh: '风险监控', en: 'Risk Monitor' },
  'nav.model':                { zh: '模型设置', en: 'Model Settings' },
  'nav.account':              { zh: '账户', en: 'Account' },
  'nav.admin_users':          { zh: '用户管理', en: 'Users' },
  'nav.admin_runs':           { zh: '所有任务', en: 'All Runs' },

  'group.analysis':           { zh: '分析', en: 'Analysis' },
  'group.trading':            { zh: '交易', en: 'Trading' },
  'group.settings':           { zh: '设置', en: 'Settings' },
  'group.admin':              { zh: '管理员', en: 'Admin' },

  'qt.header':                { zh: '手动快速下单', en: 'Quick Trade (Manual)' },
  'qt.ticker':                { zh: '股票代码', en: 'Ticker' },
  'qt.side':                  { zh: '方向', en: 'Side' },
  'qt.side.buy':              { zh: '买入', en: 'BUY' },
  'qt.side.sell':             { zh: '卖出', en: 'SELL' },
  'qt.qty':                   { zh: '股数', en: 'Shares' },
  'qt.submit':                { zh: '提交手动订单', en: 'Submit Manual Order' },
  'qt.disabled':              { zh: '后端尚未提供 POST /orders，待 Phase 3 启用。', en: 'POST /orders not yet exposed.' },

  'sig.subheader':            { zh: '智能体推理', en: 'Agent Reasoning' },
  'sig.caption':              { zh: '查看每个智能体的完整推理 — 分析师、研究员、风险辩手以及组合经理。', en: 'Inspect the full reasoning of every agent.' },

  'auth.app.title':           { zh: 'TradingAgents 登录', en: 'TradingAgents Sign-in' },
  'auth.login':               { zh: '登录', en: 'Sign in' },
  'auth.register':            { zh: '注册', en: 'Register' },
  'auth.username':            { zh: '用户名', en: 'Username' },
  'auth.password':            { zh: '密码', en: 'Password' },
  'auth.go_register':         { zh: '没有账号？去注册', en: 'No account? Register' },
  'auth.go_login':            { zh: '已有账号？去登录', en: 'Have an account? Sign in' },
  'auth.subtitle.login':      { zh: '登录到分析控制台', en: 'Sign in to the analysis console' },
  'auth.subtitle.register':   { zh: '注册新账号（首位用户自动为 admin）', en: 'Register (first user becomes admin)' },

  'common.loading':           { zh: '加载中…', en: 'Loading…' },
  'common.empty':             { zh: '暂无数据。', en: 'No data.' },
  'common.cancel':            { zh: '取消', en: 'Cancel' },
  'common.save':              { zh: '保存', en: 'Save' },
  'common.saved':             { zh: '已保存', en: 'Saved' },
  'common.submit':            { zh: '提交', en: 'Submit' },
};

let lang: Lang = (localStorage.getItem('lang') as Lang) || 'zh';

export function setLang(l: Lang) {
  lang = l;
  localStorage.setItem('lang', l);
  // simple reload to re-render — keeps t() pure
  location.reload();
}
export function getLang(): Lang { return lang; }

export function t(key: string, vars?: Record<string, string | number>): string {
  const row = DICT[key];
  let s = row ? row[lang] : key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
  return s;
}
