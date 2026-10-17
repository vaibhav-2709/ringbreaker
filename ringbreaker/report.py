"""Render a self-contained HTML case report (no external assets). Run: python3 -m ringbreaker.report"""
import html
import json

from .agent import Investigator
from .graph import connect, load

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RingBreaker Case Report</title>
<style>
:root{--bg:#f7f6f2;--card:#fff;--ink:#1c1b19;--mut:#6b6860;--line:#e3e0d8;--freeze:#c0392b;--clear:#2e7d52;--esc:#b9770e;--acct:#2b5fa8;--ident:#8e6bbf;--money:#c0392b}
@media(prefers-color-scheme:dark){:root{--bg:#161614;--card:#1f1f1c;--ink:#ecebe6;--mut:#9a978e;--line:#33322d;--freeze:#ff6b5b;--clear:#5fc08a;--esc:#e8a33d;--acct:#6ea3ec;--ident:#b394e0;--money:#ff6b5b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:20px 16px 60px}
main{max-width:980px;margin:0 auto}h1{font-size:26px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 20px}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:120px}
.stat b{display:block;font-size:22px}.stat span{color:var(--mut);font-size:12px}
.case{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:18px}
.head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.head h2{margin:0;font-size:18px}
.badge{font-size:12px;font-weight:700;padding:3px 9px;border-radius:99px;color:#fff}.FREEZE{background:var(--freeze)}.CLEAR{background:var(--clear)}.ESCALATE{background:var(--esc)}
.grid{display:grid;grid-template-columns:1fr;gap:16px;margin-top:12px}@media(min-width:820px){.grid.two{grid-template-columns:1.1fr 1fr}}
svg{width:100%;height:auto;background:transparent;border:1px solid var(--line);border-radius:10px}
.sig{border-left:3px solid var(--freeze);padding:4px 0 4px 10px;margin:0 0 10px}.sig b{display:inline-block;min-width:34px}
.path{font:12px ui-monospace,monospace;color:var(--mut);word-break:break-all}
.trace{font-size:13px;color:var(--mut);margin-top:8px}.trace li{margin:2px 0}.trace code{color:var(--ink)}
.legend{display:flex;gap:14px;font-size:12px;color:var(--mut);margin-top:6px;flex-wrap:wrap}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
text{fill:var(--ink);font:10px system-ui}
</style></head><body><main>
<h1>RingBreaker case report</h1><p class="sub">Graph-driven fraud investigation on FalkorDB. Every decision below carries the graph path behind it.</p>
<div class="stats" id="stats"></div><div id="cases"></div></main>
<script>
const DATA=__DATA__;
const el=(t,a={},h='')=>{const e=document.createElement(t);for(const k in a)e.setAttribute(k,a[k]);e.innerHTML=h;return e};
const ns=(t,a={})=>{const e=document.createElementNS('http://www.w3.org/2000/svg',t);for(const k in a)e.setAttribute(k,a[k]);return e};
const S=DATA.summary;
document.getElementById('stats').innerHTML=[['Accounts',S.accounts],['Clusters reviewed',S.clusters],['Frozen',S.frozen],['Cleared',S.cleared],['Victims to notify',S.victims]]
 .map(([k,v])=>`<div class="stat"><b>${v}</b><span>${k}</span></div>`).join('');
function draw(c){
  const W=520,H=400,cx=W/2,cy=H/2,svg=ns('svg',{viewBox:`0 0 ${W} ${H}`,role:'img','aria-label':'Graph of accounts, shared devices and addresses, and money flow'});
  const defs=ns('defs');defs.innerHTML='<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0L10,5L0,10z" fill="var(--money)"/></marker>';svg.appendChild(defs);
  const n=c.graph.accounts.length,pos={};
  c.graph.accounts.forEach((a,i)=>{const t=2*Math.PI*i/n-Math.PI/2,r=Math.min(150,60+n*10);pos[a]=[cx+r*Math.cos(t),cy+r*Math.sin(t)]});
  const ni=c.graph.ident.length;
  c.graph.ident.forEach((x,i)=>{if(ni===1){pos[x.id]=[cx,cy];return}const t=2*Math.PI*i/ni-Math.PI/2,r=ni>3?58:40;pos[x.id]=[cx+r*Math.cos(t),cy+r*Math.sin(t)]});
  c.graph.ident.forEach(x=>x.accounts.forEach(a=>{if(pos[a])svg.appendChild(ns('line',{x1:pos[x.id][0],y1:pos[x.id][1],x2:pos[a][0],y2:pos[a][1],stroke:'var(--ident)','stroke-width':1,'stroke-dasharray':'3 3',opacity:.7}))}));
  c.graph.money.forEach(m=>{if(!pos[m.s]||!pos[m.d])return;const [x1,y1]=pos[m.s],[x2,y2]=pos[m.d];const dx=x2-x1,dy=y2-y1,L=Math.hypot(dx,dy)||1,ux=dx/L,uy=dy/L;
    svg.appendChild(ns('path',{d:`M${x1+ux*11},${y1+uy*11} Q${(x1+x2)/2-uy*18},${(y1+y2)/2+ux*18} ${x2-ux*13},${y2-uy*13}`,fill:'none',stroke:'var(--money)','stroke-width':1.4,'marker-end':'url(#ar)',opacity:.85}))});
  c.graph.ident.forEach(x=>{const [px,py]=pos[x.id];svg.appendChild(ns('rect',{x:px-6,y:py-6,width:12,height:12,rx:2,fill:'var(--ident)'}));const t=ns('text',{x:px+9,y:py+3});t.textContent=x.id.replace('DEV','D').replace('ADDR','A');svg.appendChild(t)});
  c.graph.accounts.forEach(a=>{const [px,py]=pos[a];svg.appendChild(ns('circle',{cx:px,cy:py,r:9,fill:c.hub===a?'var(--freeze)':'var(--acct)',stroke:'var(--card)','stroke-width':2}));const t=ns('text',{x:px-17,y:py<cy?py-14:py+22});t.textContent=a.replace('ACCT','#');svg.appendChild(t)});
  return svg}
const root=document.getElementById('cases');
DATA.cases.forEach(c=>{
  const d=el('section',{class:'case'});
  d.appendChild(el('div',{class:'head'},`<h2>${c.case_id}</h2><span class="badge ${c.verdict}">${c.verdict}</span><span style="color:var(--mut)">score ${c.score} · ${c.accounts.length} accounts${c.victims.length?` · ${c.victims.length} victims`:''}</span>`));
  const g=el('div',{class:'grid'+(c.verdict==='CLEAR'?'':' two')});
  if(c.verdict!=='CLEAR'){const w=el('div');w.appendChild(draw(c));w.appendChild(el('div',{class:'legend'},'<span><i class="dot" style="background:var(--acct)"></i>account</span><span><i class="dot" style="background:var(--freeze)"></i>collector hub</span><span><i class="dot" style="background:var(--ident);border-radius:2px"></i>shared device / address</span><span>red arrows = money</span>'));g.appendChild(w)}
  const r=el('div');
  r.innerHTML=c.signals.length?c.signals.map(s=>`<div class="sig"><b>+${s.points}</b> ${s.name.replace(/_/g,' ')}: ${s.why}${s.evidence.slice(0,2).map(e=>`<div class="path">${e}</div>`).join('')}</div>`).join(''):'<p>No risk signals. Mature, verified accounts that share a home or device: normal household behaviour. The agent stopped after two tool calls.</p>';
  r.appendChild(el('ol',{class:'trace'},c.trace.map(t=>`<li><code>${t.tool}</code>: ${t.why}</li>`).join('')));
  g.appendChild(r);d.appendChild(g);root.appendChild(d)});
</script></body></html>"""


def build(g, cases):
    out = []
    n_accounts = g.query("MATCH (a:Account) RETURN count(a)").result_set[0][0]
    for c in cases:
        ids = c.accounts
        ident = []
        for rel, label in (("USES", "Device"), ("LIVES_AT", "Address")):
            rows = g.query(
                f"MATCH (a:Account)<-[:OWNS]-(:Customer)-[:{rel}]->(x:{label}) WHERE a.id IN $ids "
                "RETURN x.id, collect(DISTINCT a.id)", {"ids": ids}).result_set
            ident += [{"id": x, "accounts": a} for x, a in rows if len(a) >= 2]
        money = [{"s": s, "d": d} for s, d in g.query(
            "MATCH (a:Account)-[:SENT]->(b:Account) WHERE a.id IN $ids AND b.id IN $ids RETURN DISTINCT a.id, b.id", {"ids": ids}).result_set]
        d = c.to_dict()
        d["graph"] = {"accounts": ids, "ident": ident, "money": money}
        out.append(d)
    frozen = sum(1 for c in cases if c.verdict == "FREEZE")
    summary = {"accounts": n_accounts, "clusters": len(cases), "frozen": frozen, "cleared": sum(1 for c in cases if c.verdict == "CLEAR"),
               "victims": sum(len(c.victims) for c in cases)}
    return {"summary": summary, "cases": out}


def main(path="report.html"):
    g = connect()
    load(g)
    cases = Investigator(g).sweep()
    data = build(g, cases)
    open(path, "w").write(PAGE.replace("__DATA__", json.dumps(data)))
    print("wrote", path, data["summary"])


if __name__ == "__main__":
    main()
