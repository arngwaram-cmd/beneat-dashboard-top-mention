"""
BeNeat Mention Dashboard — Auto Generator
ดึงข้อมูล mention จาก Slack แล้ว generate index.html ใหม่ทุกครั้งที่รัน
"""
import os, re, json, requests
from datetime import datetime, timedelta, timezone

SLACK_TOKEN = os.environ["SLACK_TOKEN"]
HOOD_ID     = "U03E71FCC4F"
PUM_ID      = "U05MWPH3136"
TZ_OFFSET   = timezone(timedelta(hours=7))   # Asia/Bangkok

def slack_search(query, pages=4):
    """ดึง messages จาก Slack Search API"""
    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    results = []
    cursor  = None
    for _ in range(pages):
        params = {"query": query, "sort": "timestamp", "sort_dir": "desc", "count": 20}
        if cursor:
            params["cursor"] = cursor
        r = requests.get("https://slack.com/api/search.messages", headers=headers, params=params)
        data = r.json()
        if not data.get("ok"):
            break
        msgs = data.get("messages", {}).get("matches", [])
        if not msgs:
            break
        results.extend(msgs)
        cursor = data.get("messages", {}).get("pagination", {}).get("next_cursor")
        if not cursor:
            break
    return results

def parse_mentions(text):
    """Extract @mentioned names from Slack message text"""
    pattern = r'<@[A-Z0-9]+\|([^>]+)>'
    return list(dict.fromkeys(re.findall(pattern, text)))  # dedupe, preserve order

def classify_topic(text, channel):
    """Classify message into topic bucket"""
    text_lower = (text + " " + channel).lower()
    if any(k in text_lower for k in ["btaskee", "บ้าน", "แม่บ้าน", "ลูกค้า", "รับงาน", "capacity", "booking", "sprint"]):
        return "Operations / BTaskee"
    if any(k in text_lower for k in ["notion", "calendar", "save", "บันทึก", "page", "knowledge"]):
        return "Notion / Knowledge"
    if any(k in text_lower for k in ["ai", "claude", "prompt", "gpt", "model", "agent", "llm", "it", "dev", "code"]):
        return "AI / Technology"
    if any(k in text_lower for k in ["marketing", "market", "สื่อ", "โฆษณา", "content", "tiktok", "facebook"]):
        return "Marketing"
    if any(k in text_lower for k in ["iso", "qa", "quality", "qc", "มาตรฐาน"]):
        return "ISO / Quality"
    if any(k in text_lower for k in ["อนุมัติ", "approval", "file", "submit", "จัดซื้อ", "purchase"]):
        return "Approval / Admin"
    return "Other"

