
const SYMS = ["ABB", "APLAPOLLO", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS", "ADANIPOWER", "ATGL", "AMBUJACEM", "APARINDS", "APOLLOHOSP", "ASHOKLEY", "ASIANPAINT", "ASTRAL", "AUROPHARMA", "DMART", "BAJAJ-AUTO", "BDL", "BEL", "BHARATFORG", "BHEL", "BPCL", "BHARTIARTL", "BIOCON", "BLUESTARCO", "BOSCHLTD", "BRITANNIA", "CGPOWER", "CIPLA", "COALINDIA", "COCHINSHIP", "COFORGE", "COLPAL", "CONCOR", "CUMMINSIND", "DLF", "DABUR", "DIVISLAB", "DIXON", "DRREDDY", "EICHERMOT", "ETERNAL", "EXIDEIND", "NYKAA", "FORTIS", "GAIL", "GVT&D", "GMRAIRPORT", "GLENMARK", "GODFRYPHLP", "GODREJCP", "GODREJPROP", "GRASIM", "HCLTECH", "HAVELLS", "HEROMOTOCO", "HINDALCO", "HAL", "HINDCOPPER", "HINDPETRO", "HINDUNILVR", "HINDZINC", "POWERINDIA", "HYUNDAI", "ITC", "INDHOTEL", "IOC", "IRCTC", "INDUSTOWER", "NAUKRI", "INFY", "INDIGO", "JSWENERGY", "JSWSTEEL", "JINDALSTEL", "JUBLFOOD", "KEI", "KALYANKJIL", "LGEINDIA", "LTM", "LT", "LAURUSLABS", "LENSKART", "LODHA", "LUPIN", "MRF", "M&M", "MANKIND", "MARICO", "MARUTI", "MAXHEALTH", "MAZDOCK", "MEESHO", "MPHASIS", "NHPC", "NLCINDIA", "NMDC", "NTPC", "NATIONALUM", "NESTLEIND", "OBEROIRLTY", "ONGC", "OIL", "OFSS", "PIIND", "PAGEIND", "PATANJALI", "PERSISTENT", "PHOENIXLTD", "PIDILITIND", "POLYCAB", "POWERGRID", "PREMIERENE", "PRESTIGE", "RADICO", "RVNL", "RELIANCE", "SRF", "MOTHERSON", "ENRIN", "SIEMENS", "SOLARINDS", "SAIL", "SUNPHARMA", "SUPREMEIND", "SUZLON", "SWIGGY", "TVSMOTOR", "TATACOMM", "TCS", "TATACONSUM", "TMCV", "TMPV", "TATAPOWER", "TATASTEEL", "TECHM", "TITAN", "TORNTPHARM", "TRENT", "TIINDIA", "UPL", "ULTRACEMCO", "UNITDSPR", "VBL", "VAML", "VEDL", "VMM", "IDEA", "VOLTAS", "WAAREEENER", "WIPRO", "ZYDUSLIFE", "COFFEEDAY", "ZEEL", "RCOM", "JETAIRWAYS", "SUNTV"]; const SCHED = [["Cash from Operating Activity", "cash-flow"], ["Cash from Investing Activity", "cash-flow"], ["Cash from Financing Activity", "cash-flow"], ["Borrowings", "balance-sheet"], ["Other Liabilities", "balance-sheet"], ["Other Assets", "balance-sheet"], ["Trade receivables", "balance-sheet"], ["Other Income", "profit-loss"], ["Net Profit", "profit-loss"], ["Other Income", "quarters"]]; const B = 'https://www.screener.in';
const DB = 'dstm_capture_v1';
const sleep = ms => new Promise(r => setTimeout(r, ms));
function idb(){ return new Promise((res,rej)=>{ const q=indexedDB.open(DB,1); q.onupgradeneeded=()=>{q.result.createObjectStore('items'); q.result.createObjectStore('done');}; q.onsuccess=()=>res(q.result); q.onerror=()=>rej(q.error);}); }
function put(db,store,k,v){ return new Promise((res,rej)=>{ const t=db.transaction(store,'readwrite'); t.objectStore(store).put(v,k); t.oncomplete=res; t.onerror=()=>rej(t.error);}); }
function has(db,store,k){ return new Promise((res)=>{ const t=db.transaction(store); const g=t.objectStore(store).get(k); g.onsuccess=()=>res(g.result!==undefined); g.onerror=()=>res(false);}); }
let db, n=0;
async function get(path){ const t0=new Date().toISOString(); let st=0, body='', ct='';
  for (let a=1; a<=4; a++){ try{ const r=await fetch(B+path,{credentials:'omit'}); st=r.status; ct=r.headers.get('content-type')||''; body=await r.text(); }catch(e){ st=0; body=''; }
    await sleep(1100); if (st===200 || [400,401,403,404,410].includes(st)) break; await sleep(2000*Math.pow(2,a-1)); }
  await put(db,'items',B+path,{status:st,content_type:ct,fetched_at:t0,body: st===200?body:''}); n++; postMessage({type:'progress',n}); return {st,body}; }
function eom(y,m){ return new Date(Date.UTC(y,m,0)).toISOString().slice(0,10); }
const MON={Jan:1,Feb:2,Mar:3,Apr:4,May:5,Jun:6,Jul:7,Aug:8,Sep:9,Oct:10,Nov:11,Dec:12};
function plHeads(html){ const i=html.indexOf('id="profit-loss"'); if(i<0) return []; const s=html.indexOf('<thead',i), e=html.indexOf('</thead>',s); if(s<0||e<0) return [];
  const out=[]; const re=/<th([^>]*)>([\s\S]*?)<\/th>/g; let m; const th=html.slice(s,e);
  while((m=re.exec(th))){ const txt=m[2].replace(/<[^>]+>/g,' ').replace(/\s+/g,' ').trim(); if(!txt||txt==='TTM') continue;
    const k=(m[1].match(/data-date-key="(\d{4}-\d{2}-\d{2})"/)||[])[1]; const mm=txt.match(/^([A-Z][a-z]{2}) (\d{4})/); if(!mm||!MON[mm[1]]) continue;
    out.push({end: k||eom(+mm[2],MON[mm[1]]), own: !/\(S\)/.test(txt)}); } return out; }
function latest(h,ownOnly){ const d=h.filter(x=>!ownOnly||x.own).map(x=>x.end).sort(); return d.length?d[d.length-1]:null; }
onmessage = async (ev) => { db = await idb(); const cutoff=new Date(Date.now()-732*864e5).toISOString().slice(0,10);
  for (const sym of SYMS){ if (await has(db,'done',sym)) continue; const es=encodeURIComponent(sym);
    const c=await get(`/company/${es}/consolidated/`); let cons=c.st===200?c.body:null, stand=null, basis=null;
    const ch=cons?plHeads(cons):[]; const cOwn=latest(ch,true);
    let needStand = !cons || !cOwn || cOwn < cutoff;
    if (!needStand) basis='consolidated';
    else { const s=await get(`/company/${es}/`); stand=s.st===200?s.body:null; const sh=stand?plHeads(stand):[]; const sOwn=latest(sh,true), sAll=latest(sh,false);
      if (!cOwn && !sOwn) basis=null; else if (!cOwn) basis='standalone';
      else if (sOwn){ basis = cOwn < sAll ? 'standalone' : 'consolidated'; } else basis = cOwn < cutoff ? 'standalone':'consolidated'; }
    const src = (basis==='consolidated'?cons:stand) || cons || stand; const cid = src && (src.match(/data-company-id="(\d+)"/)||[])[1];
    if (cid && basis){ for (const [p,sec] of SCHED) await get(`/api/company/${cid}/schedules/?parent=${encodeURIComponent(p)}&section=${sec}${basis==='consolidated'?'&consolidated=':''}`);
      await get(`/api/company/${cid}/chart/?q=Price&days=10000`); }
    await put(db,'done',sym,{basis,cid,at:new Date().toISOString()}); postMessage({type:'done',sym,basis}); }
  postMessage({type:'finished',n}); };
