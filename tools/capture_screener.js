// Browser capture for offline testing / environments where Python cannot reach screener.in.
// Paste into the DevTools console on any https://www.screener.in page (no login needed).
// It requests the same URLs the Python pipeline requests (1.1 s apart) and downloads one JSON file
// that `python -m dstm_data refresh --replay <file> --symbols ...` replays through the unchanged pipeline.
(async () => {
  const SYMS = ['TATASTEEL', 'IDEA', 'INDIGO', 'LT', 'DLF', 'ADANIENT', 'TCS', 'GVT&D', 'TMCV', 'COLPAL'];
  const SCHED = [['Cash from Operating Activity', 'cash-flow'], ['Cash from Investing Activity', 'cash-flow'],
    ['Cash from Financing Activity', 'cash-flow'], ['Borrowings', 'balance-sheet'], ['Other Liabilities', 'balance-sheet'],
    ['Other Assets', 'balance-sheet'], ['Trade receivables', 'balance-sheet'], ['Other Income', 'profit-loss'],
    ['Net Profit', 'profit-loss'], ['Other Income', 'quarters']];
  // A hidden tab throttles timers; MessageChannel keeps the 1.1 s spacing honest.
  const sleep = (ms) => new Promise(res => { const end = performance.now() + ms; if (!document.hidden) { setTimeout(res, ms); return; }
    const ch = new MessageChannel(); ch.port1.onmessage = () => performance.now() >= end ? res() : ch.port2.postMessage(0); ch.port2.postMessage(0); });
  const cap = { meta: { started: new Date().toISOString(), ua: navigator.userAgent, errors: [] }, items: {} };
  const get = async (path) => {
    const t0 = new Date().toISOString(); let st = 0, body = '', ct = '';
    try { const r = await fetch(path, { credentials: 'omit' }); st = r.status; ct = r.headers.get('content-type') || ''; body = await r.text(); }
    catch (e) { cap.meta.errors.push(path + ' ' + e); }
    cap.items['https://www.screener.in' + path] = { status: st, content_type: ct, fetched_at: t0, body };
    await sleep(1100); return { st, body };
  };
  for (const sym of SYMS) {
    const es = encodeURIComponent(sym);
    const c = await get(`/company/${es}/consolidated/`);
    const s = await get(`/company/${es}/`);
    const m = (c.st === 200 ? c.body : s.body).match(/data-company-id="(\d+)"/);
    if (!m) { cap.meta.errors.push('no company id ' + sym); continue; }
    for (const flag of ['&consolidated=', '']) // consolidated is presence-based: omit it for standalone
      for (const [p, sec] of SCHED) await get(`/api/company/${m[1]}/schedules/?parent=${encodeURIComponent(p)}&section=${sec}${flag}`);
    console.log('captured', sym);
  }
  cap.meta.finished = new Date().toISOString();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(cap)], { type: 'application/json' }));
  a.download = 'dstm_capture.json'; document.body.appendChild(a); a.click();
})();