def approx_date(idx, total, page, today):
    """Assign approximate date based on page and position"""
    buckets = [
        (0, 7),    # page 0: last 7 days
        (8, 30),   # page 1: 8-30 days
        (31, 90),  # page 2: 31-90 days
        (91, 180), # page 3: 91-180 days
    ]
    lo, hi = buckets[min(page, 3)]
    step = max(1, (hi - lo) // max(total, 1))
    days_ago = lo + idx * step
    d = today - timedelta(days=days_ago)
    return d.strftime("%Y-%m-%d")

def fetch_mentions(user_id, sender_name, today):
    cutoff = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    msgs = slack_search(f"from:<@{user_id}> after:{cutoff}")
    events = []
    for i, msg in enumerate(msgs):
        text    = msg.get("text", "")
        channel = msg.get("channel", {}).get("name", "unknown")
        mentioned = parse_mentions(text)
        # skip DMs and messages with no user mentions
        if "im" in msg.get("channel", {}).get("type", "") or not mentioned:
            continue
        # figure out which page this result is from
        page = i // 20
        pos_in_page = i % 20
        date = approx_date(pos_in_page, 20, page, today)
        events.append({
            "date":      date,
            "sender":    sender_name,
            "mentioned": mentioned,
            "channel":   channel,
            "topic":     classify_topic(text, channel),
            "preview":   text[:100].replace("\n", " "),
        })
    return events

def build_html(raw_data, refreshed_at):
    """Build complete HTML dashboard with embedded data"""
    raw_json = json.dumps(raw_data, ensure_ascii=False, indent=2)

    return f"""<!DOCTYPE html>
<html lang="th">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BeNeat — Mention Dashboard</title>
<style>
  :root {{
    --cyan:#31c1d7; --light-blue:#7ae6f0; --taupe:#a69586;
    --orange:#f2ac57; --gold:#dfae69; --bg:#f7f9fc;
    --card:#ffffff; --text:#1a2233; --muted:#6b7a99; --border:#e4eaf5;
    --hood:#31c1d7; --pum:#f2ac57;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}}
  .header{{background:linear-gradient(135deg,#1a2233,#2a3a55);padding:24px 32px;display:flex;align-items:center;justify-content:space-between}}
  .header h1{{color:#fff;font-size:22px;font-weight:700}} .header h1 span{{color:var(--cyan)}}
  .header .subtitle{{color:#8fa3c8;font-size:13px;margin-top:4px}}
  .badge{{background:rgba(49,193,215,.18);color:var(--light-blue);border-radius:20px;padding:4px 14px;font-size:12px;font-weight:600}}
  .filter-bar{{background:var(--card);border-bottom:1px solid var(--border);padding:0 32px;display:flex;align-items:center;gap:0;overflow-x:auto}}
  .filter-btn{{padding:14px 20px;font-size:13px;font-weight:600;color:var(--muted);background:none;border:none;border-bottom:3px solid transparent;cursor:pointer;white-space:nowrap;transition:all .15s}}
  .filter-btn:hover{{color:var(--text)}} .filter-btn.active{{color:var(--cyan);border-bottom-color:var(--cyan)}}
  .filter-sep{{width:1px;height:20px;background:var(--border);margin:0 8px;flex-shrink:0}}
  #customSection{{display:none;align-items:center;gap:8px;padding:6px 16px;background:#f0fafd;border-radius:8px;margin:4px 0 4px 8px}}
  #customSection.visible{{display:flex}}
  .custom-range input[type="date"]{{border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:12px;color:var(--text);background:var(--bg);cursor:pointer}}
  .custom-range label{{font-size:12px;color:var(--muted)}}
  .main{{padding:28px 32px;max-width:1400px}}
  .stats-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:24px}}
  .stat-card{{background:var(--card);border-radius:12px;padding:20px 24px;border:1px solid var(--border)}}
  .stat-card .label{{font-size:12px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px}}
  .stat-card .value{{font-size:32px;font-weight:800;color:var(--text);line-height:1}}
  .stat-card .sub{{font-size:12px;color:var(--muted);margin-top:6px}}
  .stat-card.hood .value{{color:var(--hood)}} .stat-card.pum .value{{color:var(--pum)}}
  .grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}}
  .card{{background:var(--card);border-radius:12px;border:1px solid var(--border);padding:24px}}
  .card-title{{font-size:14px;font-weight:700;color:var(--text);margin-bottom:18px;display:flex;align-items:center;gap:8px}}
  .dot{{width:10px;height:10px;border-radius:50%}} .dot-hood{{background:var(--hood)}} .dot-pum{{background:var(--pum)}} .dot-both{{background:linear-gradient(135deg,var(--hood),var(--pum))}}
  .bar-item{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
  .bar-name{{font-size:13px;color:var(--text);min-width:160px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}}
  .bar-track{{flex:1;height:24px;background:var(--bg);border-radius:6px;overflow:hidden}}
  .bar-fill{{height:100%;border-radius:6px;transition:width .5s ease;display:flex;align-items:center;padding-left:8px}}
  .bar-fill.hood{{background:linear-gradient(90deg,var(--hood),var(--light-blue))}}
  .bar-fill.pum{{background:linear-gradient(90deg,var(--pum),var(--gold))}}
  .bar-fill.both{{background:linear-gradient(90deg,var(--hood),var(--pum))}}
  .bar-count{{font-size:12px;font-weight:700;color:var(--text);min-width:28px;text-align:right}}
  .channel-list{{display:flex;flex-direction:column;gap:8px}}
  .channel-item{{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;border-radius:8px;background:var(--bg)}}
  .channel-name{{font-size:12px;color:var(--text);font-weight:500}}
  .channel-counts{{display:flex;gap:6px}}
  .chip{{padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700}}
  .chip-hood{{background:rgba(49,193,215,.15);color:#1a8fa0}} .chip-pum{{background:rgba(242,172,87,.2);color:#b5722a}}
  .timeline{{display:flex;flex-direction:column;gap:0;position:relative}}
  .timeline::before{{content:'';position:absolute;left:20px;top:0;bottom:0;width:2px;background:var(--border)}}
  .tl-item{{display:flex;gap:16px;padding:10px 0;position:relative}}
  .tl-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0;margin-top:5px;margin-left:16px;z-index:1;border:2px solid #fff}}
  .tl-dot.hood{{background:var(--hood);box-shadow:0 0 0 2px rgba(49,193,215,.3)}}
  .tl-dot.pum{{background:var(--pum);box-shadow:0 0 0 2px rgba(242,172,87,.3)}}
  .tl-content{{flex:1}}
  .tl-meta{{font-size:11px;color:var(--muted);margin-bottom:2px}}
  .tl-text{{font-size:12px;color:var(--muted);line-height:1.4}}
  .tl-mentions{{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}}
  .mention-tag{{background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:2px 8px;font-size:11px;color:var(--muted)}}
  .tl-channel{{font-size:11px;color:var(--cyan);background:rgba(49,193,215,.08);padding:1px 7px;border-radius:10px;display:inline-block;margin-left:4px}}
  .table-wrap{{overflow-x:auto}}
  table{{width:100%;border-collapse:collapse}}
  th{{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);font-weight:700;padding:8px 12px;border-bottom:2px solid var(--border);text-align:left}}
  td{{font-size:13px;padding:10px 12px;border-bottom:1px solid var(--border);color:var(--text);vertical-align:top}}
  tr:last-child td{{border-bottom:none}} tr:hover td{{background:#f7fcfe}}
  .sender-badge{{padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700}}
  .sender-hood{{background:rgba(49,193,215,.15);color:#1a8fa0}} .sender-pum{{background:rgba(242,172,87,.2);color:#b5722a}}
  .topic-tag{{background:#f0f4ff;color:#4a5a8a;border-radius:10px;padding:2px 8px;font-size:11px}}
  .no-data{{text-align:center;padding:32px;color:var(--muted);font-size:14px}}
  .footer{{text-align:center;color:var(--muted);font-size:11px;padding:24px;border-top:1px solid var(--border);margin-top:8px}}
  .refresh-info{{background:rgba(49,193,215,.08);border:1px solid rgba(49,193,215,.2);border-radius:8px;padding:6px 14px;font-size:12px;color:var(--cyan);display:inline-block;margin-bottom:16px}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>BeNeat <span>Mention Dashboard</span></h1>
    <div class="subtitle">ติดตามการ mention จาก Hood &amp; Pum ใน Slack · อัปเดตอัตโนมัติ 09:00 &amp; 15:00</div>
  </div>
  <span class="badge" id="badgeRange">Last 7 Days</span>
</div>
<div class="filter-bar">
  <button class="filter-btn" onclick="setFilter('today')">Today</button>
  <button class="filter-btn active" onclick="setFilter('7d')">Last 7 Days</button>
  <button class="filter-btn" onclick="setFilter('30d')">Last Month</button>
  <button class="filter-btn" onclick="setFilter('90d')">Last 3 Months</button>
  <button class="filter-btn" onclick="setFilter('180d')">Last 6 Months</button>
  <div class="filter-sep"></div>
  <button class="filter-btn" onclick="toggleCustom()">Custom Range</button>
  <div id="customSection" class="custom-range">
    <label>From</label><input type="date" id="customFrom" onchange="applyCustom()">
    <label>To</label><input type="date" id="customTo" onchange="applyCustom()">
  </div>
</div>
<div class="main">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
    <span class="refresh-info">🔄 ข้อมูล ณ {refreshed_at}</span>
  </div>
  <div class="stats-row">
    <div class="stat-card"><div class="label">Total Mentions</div><div class="value" id="statTotal">—</div><div class="sub">in selected period</div></div>
    <div class="stat-card hood"><div class="label">Hood's Mentions</div><div class="value" id="statHood">—</div><div class="sub" id="subHood">—</div></div>
    <div class="stat-card pum"><div class="label">Pum's Mentions</div><div class="value" id="statPum">—</div><div class="sub" id="subPum">—</div></div>
    <div class="stat-card"><div class="label">Most Mentioned</div><div class="value" style="font-size:18px;line-height:1.3" id="statTop">—</div><div class="sub" id="statTopSub">—</div></div>
  </div>
  <div class="grid-2">
    <div class="card"><div class="card-title"><span class="dot dot-hood"></span>Hood's Top Mentions</div><div id="hoodBars"></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-pum"></span>Pum's Top Mentions</div><div id="pumBars"></div></div>
  </div>
  <div class="grid-2">
    <div class="card"><div class="card-title"><span class="dot dot-both"></span>Channel Breakdown</div><div class="channel-list" id="channelList"></div></div>
    <div class="card"><div class="card-title"><span class="dot dot-both"></span>หัวข้อที่ mention บ่อย</div><div id="topicBars"></div></div>
  </div>
  <div class="card" style="margin-bottom:24px">
    <div class="card-title"><span class="dot dot-both"></span>Timeline ล่าสุด</div>
    <div class="timeline" id="timeline"></div>
  </div>
  <div class="card">
    <div class="card-title"><span class="dot dot-both"></span>รายการ Mentions ทั้งหมด</div>
    <div class="table-wrap">
      <table><thead><tr><th>Date</th><th>Sender</th><th>Mentioned</th><th>Channel</th><th>Topic</th><th>Preview</th></tr></thead>
      <tbody id="tableBody"></tbody></table>
    </div>
  </div>
</div>
<div class="footer">BeNeat Mention Dashboard · อัปเดตอัตโนมัติทุกวัน 09:00 &amp; 15:00 · Refreshed: {refreshed_at}</div>
<script>
const RAW = {raw_json};
const TODAY = new Date('{today_str}');
let currentFilter='7d', customFrom=null, customTo=null;
function dateOf(s){{return new Date(s)}}
function inRange(ds){{
  const d=dateOf(ds);
  if(currentFilter==='today'){{const f=new Date(TODAY);f.setHours(0,0,0,0);return d>=f&&d<=TODAY}}
  const days={{today:0,'7d':6,'30d':29,'90d':89,'180d':179}};
  if(days[currentFilter]!==undefined){{const f=new Date(TODAY);f.setDate(f.getDate()-days[currentFilter]);return d>=f&&d<=TODAY}}
  if(currentFilter==='custom'&&customFrom&&customTo)return d>=customFrom&&d<=customTo;
  return true;
}}
function getFiltered(){{return RAW.filter(r=>inRange(r.date))}}
function renderAll(){{const d=getFiltered();renderStats(d);renderBars(d);renderChannels(d);renderTopics(d);renderTimeline(d);renderTable(d)}}
function renderStats(data){{
  const hd=data.filter(d=>d.sender==='Hood'),pd=data.filter(d=>d.sender==='Pum');
  const tot=data.reduce((s,r)=>s+r.mentioned.length,0);
  const counts={{}};data.forEach(r=>r.mentioned.forEach(m=>counts[m]=(counts[m]||0)+1));
  const sorted=Object.entries(counts).sort((a,b)=>b[1]-a[1]);
  document.getElementById('statTotal').textContent=tot;
  document.getElementById('statHood').textContent=hd.reduce((s,r)=>s+r.mentioned.length,0);
  document.getElementById('subHood').textContent=`จาก ${{hd.length}} ข้อความ`;
  document.getElementById('statPum').textContent=pd.reduce((s,r)=>s+r.mentioned.length,0);
  document.getElementById('subPum').textContent=`จาก ${{pd.length}} ข้อความ`;
  if(sorted.length){{document.getElementById('statTop').textContent=sorted[0][0].replace(/\s*\(.*\)/,'');document.getElementById('statTopSub').textContent=`${{sorted[0][1]}} ครั้งใน period นี้`}}
  else{{document.getElementById('statTop').textContent='—';document.getElementById('statTopSub').textContent='ไม่มีข้อมูล'}}
}}
function buildBars(subset,id,cls){{
  const counts={{}};subset.forEach(r=>r.mentioned.forEach(m=>counts[m]=(counts[m]||0)+1));
  const sorted=Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8);
  const max=sorted[0]?.[1]||1,el=document.getElementById(id);
  if(!sorted.length){{el.innerHTML='<div class="no-data">ไม่มีข้อมูลใน period นี้</div>';return}}
  el.innerHTML=sorted.map(([n,c])=>`<div class="bar-item"><div class="bar-name" title="${{n}}">${{n.replace(/\s*\(.*?\)/,'')}}</div><div class="bar-track"><div class="bar-fill ${{cls}}" style="width:${{Math.round(c/max*100)}}%"><span style="font-size:11px;color:#fff;font-weight:700">${{c>1?c:''}}</span></div></div><div class="bar-count">${{c}}</div></div>`).join('');
}}
function renderBars(data){{buildBars(data.filter(d=>d.sender==='Hood'),'hoodBars','hood');buildBars(data.filter(d=>d.sender==='Pum'),'pumBars','pum')}}
function renderChannels(data){{
  const hC={{}},pC={{}};
  data.filter(d=>d.sender==='Hood').forEach(r=>hC[r.channel]=(hC[r.channel]||0)+r.mentioned.length);
  data.filter(d=>d.sender==='Pum').forEach(r=>pC[r.channel]=(pC[r.channel]||0)+r.mentioned.length);
  const all=new Set([...Object.keys(hC),...Object.keys(pC)]);
  const sorted=[...all].sort((a,b)=>((hC[b]||0)+(pC[b]||0))-((hC[a]||0)+(pC[a]||0))).slice(0,8);
  const el=document.getElementById('channelList');
  if(!sorted.length){{el.innerHTML='<div class="no-data">ไม่มีข้อมูล</div>';return}}
  el.innerHTML=sorted.map(ch=>`<div class="channel-item"><div class="channel-name">#${{ch.replace(/_/g,' ')}}</div><div class="channel-counts">${{hC[ch]?`<span class="chip chip-hood">Hood ×${{hC[ch]}}</span>`:''}}&nbsp;${{pC[ch]?`<span class="chip chip-pum">Pum ×${{pC[ch]}}</span>`:''}}</div></div>`).join('');
}}
function renderTopics(data){{
  const counts={{}};data.forEach(r=>counts[r.topic]=(counts[r.topic]||0)+r.mentioned.length);
  const sorted=Object.entries(counts).sort((a,b)=>b[1]-a[1]);
  const max=sorted[0]?.[1]||1,el=document.getElementById('topicBars');
  if(!sorted.length){{el.innerHTML='<div class="no-data">ไม่มีข้อมูล</div>';return}}
  const clsMap={{'Operations / BTaskee':'both','Notion / Knowledge':'hood','AI / Technology':'hood','Marketing':'pum','ISO / Quality':'hood','Approval / Admin':'pum'}};
  el.innerHTML=sorted.map(([t,c])=>`<div class="bar-item"><div class="bar-name" title="${{t}}">${{t}}</div><div class="bar-track"><div class="bar-fill ${{clsMap[t]||'both'}}" style="width:${{Math.round(c/max*100)}}%"></div></div><div class="bar-count">${{c}}</div></div>`).join('');
}}
function renderTimeline(data){{
  const sorted=[...data].sort((a,b)=>b.date.localeCompare(a.date)).slice(0,15);
  const el=document.getElementById('timeline');
  if(!sorted.length){{el.innerHTML='<div class="no-data">ไม่มีข้อมูล</div>';return}}
  el.innerHTML=sorted.map(r=>`<div class="tl-item"><div class="tl-dot ${{r.sender==='Hood'?'hood':'pum'}}"></div><div class="tl-content"><div class="tl-meta">${{r.date}} · <strong style="color:${{r.sender==='Hood'?'var(--hood)':'var(--pum)'}}">${{r.sender}}</strong><span class="tl-channel">#${{r.channel}}</span></div><div class="tl-text">${{r.preview.substring(0,80)}}${{r.preview.length>80?'…':''}}</div><div class="tl-mentions">${{r.mentioned.map(m=>`<span class="mention-tag">@${{m.replace(/\s*\(.*?\)/,'')}}</span>`).join('')}}</div></div></div>`).join('');
}}
function renderTable(data){{
  const sorted=[...data].sort((a,b)=>b.date.localeCompare(a.date));
  const el=document.getElementById('tableBody');
  if(!sorted.length){{el.innerHTML='<tr><td colspan="6" class="no-data">ไม่มีข้อมูลใน period ที่เลือก</td></tr>';return}}
  el.innerHTML=sorted.map(r=>`<tr><td style="white-space:nowrap">${{r.date}}</td><td><span class="sender-badge sender-${{r.sender.toLowerCase()}}">${{r.sender}}</span></td><td style="max-width:200px">${{r.mentioned.map(m=>`@${{m.replace(/\s*\(.*?\)/,'')}}`).join(', ')}}</td><td><span style="font-size:12px;color:var(--cyan)">#${{r.channel}}</span></td><td><span class="topic-tag">${{r.topic}}</span></td><td style="max-width:240px;color:var(--muted);font-size:12px">${{r.preview.substring(0,70)}}${{r.preview.length>70?'…':''}}</td></tr>`).join('');
}}
const LABELS={{today:'Today','7d':'Last 7 Days','30d':'Last Month','90d':'Last 3 Months','180d':'Last 6 Months',custom:'Custom Range'}};
function setFilter(f){{
  currentFilter=f;
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  const idx={{today:0,'7d':1,'30d':2,'90d':3,'180d':4}};
  if(idx[f]!==undefined)document.querySelectorAll('.filter-btn')[idx[f]].classList.add('active');
  document.getElementById('badgeRange').textContent=LABELS[f]||'Custom';
  renderAll();
}}
function toggleCustom(){{document.getElementById('customSection').classList.toggle('visible')}}
function applyCustom(){{
  const f=document.getElementById('customFrom').value,t=document.getElementById('customTo').value;
  if(f&&t){{customFrom=new Date(f);customTo=new Date(t+'T23:59:59');currentFilter='custom';document.getElementById('badgeRange').textContent=f+' → '+t;renderAll()}}
}}
renderAll();
</script>
</body>
</html>"""

if __name__ == "__main__":
    today = datetime.now(TZ_OFFSET)
    today_date = today.replace(hour=0, minute=0, second=0, microsecond=0)
    today_str   = today.strftime("%Y-%m-%d")
    refreshed   = today.strftime("%d %b %Y, %H:%M น.")

    print(f"🔍 Fetching Hood's messages...")
    hood_events = fetch_mentions(HOOD_ID, "Hood", today_date)
    print(f"   Found {len(hood_events)} mention events")

    print(f"🔍 Fetching Pum's messages...")
    pum_events = fetch_mentions(PUM_ID, "Pum", today_date)
    print(f"   Found {len(pum_events)} mention events")

    raw_data = hood_events + pum_events
    print(f"📊 Total mention events: {len(raw_data)}")

    html = build_html(raw_data, refreshed)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ index.html generated successfully")
