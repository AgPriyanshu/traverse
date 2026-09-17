import json, sys
sys.path.insert(0, '.')
from _parts import ICON, topbar, sidenav, pref

TOKENS = open('_tokens.css').read()
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600'
         '&family=Literata:ital,opsz,wght@0,7..72,400;0,7..72,500;0,7..72,600;1,7..72,400&display=swap">')

def dc(path, body, extra_css="", w=1440, h=900, themed=True):
    props = {"$preview": {"width": w, "height": h}}
    if themed:
        props["dark"] = {"editor": "boolean", "default": False, "section": "Theme"}
    script = ""
    if themed:
        script = ("\n<script data-dc-script data-props='" + json.dumps(props).replace("'", "&#39;") + "'>\n"
                  "class Component extends DCLogic {\n"
                  "  renderVals() {\n"
                  "    return { theme: this.props.dark ? 'dark' : '' };\n"
                  "  }\n"
                  "}\n</script>")
    else:
        script = ("\n<script data-dc-script data-props='" + json.dumps(props).replace("'", "&#39;") + "'>\n"
                  "class Component extends DCLogic {}\n</script>")
    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  {FONTS}
  <style>
{TOKENS}
{extra_css}
  </style>
</helmet>
{body}
</x-dc>{script}
</body>
</html>
"""
    open(path, 'w').write(html)
    print("wrote", path, len(html))

# ───────────────────────────────── 1. Main — Shell & foundations
swatch = lambda n, v, note: f'''<div style="display:flex;flex-direction:column;gap:6px">
  <div style="height:44px;border-radius:7px;background:{v};border:1px solid var(--line)"></div>
  <div style="font-size:12.5px;font-weight:600">{n}</div><div style="font-size:12px;color:var(--ink3)">{note}</div></div>'''

fam = lambda n, c, dash, use: f'''<div style="display:flex;align-items:center;gap:12px">
  <svg width="56" height="10" style="flex:none"><line x1="2" y1="5" x2="54" y2="5" stroke="{c}" stroke-width="2.4" stroke-dasharray="{dash}" stroke-linecap="round"/></svg>
  <div><div style="font-size:13px;font-weight:600;color:{c}">{n}</div>
  <div style="font-size:12.5px;color:var(--ink3)">{use}</div></div></div>'''

MAIN_BODY = f'''<div class="rt" style="width:1440px;display:flex;flex-direction:column">
{topbar()}
<div style="display:flex;min-height:1010px">
{sidenav("Library")}
<main style="flex-grow:1;padding:26px 40px 40px;display:flex;flex-direction:column;gap:26px;max-width:1228px">

  <div style="display:flex;align-items:flex-end;gap:16px;padding-bottom:18px;border-bottom:1px solid var(--line)">
    <div>
      <h1 class="serif" style="margin:0;font-size:30px;font-weight:600;letter-spacing:-.015em;line-height:1.15">The reading tool, not the dashboard</h1>
      <p style="margin:8px 0 0;max-width:62ch;color:var(--ink2);font-size:14.5px;line-height:1.6">Literata carries anything a reader reads — names, book titles, quoted passages. IBM Plex Sans carries the interface around it, and IBM Plex Mono carries anything precise: page numbers, counts, confidence.</p>
    </div>
  </div>

  <section style="display:flex;flex-direction:column;gap:14px">
    <div class="lbl">Type</div>
    <div class="card" style="padding:26px 28px;display:flex;flex-direction:column;gap:18px">
      <div style="display:flex;align-items:baseline;gap:22px">
        <span class="mono" style="width:120px;flex:none;font-size:12px;color:var(--ink3)">display / 30</span>
        <span class="serif" style="font-size:30px;font-weight:600;letter-spacing:-.015em">Elizabeth Bennet</span></div>
      <div style="display:flex;align-items:baseline;gap:22px">
        <span class="mono" style="width:120px;flex:none;font-size:12px;color:var(--ink3)">heading / 20</span>
        <span class="serif" style="font-size:20px;font-weight:600">Pride and Prejudice</span></div>
      <div style="display:flex;align-items:baseline;gap:22px">
        <span class="mono" style="width:120px;flex:none;font-size:12px;color:var(--ink3)">quote / 16.5</span>
        <span class="serif" style="font-size:16.5px;font-style:italic;line-height:1.55;max-width:56ch;color:var(--ink)">“She is tolerable, but not handsome enough to tempt me; and I am in no humour at present to give consequence to young ladies who are slighted by other men.”</span></div>
      <div style="display:flex;align-items:baseline;gap:22px">
        <span class="mono" style="width:120px;flex:none;font-size:12px;color:var(--ink3)">body / 14.5</span>
        <span style="font-size:14.5px;max-width:64ch;line-height:1.6;color:var(--ink2)">Interface copy sits in Plex Sans at a comfortable measure. Never wider than about sixty-five characters, because this is something people read rather than scan.</span></div>
      <div style="display:flex;align-items:baseline;gap:22px">
        <span class="mono" style="width:120px;flex:none;font-size:12px;color:var(--ink3)">data / mono 12</span>
        <span class="mono" style="font-size:12px;color:var(--ink2)">p. 214 · ch. 34 · 41 mentions · 0.94</span></div>
    </div>
  </section>

  <div style="display:grid;grid-template-columns:repeat(2, minmax(0, 1fr));gap:26px">
    <section style="display:flex;flex-direction:column;gap:14px">
      <div class="lbl long">Surfaces and ink — light</div>
      <div class="card" style="padding:22px;display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));gap:14px">
        {swatch("paper", "#FAF7F2", "page ground")}
        {swatch("surface", "#FFFDFA", "cards, bars")}
        {swatch("sunken", "#F2EDE4", "wells, inputs")}
        {swatch("line", "#E2DACD", "borders")}
        {swatch("ink", "#2B2622", "13.1:1")}
        {swatch("ink-2", "#6B6157", "5.6:1")}
        {swatch("accent", "#A8502A", "5.4:1")}
        {swatch("accent-soft", "#F4E7DF", "chips, fills")}
      </div>
    </section>

    <section style="display:flex;flex-direction:column;gap:14px">
      <div class="lbl long">Kinds of tie — colour <em style="font-style:normal;color:var(--accent)">and</em> line</div>
      <div class="card" style="padding:22px;display:flex;flex-direction:column;gap:16px">
        {fam("Kinship", "var(--kin)", "0", "parent_of · sibling_of · guardian_of")}
        {fam("Romantic", "var(--rom)", "7 5", "married_to · engaged_to · lover_of")}
        {fam("Social", "var(--soc)", "2 4", "friend_of · employer_of · neighbour_of")}
        {fam("Adversarial", "var(--adv)", "9 4 2 4", "rival_of · enemy_of · deceives")}
        <p style="margin:2px 0 0;font-size:12.5px;line-height:1.55;color:var(--ink3);border-top:1px solid var(--line);padding-top:14px">Colour never carries meaning alone. Every family owns a stroke pattern too, so the graph still reads with colour vision deficiency, in greyscale, and in an export.</p>
      </div>
    </section>
  </div>

  <section style="display:flex;flex-direction:column;gap:14px">
    <div class="lbl long">The page reference</div>
    <div class="card" style="padding:24px 26px;display:flex;flex-direction:column;gap:18px">
      <div style="display:flex;align-items:center;gap:34px;flex-wrap:wrap">
        <div style="display:flex;flex-direction:column;gap:7px"><span class="mono" style="font-size:12px;color:var(--ink3)">default</span>{pref("p. 214")}</div>
        <div style="display:flex;flex-direction:column;gap:7px"><span class="mono" style="font-size:12px;color:var(--ink3)">hover</span><span class="pref" style="border-bottom-style:solid">p. 214</span></div>
        <div style="display:flex;flex-direction:column;gap:7px"><span class="mono" style="font-size:12px;color:var(--ink3)">focus-visible</span>{pref("p. 214","focus")}</div>
        <div style="display:flex;flex-direction:column;gap:7px"><span class="mono" style="font-size:12px;color:var(--ink3)">series</span>{pref("bk 1, p. 47")}</div>
        <div style="display:flex;flex-direction:column;gap:7px"><span class="mono" style="font-size:12px;color:var(--ink3)">range</span>{pref("pp. 96–98")}</div>
        <div style="display:flex;flex-direction:column;gap:7px"><span class="mono" style="font-size:12px;color:var(--ink3)">not yet rendered</span><span class="pref" style="color:var(--ink3);border-bottom-style:dashed">p. 331</span></div>
      </div>
      <p style="margin:0;font-size:13px;line-height:1.6;color:var(--ink2);border-top:1px solid var(--line);padding-top:16px;max-width:78ch">Set like a cross-reference in a printed book — oldstyle figures, a hairline rule, no capsule. It is a <strong style="color:var(--ink)">link, not a button</strong>: it takes you to the page. Its accessible name reads “page 214 of Pride and Prejudice”, never a bare number. It sits beside every fact the system states, and a fact without one is not rendered at all.</p>
    </div>
  </section>

</main></div></div>

<div class="rt dark" style="width:1440px;padding-bottom:26px;display:flex;flex-direction:column">
{topbar()}
<div style="display:flex;min-height:214px">
{sidenav("Library")}
<main style="flex-grow:1;padding:22px 40px;display:flex;gap:30px;align-items:flex-start">
  <div style="display:flex;flex-direction:column;gap:12px;flex-grow:1">
    <div class="lbl long">Dark — the same page, re-tinted</div>
    <div class="card" style="padding:18px 20px;display:flex;flex-direction:column;gap:12px">
      <span class="serif" style="font-size:19px;font-weight:600">Elizabeth Bennet</span>
      <span class="serif" style="font-size:15px;font-style:italic;line-height:1.55;color:var(--ink2);max-width:52ch">“There is a stubbornness about me that never can bear to be frightened at the will of others.”</span>
      <div style="display:flex;align-items:center;gap:10px">{pref("p. 158")}<span class="chip">narrated</span></div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:repeat(4, minmax(0, 1fr));gap:12px;width:440px">
    {swatch("paper", "#1C1815", "")}{swatch("surface", "#24201C", "")}{swatch("line", "#3A342E", "")}{swatch("accent", "#D98357", "7.0:1")}
  </div>
  <div style="display:flex;flex-direction:column;gap:14px;width:250px">
    {fam("Kinship", "var(--kin)", "0", "")}
    {fam("Romantic", "var(--rom)", "7 5", "")}
    {fam("Social", "var(--soc)", "2 4", "")}
    {fam("Adversarial", "var(--adv)", "9 4 2 4", "")}
  </div>
</main></div></div>'''

dc('Main.dc.html', MAIN_BODY, w=1440, h=1500, themed=False)

# ───────────────────────────────── 2. Library
def pill(txt, tone):
    c = {"ok":"var(--ok)","warn":"var(--warn)","err":"var(--err)","idle":"var(--ink3)"}[tone]
    return '<span class="state" style="color:%s"><i></i>%s</span>' % (c, txt)

def spine(colors):
    bars = "".join(f'<div style="flex-grow:1;background:{c}"></div>' for c in colors)
    return f'<div style="display:flex;flex-direction:column;width:7px;flex:none;border-radius:3px 0 0 3px;overflow:hidden">{bars}</div>'

def bookcard(title, author, meta, status, tone, colors, extra=""):
    return f'''<div class="card" style="display:flex;overflow:hidden;box-shadow:var(--shadow)">
  {spine(colors)}
  <div style="flex-grow:1;padding:18px 20px;display:flex;flex-direction:column;gap:10px">
    <div style="display:flex;align-items:flex-start;gap:12px">
      <div style="flex-grow:1">
        <div class="serif" style="font-size:17.5px;font-weight:600;line-height:1.25;letter-spacing:-.01em">{title}</div>
        <div style="margin-top:3px;font-size:12.5px;color:var(--ink2)">{author}</div>
      </div>{pill(status, tone)}
    </div>
    <div class="mono" style="font-size:12.5px;color:var(--ink3)">{meta}</div>
    {extra}
  </div></div>'''

def bookrow(n, title, state):
    return f'''<div style="display:flex;align-items:center;gap:10px;font-size:12px;color:var(--ink2)">
      <span class="mono" style="color:var(--ink3);width:16px;flex:none">{n}</span>
      <span class="serif" style="flex-grow:1;font-size:13px">{title}</span><span style="color:var(--ink3);font-size:12.5px">{state}</span></div>'''

LIBRARY_BODY = f'''<div class="rt {{{{theme}}}}" style="width:1440px;display:flex;flex-direction:column">
{topbar("All projects")}
<div style="display:flex;min-height:1024px">
{sidenav("Library")}
<main style="flex-grow:1;padding:26px 40px 40px;display:flex;flex-direction:column;gap:24px">

  <div style="display:flex;align-items:flex-end;gap:20px;padding-bottom:18px;border-bottom:1px solid var(--line)">
    <div style="flex-grow:1">
      <h1 class="serif" style="margin:0;font-size:27px;font-weight:600;letter-spacing:-.015em">Your library</h1>
      <p style="margin:7px 0 0;color:var(--ink2);font-size:14px;max-width:60ch">Six projects · 241 characters · 1,904 relationships, every one of them cited.</p>
    </div>
    <div style="display:flex;gap:10px">
      <div style="display:flex;align-items:center;gap:7px;padding:9px 14px;border:1px solid var(--line);border-radius:8px;background:var(--surface);font-size:13px;font-weight:500">New project</div>
      <div style="display:flex;align-items:center;gap:7px;padding:9px 15px;border-radius:8px;background:var(--accent);color:var(--accentInk);font-size:13px;font-weight:600">{ICON["up"].replace('width="22" height="22"','width="15" height="15"')}Upload a novel</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3, minmax(0, 1fr));gap:18px">
    {bookcard("Pride and Prejudice","Jane Austen · 1813","61 chapters · 432 pp · 47 characters","Ready","ok",["#A8502A","#8A6A12","#2C6E6A"])}
    {bookcard("Anne of Green Gables","L. M. Montgomery · series","3 of 8 books · 112 characters","Ready","ok",["#2C6E6A","#5D4A96","#A6385C"],
      '<div style="display:flex;flex-direction:column;gap:5px;padding-top:9px;border-top:1px solid var(--line)">'
      + bookrow(1,"Anne of Green Gables","38 characters")
      + bookrow(2,"Anne of Avonlea","+21 new")
      + bookrow(3,"Anne of the Island","+53 new") + '</div>')}
    {bookcard("Wuthering Heights","Emily Brontë · 1847","34 chapters · 288 pp · 23 characters","Ready","ok",["#5D4A96","#A6385C","#2B2622"],
      '<div style="display:flex;align-items:center;gap:7px;padding-top:9px;border-top:1px solid var(--line);font-size:12.5px;color:var(--warn)">'
      + ICON["warn"] + '<span>2 name collisions resolved by review</span></div>')}
    {bookcard("The Adventures of Sherlock Holmes","Arthur Conan Doyle · series","2 of 4 books · 64 characters","1 book processing","warn",["#2C6E6A","#8A6A12"],
      '<div style="display:flex;flex-direction:column;gap:5px;padding-top:9px;border-top:1px solid var(--line)">'
      + bookrow(1,"A Study in Scarlet","31 characters")
      + bookrow(2,"The Sign of the Four","+18 new")
      + bookrow(3,"The Hound of the Baskervilles","mapping relationships…") + '</div>')}
    {bookcard("Frankenstein","Mary Shelley · 1818","Discovering characters · 3 of 5 stages","Processing","warn",["#8A6A12","#2C6E6A"],
      '<div style="display:flex;flex-direction:column;gap:7px;padding-top:9px;border-top:1px solid var(--line)">'
      '<div style="height:5px;border-radius:3px;background:var(--sunken);overflow:hidden"><div style="width:58%;height:100%;background:var(--accent)"></div></div>'
      '<div class="mono" style="font-size:12px;color:var(--ink3)">about 4 minutes remaining</div></div>')}
    {bookcard("The Great Gatsby","F. Scott Fitzgerald · 1925","Failed at “Finding chapters”","Needs attention","err",["#9E3B30","#2B2622"],
      '<div style="padding-top:9px;border-top:1px solid var(--line);font-size:12px;color:var(--ink2);line-height:1.5">'
      'Scanned pages with no text layer. <span style="color:var(--accent);font-weight:600">Re-run with OCR →</span></div>')}
  </div>

  <div style="margin-top:8px;display:flex;flex-direction:column;gap:12px">
    <div class="lbl long">Empty state — a first visit</div>
    <div class="card" style="padding:56px 40px;display:flex;flex-direction:column;align-items:center;gap:16px;text-align:center;background:var(--sunken);border-style:dashed">
      <div style="color:var(--ink3)">{ICON["book"].replace('width="17" height="17"','width="34" height="34"')}</div>
      <div class="serif" style="font-size:21px;font-weight:600">No books yet — upload a novel to begin</div>
      <p style="margin:0;max-width:54ch;color:var(--ink2);font-size:14px;line-height:1.6">Drop in a PDF and Traverse reads it end to end: every character, every relationship, and the exact page each one was established on. A 430-page novel takes about twenty minutes.</p>
      <div style="display:flex;align-items:center;gap:8px;margin-top:6px;padding:10px 18px;border-radius:8px;background:var(--accent);color:var(--accentInk);font-size:13.5px;font-weight:600">{ICON["up"].replace('width="22" height="22"','width="16" height="16"')}Upload a novel</div>
      <div style="font-size:12.5px;color:var(--ink3)">or start with <span style="color:var(--accent);font-weight:600">Pride and Prejudice</span>, already prepared</div>
    </div>
  </div>

</main></div></div>'''

dc('Library.dc.html', LIBRARY_BODY, w=1440, h=1080)

# ───────────────────────────────── 3. Upload & ingestion progress
def stagerow(name, detail, state, dur, last=False, extra=""):
    if state == "done":
        dot = '<div style="width:22px;height:22px;border-radius:50%;background:var(--ok);color:#fff;display:flex;align-items:center;justify-content:center;flex:none">' + ICON["tick"] + '</div>'
        rail, nc = "var(--ok)", "var(--ink)"
    elif state == "fail":
        dot = '<div style="width:22px;height:22px;border-radius:50%;background:var(--err);color:#fff;display:flex;align-items:center;justify-content:center;flex:none">' + ICON["warn"] + '</div>'
        rail, nc = "var(--line)", "var(--err)"
    else:
        dot = '<div style="width:22px;height:22px;border-radius:50%;border:2px dashed var(--line);flex:none"></div>'
        rail, nc = "var(--line)", "var(--ink3)"
    line = "" if last else '<div style="flex-grow:1;width:2px;background:' + rail + ';margin:4px 0"></div>'
    pad = "0" if last else "22px"
    return ('<div style="display:flex;gap:14px">'
      '<div style="display:flex;flex-direction:column;align-items:center;flex:none;width:22px">' + dot + line + '</div>'
      '<div style="flex-grow:1;padding-bottom:' + pad + '">'
        '<div style="display:flex;align-items:baseline;gap:12px">'
          '<span style="font-size:14.5px;font-weight:600;color:' + nc + '">' + name + '</span>'
          '<span class="mono" style="font-size:12.5px;color:var(--ink3);margin-left:auto">' + dur + '</span></div>'
        '<div style="margin-top:3px;font-size:12.5px;color:var(--ink2);line-height:1.55">' + detail + '</div>'
        + extra + '</div></div>')

def icon(n, px):
    return ICON[n].replace('width="22" height="22"', 'width="%d" height="%d"' % (px, px)) \
                  .replace('width="17" height="17"', 'width="%d" height="%d"' % (px, px)) \
                  .replace('width="13" height="13"', 'width="%d" height="%d"' % (px, px))

RETRY = ('<div style="margin-top:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
  '<div style="display:flex;align-items:center;gap:7px;padding:7px 13px;border-radius:7px;background:var(--accent);color:var(--accentInk);font-size:12.5px;font-weight:600">'
  + ICON["redo"] + 'Retry from this stage</div>'
  '<span style="font-size:12px;color:var(--ink3)">or <a href="#">send batch 14 to a stronger model</a></span></div>')

STAGES = (
  stagerow("Reading the PDF", "432 pages parsed. 1,107 passages, every one carrying the page it came from.", "done", "1m 12s")
+ stagerow("Finding chapters", "24 chapters found — 21 by pattern, 3 read by the model.", "done", "48s")
+ stagerow("Embedding passages", "1,107 passages embedded locally with BGE-M3. Nothing left this machine.", "done", "3m 06s")
+ stagerow("Discovering characters", "The model returned an unreadable response for batch 14 of 31, four times running. The 13 batches before it are saved and will not be redone.", "fail", "failed", extra=RETRY)
+ stagerow("Mapping relationships", "Waits for the cast. Roughly 9 minutes once it starts.", "wait", "—", last=True))

UPLOAD_BODY = '''<div class="rt {{theme}}" style="width:1440px;display:flex;flex-direction:column">
''' + topbar("Frankenstein") + '''
<div style="display:flex;min-height:1024px">
''' + sidenav("Library") + '''
<main style="flex-grow:1;padding:26px 40px 40px;display:flex;flex-direction:column;gap:26px">

  <div style="display:flex;align-items:flex-end;gap:20px;padding-bottom:18px;border-bottom:1px solid var(--line)">
    <div style="flex-grow:1">
      <h1 class="serif" style="margin:0;font-size:27px;font-weight:600;letter-spacing:-.015em">Frankenstein</h1>
      <p style="margin:7px 0 0;color:var(--ink2);font-size:14px">Mary Shelley · 1818 · 280 pages · added 14 minutes ago</p>
    </div>
    <div style="display:flex;align-items:center;gap:8px;padding:8px 14px;border:1px solid var(--err);border-radius:8px;color:var(--err);font-size:13px;font-weight:600">''' + ICON["warn"] + '''Paused — one stage needs you</div>
  </div>

  <div style="display:flex;gap:30px;align-items:flex-start">
    <div class="card" style="flex-grow:1;padding:28px 30px;display:flex;flex-direction:column;gap:20px">
      <div style="display:flex;align-items:baseline;gap:14px;padding-bottom:16px;border-bottom:1px solid var(--line)">
        <span class="serif" style="font-size:18px;font-weight:600">Reading the book</span>
        <span class="mono" style="font-size:12px;color:var(--ink3);margin-left:auto">3 of 5 done · 5m 06s so far</span>
      </div>
      ''' + STAGES + '''
    </div>

    <div style="width:320px;flex:none;display:flex;flex-direction:column;gap:18px">
      <div class="card" style="padding:20px 22px;display:flex;flex-direction:column;gap:13px">
        <span class="lbl">This file</span>
        <div style="display:flex;flex-direction:column;gap:9px;font-size:12.5px">
          <div style="display:flex;gap:10px"><span style="color:var(--ink3);width:84px;flex:none">Pages</span><span class="mono">280</span></div>
          <div style="display:flex;gap:10px"><span style="color:var(--ink3);width:84px;flex:none">Passages</span><span class="mono">1,107</span></div>
          <div style="display:flex;gap:10px"><span style="color:var(--ink3);width:84px;flex:none">Chapters</span><span class="mono">24</span></div>
          <div style="display:flex;gap:10px"><span style="color:var(--ink3);width:84px;flex:none">Fingerprint</span><span class="mono" style="color:var(--ink2)">b2a9…41c7</span></div>
          <div style="display:flex;gap:10px"><span style="color:var(--ink3);width:84px;flex:none">Inference</span><span style="color:var(--ok);font-weight:600">local only</span></div>
        </div>
      </div>
      <div class="card" style="padding:20px 22px;background:var(--sunken);display:flex;flex-direction:column;gap:9px">
        <span class="lbl">Nothing is lost</span>
        <p style="margin:0;font-size:12.5px;line-height:1.65;color:var(--ink2)">Each stage is saved as it finishes. Retrying picks up where it stopped — the parse, the chapters and the embeddings above are already on disk and will not be recomputed.</p>
      </div>
    </div>
  </div>

  <div style="margin-top:6px;display:flex;flex-direction:column;gap:12px">
    <div class="lbl long">Before any of that — dropping the file in</div>
    <div class="card" style="padding:52px 40px;display:flex;flex-direction:column;align-items:center;gap:14px;text-align:center;border-style:dashed;border-color:var(--accent);background:var(--accentSoft)">
      <div style="color:var(--accent)">''' + icon("up", 30) + '''</div>
      <div class="serif" style="font-size:19px;font-weight:600;color:var(--accent)">Drop <em>Frankenstein.pdf</em> to add it to this project</div>
      <p style="margin:0;max-width:52ch;color:var(--ink2);font-size:13.5px;line-height:1.6">PDF, up to 1,000 pages. Reading it takes about twenty minutes, and you can close the tab — it keeps going.</p>
    </div>
  </div>

</main></div></div>'''

dc('UploadProgress.dc.html', UPLOAD_BODY, w=1440, h=1080)

# ───────────────────────────────── 4. Character list
def dist(vals, color="var(--accent)", w=148, h=26):
    """Mentions per chapter. Real distribution — it answers 'which stretch of the book is this person in'."""
    n = len(vals); mx = max(vals) or 1
    bw = w / n
    bars = []
    for i, v in enumerate(vals):
        bh = max(1.0, (v / mx) * (h - 3))
        bars.append('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" rx="0.6" fill="%s" opacity="%.2f"/>'
                    % (i * bw, h - bh, max(bw - 0.9, 0.9), bh, color, 0.30 + 0.70 * (v / mx)))
    return ('<svg width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-label="mentions per chapter">'
            % (w, h, w, h)) + "".join(bars) + \
           ('<line x1="0" y1="%d" x2="%d" y2="%d" stroke="var(--line)" stroke-width="1"/></svg>' % (h, w, h))

def alias(a):
    return '<span>' + a + '</span>'

def crow(name, aliases, more, mentions, page, vals, color="var(--accent)", note=""):
    chips = '<span class="aliases">' + "".join(alias(a) for a in aliases)
    if more:
        chips += '<span style="font-style:normal;color:var(--ink3);font-size:12.5px">and ' + str(more) + ' more</span>'
    chips += '</span>'
    notehtml = ('<div style="margin-top:4px;font-size:12.5px;color:var(--ink3)">' + note + '</div>') if note else ''
    return ('<div style="display:flex;align-items:center;gap:20px;padding:13px 18px;border-top:1px solid var(--line)">'
      '<div style="width:250px;flex:none">'
        '<div class="serif" style="font-size:16px;font-weight:600;letter-spacing:-.005em">' + name + '</div>' + notehtml + '</div>'
      '<div style="flex-grow:1;min-width:0">' + chips + '</div>'
      '<div class="mono" style="width:78px;flex:none;text-align:right;font-size:12.5px;color:var(--ink2)">' + mentions + '</div>'
      '<div style="width:96px;flex:none;display:flex;justify-content:flex-end">' + pref(page) + '</div>'
      '<div style="width:148px;flex:none;display:flex;justify-content:flex-end">' + dist(vals, color) + '</div></div>')

import random
random.seed(7)
def curve(peaks, n=61, base=1):
    out = []
    for i in range(n):
        v = base
        for (c, amp, wid) in peaks:
            v += amp * pow(2.718, -((i - c) ** 2) / (2.0 * wid * wid))
        out.append(max(0.0, v + random.random() * 0.6))
    return out

GROUPS = [
 ("Protagonists", "2", [
   crow("Elizabeth Bennet", ["Elizabeth", "Lizzy", "Eliza"], 4, "1,142", "p. 3",
        curve([(6, 9, 9), (30, 11, 10), (52, 12, 8)], base=3)),
   crow("Fitzwilliam Darcy", ["Mr Darcy", "Darcy"], 3, "418", "p. 9",
        curve([(9, 6, 6), (33, 9, 7), (55, 10, 6)], base=1)),
 ]),
 ("Major", "7", [
   crow("Jane Bennet", ["Jane", "Miss Bennet"], 2, "292", "p. 3", curve([(4, 7, 7), (46, 6, 9)], base=1.5)),
   crow("Charles Bingley", ["Mr Bingley", "Bingley"], 1, "174", "p. 7", curve([(5, 7, 6), (54, 6, 5)], base=1)),
   crow("Mrs Bennet", ["Mrs. Bennet", "my dear"], 2, "187", "p. 1", curve([(2, 8, 5), (48, 5, 6)], base=1.4)),
   crow("Mr Bennet", ["Mr. Bennet", "her father"], 1, "143", "p. 1", curve([(2, 6, 5), (58, 5, 4)], base=1.2)),
   crow("Mr Collins", ["Mr. Collins", "William Collins"], 2, "131", "p. 62", curve([(15, 9, 5), (28, 6, 5)], base=0.6)),
   crow("George Wickham", ["Mr Wickham", "Wickham"], 2, "118", "p. 72", curve([(16, 7, 5), (47, 8, 5)], base=0.7)),
   crow("Lydia Bennet", ["Lydia", "the youngest"], 1, "104", "p. 4", curve([(3, 3, 5), (45, 10, 5)], base=0.8)),
 ]),
 ("Minor", "12", [
   crow("Charlotte Lucas", ["Charlotte", "Mrs Collins"], 1, "87", "p. 18", curve([(6, 4, 4), (27, 7, 5)], base=0.5),
        note="Becomes Mrs Collins in chapter 22 — one person, two names"),
   crow("Lady Catherine de Bourgh", ["Lady Catherine"], 2, "71", "p. 66", curve([(29, 8, 4), (56, 7, 3)], base=0.3)),
   crow("Caroline Bingley", ["Miss Bingley"], 2, "68", "p. 11", curve([(8, 6, 5), (41, 4, 6)], base=0.4)),
   crow("Mary Bennet", ["Mary"], 0, "24", "p. 4", curve([(3, 3, 6), (50, 2, 5)], base=0.3)),
   crow("Mrs Reynolds", ["the housekeeper"], 1, "12", "p. 240", curve([(43, 6, 2)], base=0.05),
        note="Resolved from “the housekeeper” by context, not by name"),
 ]),
]

def group(title, count, rows):
    return ('<section style="display:flex;flex-direction:column;gap:12px">'
      '<div style="display:flex;align-items:baseline;gap:10px">'
        '<h2 class="serif" style="margin:0;font-size:16px;font-weight:600">' + title + '</h2>'
        '<span class="mono" style="font-size:12px;color:var(--ink3)">' + count + '</span></div>'
      '<div class="card" style="overflow:hidden">'
      '<div style="display:flex;align-items:center;gap:20px;padding:9px 18px;background:var(--sunken)">'
        '<span class="lbl" style="width:250px;flex:none">Character</span>'
        '<span class="lbl" style="flex-grow:1">Also called</span>'
        '<span class="lbl" style="width:78px;flex:none;text-align:right">Mentions</span>'
        '<span class="lbl" style="width:96px;flex:none;text-align:right">First seen</span>'
        '<span class="lbl" style="width:148px;flex:none;text-align:right">Across the book</span></div>'
      + "".join(rows) + '</div></section>')

LIST_BODY = '''<div class="rt {{theme}}" style="width:1440px;display:flex;flex-direction:column">
''' + topbar() + '''
<div style="display:flex;min-height:1130px">
''' + sidenav("Characters") + '''
<main style="flex-grow:1;padding:26px 40px 40px;display:flex;flex-direction:column;gap:28px">

  <div style="display:flex;align-items:flex-end;gap:20px;padding-bottom:18px;border-bottom:1px solid var(--line)">
    <div style="flex-grow:1">
      <h1 class="serif" style="margin:0;font-size:27px;font-weight:600;letter-spacing:-.015em">Everyone in this book</h1>
      <p style="margin:7px 0 0;color:var(--ink2);font-size:14px;max-width:62ch">47 people, gathered from 3,209 mentions across 61 chapters. Names that turned out to be the same person have been folded together — open anyone to see why.</p>
    </div>
    <div style="display:flex;gap:9px;align-items:center">
      <div style="display:flex;align-items:center;gap:8px;width:230px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink3);font-size:13px">''' + ICON["search"] + '''<span>Try “Lizzy”</span></div>
      <div style="display:flex;align-items:center;gap:7px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);font-size:13px">Most mentioned''' + ICON["chev"] + '''</div>
    </div>
  </div>

  <div style="display:flex;flex-direction:column;gap:26px">
''' + "".join(group(t, c, r) for t, c, r in GROUPS) + '''
  </div>

  <div style="display:flex;align-items:center;justify-content:center;gap:8px;padding:14px;color:var(--ink3);font-size:13px">
    <span>28 more people appear once or twice.</span><a href="#">Show them</a>
  </div>

</main></div></div>'''

dc('CharacterList.dc.html', LIST_BODY, w=1440, h=1190)

# ───────────────────────────────── 5. Character detail
def aliasrow(form, count, method, shared=""):
    sh = ('<span style="margin-left:8px;font-size:12.5px;color:var(--warn)">' + shared + '</span>') if shared else ''
    return ('<div style="display:flex;align-items:center;gap:14px;padding:9px 0;border-top:1px solid var(--line)">'
      '<span class="serif" style="width:210px;flex:none;font-size:14.5px">' + form + '</span>'
      '<span class="mono" style="width:56px;flex:none;font-size:12px;color:var(--ink2);text-align:right">' + count + '</span>'
      '<span style="flex-grow:1;font-size:12px;color:var(--ink3)">' + method + sh + '</span></div>')

def attrrow(label, value, page):
    return ('<div style="display:flex;align-items:baseline;gap:14px;padding:9px 0;border-top:1px solid var(--line)">'
      '<span class="lbl" style="width:120px;flex:none">' + label + '</span>'
      '<span style="flex-grow:1;font-size:13.5px;color:var(--ink)">' + value + '</span>' + pref(page) + '</div>')

def relrow(who, pred, ev, page, color, dash):
    return ('<div style="display:flex;align-items:center;gap:11px;padding:10px 0;border-top:1px solid var(--line)">'
      '<svg width="26" height="8" style="flex:none"><line x1="1" y1="4" x2="25" y2="4" stroke="' + color +
      '" stroke-width="2.2" stroke-dasharray="' + dash + '" stroke-linecap="round"/></svg>'
      '<div style="flex-grow:1;min-width:0">'
        '<div class="serif" style="font-size:14px;font-weight:600">' + who + '</div>'
        '<div style="font-size:12.5px;color:var(--ink3);margin-top:1px">' + pred + ' · ' + ev + '</div></div>'
      + pref(page) + '</div>')

def relgroup(title, color, rows):
    return ('<div style="display:flex;flex-direction:column">'
      '<div style="display:flex;align-items:center;gap:8px;padding-bottom:4px">'
      '<span style="font-size:12px;font-weight:600;color:' + color + '">' + title + '</span></div>'
      + "".join(rows) + '</div>')

DETAIL_BODY = '''<div class="rt {{theme}}" style="width:1440px;display:flex;flex-direction:column">
''' + topbar() + '''
<div style="display:flex;min-height:1180px">
''' + sidenav("Characters") + '''
<main style="flex-grow:1;padding:26px 40px 40px;display:flex;flex-direction:column;gap:24px">

  <div style="display:flex;align-items:flex-end;gap:24px;padding-bottom:20px;border-bottom:1px solid var(--line)">
    <div style="flex-grow:1">
      <div style="display:flex;align-items:center;gap:10px;font-size:12.5px;color:var(--ink3)">
        <a href="#">Characters</a><span>/</span><span>Elizabeth Bennet</span></div>
      <h1 class="serif" style="margin:8px 0 0;font-size:34px;font-weight:600;letter-spacing:-.02em;line-height:1.1">Elizabeth Bennet</h1>
      <div style="display:flex;align-items:center;gap:9px;margin-top:11px">
        <span class="chip" style="border-color:var(--accent);color:var(--accent);background:var(--accentSoft);font-weight:600">Protagonist</span>
        <span class="mono" style="font-size:12px;color:var(--ink2)">1,142 mentions · chapters 1–61</span>
        <span style="color:var(--ink3)">·</span><span style="font-size:12.5px;color:var(--ink2)">first seen</span>''' + pref("p. 3") + '''
      </div>
    </div>
    <div style="display:flex;gap:9px">
      <div style="display:flex;align-items:center;gap:7px;padding:8px 13px;border:1px solid var(--line);border-radius:8px;background:var(--surface);font-size:13px;font-weight:500">''' + ICON["graph"] + '''See in the graph</div>
      <div style="display:flex;align-items:center;gap:7px;padding:8px 13px;border-radius:8px;background:var(--accent);color:var(--accentInk);font-size:13px;font-weight:600">''' + ICON["ask"] + '''Ask about her</div>
    </div>
  </div>

  <div style="display:flex;gap:30px;align-items:flex-start">
    <div style="flex-grow:1;display:flex;flex-direction:column;gap:24px;min-width:0">

      <section class="card" style="padding:24px 26px;display:flex;flex-direction:column;gap:6px">
        <div style="display:flex;align-items:baseline;gap:12px;padding-bottom:12px">
          <h2 class="serif" style="margin:0;font-size:17px;font-weight:600">Why these are all one person</h2>
          <span style="font-size:12.5px;color:var(--ink3);margin-left:auto">7 forms · 1,142 mentions</span></div>
        ''' + (
          aliasrow("Elizabeth", "604", "exact match")
        + aliasrow("Lizzy", "231", "nickname table")
        + aliasrow("Eliza", "46", "nickname table")
        + aliasrow("Miss Elizabeth Bennet", "118", "honorific stripped")
        + aliasrow("Miss Eliza Bennet", "39", "honorific stripped + nickname")
        + aliasrow("Miss Bennet", "12", "context — 74 other uses mean Jane", shared="ambiguous form")
        + aliasrow("my dearest Lizzy", "92", "context, in Jane’s letters")
        ) + '''
        <p style="margin:14px 0 0;padding-top:14px;border-top:1px solid var(--line);font-size:12.5px;line-height:1.65;color:var(--ink2);max-width:70ch">“Miss Bennet” is the difficult one: unqualified it usually means Jane, the eldest. The 12 uses folded in here sit in passages where Jane is absent or already named. <a href="#">Check each one</a>.</p>
      </section>

      <section class="card" style="padding:24px 26px;display:flex;flex-direction:column;gap:6px">
        <div style="display:flex;align-items:baseline;gap:12px;padding-bottom:12px">
          <h2 class="serif" style="margin:0;font-size:17px;font-weight:600">What the book says about her</h2>
          <span style="font-size:12.5px;color:var(--ink3);margin-left:auto">nothing here without a page</span></div>
        ''' + (
          attrrow("Family", "Second of five daughters of Mr and Mrs Bennet", "p. 3")
        + attrrow("Home", "Longbourn, Hertfordshire", "p. 1")
        + attrrow("Age", "Not yet one-and-twenty", "p. 149")
        + attrrow("Described as", "“She has fine eyes” — <em>Mr Darcy, in dialogue</em>", "p. 27")
        + attrrow("Habit", "Walks three miles alone across the fields", "p. 32")
        ) + '''
      </section>

      <section class="card" style="padding:24px 26px;display:flex;flex-direction:column;gap:16px">
        <div style="display:flex;align-items:baseline;gap:12px">
          <h2 class="serif" style="margin:0;font-size:17px;font-weight:600">Where she appears</h2>
          <span style="font-size:12.5px;color:var(--ink3);margin-left:auto">mentions per chapter</span></div>
        <div style="display:flex;align-items:flex-end;gap:2px">''' + dist(curve([(6, 9, 9), (30, 11, 10), (52, 12, 8)], base=3), w=1040, h=92) + '''</div>
        <div style="display:flex;justify-content:space-between;font-size:12px;color:var(--ink3)" class="mono">
          <span>ch. 1</span><span>ch. 15</span><span>ch. 30</span><span>ch. 45</span><span>ch. 61</span></div>
      </section>

    </div>

    <aside style="width:360px;flex:none;display:flex;flex-direction:column;gap:18px">
      <div class="card" style="padding:22px 24px;display:flex;flex-direction:column;gap:18px">
        <div style="display:flex;align-items:baseline;gap:10px">
          <h2 class="serif" style="margin:0;font-size:17px;font-weight:600">Her people</h2>
          <span class="mono" style="font-size:12.5px;color:var(--ink3);margin-left:auto">14 relationships</span></div>
        ''' + (
          relgroup("Kinship", "var(--kin)", [
            relrow("Jane Bennet", "sister_of", "41 passages", "p. 3", "var(--kin)", "0"),
            relrow("Mr Bennet", "child_of", "63 passages", "p. 1", "var(--kin)", "0"),
            relrow("Mrs Bennet", "child_of", "58 passages", "p. 1", "var(--kin)", "0"),
            relrow("Lydia Bennet", "sister_of", "27 passages", "p. 4", "var(--kin)", "0"),
          ])
        + relgroup("Romantic", "var(--rom)", [
            relrow("Fitzwilliam Darcy", "married_to · from ch. 58", "84 passages", "p. 376", "var(--rom)", "7 5"),
            relrow("Mr Collins", "refused · ch. 19", "11 passages", "p. 104", "var(--rom)", "7 5"),
          ])
        + relgroup("Social", "var(--soc)", [
            relrow("Charlotte Lucas", "friend_of", "34 passages", "p. 18", "var(--soc)", "2 4"),
            relrow("Mrs Gardiner", "niece_of", "22 passages", "p. 129", "var(--soc)", "2 4"),
          ])
        + relgroup("Adversarial", "var(--adv)", [
            relrow("Lady Catherine de Bourgh", "rival_of · from ch. 56", "16 passages", "p. 337", "var(--adv)", "9 4 2 4"),
            relrow("George Wickham", "deceived_by · ch. 16–36", "19 passages", "p. 78", "var(--adv)", "9 4 2 4"),
          ])
        ) + '''
      </div>
    </aside>
  </div>

</main></div></div>'''

dc('CharacterDetail.dc.html', DETAIL_BODY, w=1440, h=1240)

# ───────────────────────────────── 6. Graph explorer
FAMS = {"kin": ("var(--kin)", "0"), "rom": ("var(--rom)", "7 5"),
        "soc": ("var(--soc)", "2 4"), "adv": ("var(--adv)", "9 4 2 4")}

NODES = {
 "Elizabeth Bennet":   (430, 352, 34, "p"),
 "Fitzwilliam Darcy":  (668, 306, 29, "p"),
 "Jane Bennet":        (322, 196, 23, "m"),
 "Charles Bingley":    (566, 158, 21, "m"),
 "Mrs Bennet":         (236, 424, 20, "m"),
 "Mr Bennet":          (332, 512, 19, "m"),
 "Lydia Bennet":       (172, 318, 18, "m"),
 "George Wickham":     (700, 176, 18, "m"),
 "Mr Collins":         (614, 592, 17, "m"),
 "Charlotte Lucas":    (472, 558, 17, "n"),
 "Lady Catherine":     (820, 470, 17, "n"),
 "Caroline Bingley":   (772, 82,  15, "n"),
 "Mary Bennet":        (186, 522, 14, "n"),
 "Georgiana Darcy":    (858, 268, 14, "n"),
 "Mrs Gardiner":       (128, 196, 14, "n"),
}
EDGES = [
 ("Elizabeth Bennet","Jane Bennet","kin",3.0),("Elizabeth Bennet","Mrs Bennet","kin",2.6),
 ("Elizabeth Bennet","Mr Bennet","kin",2.8),("Elizabeth Bennet","Lydia Bennet","kin",2.2),
 ("Elizabeth Bennet","Mary Bennet","kin",1.6),("Jane Bennet","Mrs Bennet","kin",2.0),
 ("Jane Bennet","Mr Bennet","kin",1.8),("Lydia Bennet","Mrs Bennet","kin",1.8),
 ("Mr Bennet","Mrs Bennet","rom",2.4),("Mrs Gardiner","Elizabeth Bennet","kin",1.9),
 ("Mrs Gardiner","Jane Bennet","kin",1.4),("Mr Collins","Mr Bennet","kin",1.5),
 ("Fitzwilliam Darcy","Georgiana Darcy","kin",2.0),("Fitzwilliam Darcy","Lady Catherine","kin",1.8),
 ("Charles Bingley","Caroline Bingley","kin",1.8),
 ("Elizabeth Bennet","Fitzwilliam Darcy","rom",4.2),("Jane Bennet","Charles Bingley","rom",3.4),
 ("Charlotte Lucas","Mr Collins","rom",2.2),("Lydia Bennet","George Wickham","rom",2.4),
 ("Elizabeth Bennet","Mr Collins","rom",1.7),
 ("Elizabeth Bennet","Charlotte Lucas","soc",2.6),("Fitzwilliam Darcy","Charles Bingley","soc",3.0),
 ("Elizabeth Bennet","Mrs Gardiner","soc",1.6),("Caroline Bingley","Jane Bennet","soc",1.6),
 ("Lady Catherine","Mr Collins","soc",2.0),("Charlotte Lucas","Jane Bennet","soc",1.3),
 ("Elizabeth Bennet","George Wickham","adv",2.4),("Elizabeth Bennet","Lady Catherine","adv",2.2),
 ("Fitzwilliam Darcy","George Wickham","adv",2.6),("Caroline Bingley","Elizabeth Bennet","adv",1.8),
]
def graph_svg(w=1000, h=690):
    out = ['<svg width="%d" height="%d" viewBox="0 0 %d %d" role="img" aria-label="Character relationship graph for Pride and Prejudice">' % (w, h, w, h)]
    for a, b, fam, sw in EDGES:
        (x1, y1, _, _), (x2, y2, _, _) = NODES[a], NODES[b]
        c, d = FAMS[fam]
        hl = (a, b) in (("Elizabeth Bennet", "Fitzwilliam Darcy"),)
        out.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="%.1f" stroke-dasharray="%s" stroke-linecap="round" opacity="%.2f"/>'
                   % (x1, y1, x2, y2, c, sw + (1.4 if hl else 0), d, 0.95 if hl else 0.62))
    for name, (x, y, r, tier) in NODES.items():
        fs = {"p": 14.5, "m": 12.5, "n": 11.5}[tier]
        fw = {"p": 600, "m": 600, "n": 500}[tier]
        lead = name.split(" ")[0] if tier == "n" else name
        out.append('<circle cx="%d" cy="%d" r="%d" fill="var(--surface)" stroke="var(--ink)" stroke-width="%.1f"/>'
                   % (x, y, r, 2.2 if tier == "p" else 1.4))
        out.append('<circle cx="%d" cy="%d" r="%d" fill="var(--accent)" opacity="%.2f"/>'
                   % (x, y, r - 4, {"p": .22, "m": .13, "n": .07}[tier]))
        out.append('<text x="%d" y="%d" text-anchor="middle" font-family="Literata,Georgia,serif" font-size="%.1f" font-weight="%d" fill="var(--ink)">%s</text>'
                   % (x, y + r + 15, fs, fw, lead))
    out.append('</svg>')
    return "".join(out)

def filt(label, color, dash, on=True):
    box = ('<div style="width:15px;height:15px;border-radius:4px;flex:none;display:flex;align-items:center;justify-content:center;'
           + ('background:var(--accent);color:var(--accentInk)' if on else 'border:1.5px solid var(--line)') + '">'
           + (icon("tick", 10) if on else '') + '</div>')
    sw = ('<svg width="22" height="8" style="flex:none"><line x1="1" y1="4" x2="21" y2="4" stroke="' + color +
          '" stroke-width="2.2" stroke-dasharray="' + dash + '" stroke-linecap="round"/></svg>') if color else ''
    return ('<div style="display:flex;align-items:center;gap:9px;padding:6px 0;font-size:13px;color:var(--ink)">'
            + box + sw + '<span style="flex-grow:1">' + label + '</span></div>')

GRAPH_BODY = '''<div class="rt {{theme}}" style="width:1440px;display:flex;flex-direction:column">
''' + topbar() + '''
<div style="display:flex;min-height:844px">
''' + sidenav("Graph") + '''
<div style="flex-grow:1;display:flex;min-width:0">

  <aside style="width:236px;flex:none;border-right:1px solid var(--line);background:var(--surface);padding:20px 18px;display:flex;flex-direction:column;gap:22px">
    <div style="display:flex;flex-direction:column;gap:2px">
      <span class="lbl" style="margin-bottom:6px">Kind of tie</span>
      ''' + (filt("Kinship", "var(--kin)", "0") + filt("Romantic", "var(--rom)", "7 5")
            + filt("Social", "var(--soc)", "2 4") + filt("Adversarial", "var(--adv)", "9 4 2 4")) + '''
    </div>
    <div style="display:flex;flex-direction:column;gap:2px">
      <span class="lbl" style="margin-bottom:6px">How prominent</span>
      ''' + (filt("Protagonists", None, None) + filt("Major", None, None)
            + filt("Minor", None, None) + filt("Mentioned once", None, None, on=False)) + '''
    </div>
    <div style="display:flex;flex-direction:column;gap:9px">
      <span class="lbl">Confidence above</span>
      <div style="display:flex;align-items:center;gap:10px">
        <div style="flex-grow:1;height:4px;border-radius:2px;background:var(--sunken);position:relative">
          <div style="position:absolute;left:0;top:0;bottom:0;width:62%;background:var(--accent);border-radius:2px"></div>
          <div style="position:absolute;left:62%;top:-5px;width:14px;height:14px;border-radius:50%;background:var(--surface);border:2px solid var(--accent)"></div></div>
        <span class="mono" style="font-size:12px;color:var(--ink2)">0.62</span></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:9px">
      <span class="lbl">I have read up to</span>
      <div style="display:flex;align-items:center;gap:10px">
        <div style="flex-grow:1;height:4px;border-radius:2px;background:var(--sunken);position:relative">
          <div style="position:absolute;left:0;top:0;bottom:0;width:100%;background:var(--accent);border-radius:2px"></div>
          <div style="position:absolute;left:calc(100% - 14px);top:-5px;width:14px;height:14px;border-radius:50%;background:var(--surface);border:2px solid var(--accent)"></div></div>
        <span class="mono" style="font-size:12px;color:var(--ink2)">ch. 61</span></div>
      <p style="margin:0;font-size:12.5px;line-height:1.55;color:var(--ink3)">Drag back and anything you have not reached disappears — from the graph, the answers and the citations.</p>
    </div>
    <div style="flex-grow:1"></div>
    <div style="padding-top:16px;border-top:1px solid var(--line);display:flex;flex-direction:column;gap:7px">
      <div class="mono" style="font-size:12.5px;color:var(--ink3)">47 people · 214 ties</div>
      <div class="mono" style="font-size:12.5px;color:var(--ink3)">showing 15 · 30 ties</div>
    </div>
  </aside>

  <main style="flex-grow:1;min-width:0;display:flex;flex-direction:column;background:var(--sunken)">
    <div style="display:flex;align-items:center;gap:14px;padding:14px 24px;border-bottom:1px solid var(--line);background:var(--surface)">
      <h1 class="serif" style="margin:0;font-size:19px;font-weight:600">Who knows whom</h1>
      <span class="mono" style="font-size:12px;color:var(--ink3)">Pride and Prejudice · all 61 chapters</span>
      <div style="flex-grow:1"></div>
      <div style="display:flex;border:1px solid var(--line);border-radius:8px;overflow:hidden">
        <div style="display:flex;align-items:center;gap:6px;padding:7px 12px;background:var(--accent);color:var(--accentInk);font-size:12.5px;font-weight:600">''' + ICON["graph"] + '''Graph</div>
        <div style="display:flex;align-items:center;gap:6px;padding:7px 12px;background:var(--surface);color:var(--ink2);font-size:12.5px;font-weight:500">''' + ICON["review"] + '''List</div>
      </div>
    </div>

    <div style="position:relative;flex-grow:1;padding:22px 24px;display:flex;align-items:center;justify-content:center">
      ''' + graph_svg() + '''
      <div class="card" style="position:absolute;left:36px;bottom:26px;padding:14px 16px;display:flex;flex-direction:column;gap:9px;box-shadow:var(--shadow)">
        <span class="lbl">How to read it</span>
        ''' + "".join(
          '<div style="display:flex;align-items:center;gap:9px;font-size:12px"><svg width="26" height="8" style="flex:none">'
          '<line x1="1" y1="4" x2="25" y2="4" stroke="' + c + '" stroke-width="2.4" stroke-dasharray="' + d +
          '" stroke-linecap="round"/></svg><span style="color:var(--ink2)">' + n + '</span></div>'
          for n, (c, d) in [("Kinship", FAMS["kin"]), ("Romantic", FAMS["rom"]),
                            ("Social", FAMS["soc"]), ("Adversarial", FAMS["adv"])]) + '''
        <div style="padding-top:8px;border-top:1px solid var(--line);font-size:12.5px;color:var(--ink3);line-height:1.5;max-width:20ch">Thicker means more passages say so. Bigger means more of the book.</div>
      </div>
      <div class="card" style="position:absolute;right:36px;top:26px;padding:12px 15px;display:flex;align-items:center;gap:10px;box-shadow:var(--shadow)">
        <svg width="30" height="8" style="flex:none"><line x1="1" y1="4" x2="29" y2="4" stroke="var(--rom)" stroke-width="4" stroke-dasharray="7 5" stroke-linecap="round"/></svg>
        <div><div class="serif" style="font-size:13.5px;font-weight:600">Elizabeth &amp; Darcy</div>
        <div style="font-size:12.5px;color:var(--ink3)">84 passages · click for the pages</div></div>
      </div>
    </div>
  </main>
</div></div></div>'''

dc('GraphExplorer.dc.html', GRAPH_BODY, w=1440, h=900)

# ───────────────────────────────── 7. Evidence panel
def badge(kind):
    m = {"narrated": ("var(--ink2)", "var(--sunken)", "Narrated"),
         "dialogue": ("var(--warn)", "transparent", "Said by a character"),
         "inferred": ("var(--adv)", "transparent", "Pieced together")}
    c, bg, label = m[kind]
    return ('<span style="display:inline-flex;align-items:center;gap:5px;padding:2px 8px;border-radius:999px;'
            'border:1px solid ' + c + ';background:' + bg + ';color:' + c + ';font-size:12px;font-weight:600">' + label + '</span>')

def ev(quote, page, ch, kind, speaker=None):
    note = ''
    if speaker:
        note = ('<div style="margin-top:9px;padding:9px 12px;border-radius:7px;background:var(--sunken);'
                'font-size:12px;line-height:1.55;color:var(--ink2)">Mrs Bennet says this, in a fit of delight. '
                'The book does not state it as fact, so nothing in an answer will either.</div>')
    return ('<div style="padding:18px 0;border-top:1px solid var(--line)">'
      '<blockquote class="serif" style="margin:0;font-size:15.5px;font-style:italic;line-height:1.6;color:var(--ink)">“' + quote + '”</blockquote>'
      '<div style="display:flex;align-items:center;gap:9px;margin-top:11px;flex-wrap:wrap">'
      + pref(page) + '<span class="mono" style="font-size:12.5px;color:var(--ink3)">ch. ' + ch + '</span>'
      '<span style="flex-grow:1"></span>' + badge(kind)
      + (('<span style="font-size:12.5px;color:var(--warn)">— ' + speaker + '</span>') if speaker else '')
      + '</div>' + note + '</div>')

ARC_W = 660
def arc():
    segs = [(0, 0.18, "adv", "strangers, then a slight"),
            (0.18, 0.56, "adv", "she dislikes him"),
            (0.56, 0.80, "soc", "regard"),
            (0.80, 1.0, "rom", "engaged, then married")]
    out = ['<svg width="%d" height="84" viewBox="0 0 %d 84" role="img" aria-label="How the relationship changes across the book">' % (ARC_W, ARC_W)]
    for a, b, fam, _ in segs:
        c, d = FAMS[fam]
        out.append('<line x1="%.1f" y1="34" x2="%.1f" y2="34" stroke="%s" stroke-width="5" stroke-dasharray="%s" stroke-linecap="round"/>'
                   % (a * ARC_W + 2, b * ARC_W - 2, c, d))
    marks = [(0.04, "ch. 3", "p. 13"), (0.55, "ch. 34", "p. 189"), (0.80, "ch. 50", "p. 294"), (0.96, "ch. 58", "p. 376")]
    for x, ch, pg in marks:
        px = x * ARC_W
        out.append('<circle cx="%.1f" cy="34" r="5.5" fill="var(--surface)" stroke="var(--ink)" stroke-width="2"/>' % px)
        out.append('<text x="%.1f" y="18" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="11.5" fill="var(--ink3)">%s</text>' % (px, ch))
        out.append('<text x="%.1f" y="56" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="11.5" fill="var(--accent)">%s</text>' % (px, pg))
    out.append('<text x="2" y="76" font-family="IBM Plex Sans,sans-serif" font-size="11" fill="var(--ink3)">chapter 1</text>')
    out.append('<text x="%d" y="76" text-anchor="end" font-family="IBM Plex Sans,sans-serif" font-size="11" fill="var(--ink3)">chapter 61</text>' % ARC_W)
    out.append('</svg>')
    return "".join(out)

PANEL_BODY = '''<div class="rt {{theme}}" style="width:760px;min-height:1080px;background:var(--surface);display:flex;flex-direction:column;border-left:1px solid var(--line)">

  <div style="padding:24px 30px 20px;border-bottom:1px solid var(--line)">
    <div style="display:flex;align-items:flex-start;gap:14px">
      <div style="flex-grow:1;min-width:0">
        <div style="display:flex;align-items:center;gap:10px">
          <svg width="30" height="8" style="flex:none"><line x1="1" y1="4" x2="29" y2="4" stroke="var(--rom)" stroke-width="4" stroke-dasharray="7 5" stroke-linecap="round"/></svg>
          <span style="font-size:12px;font-weight:600;color:var(--rom)">Romantic</span>
        </div>
        <h2 class="serif" style="margin:10px 0 0;font-size:23px;font-weight:600;line-height:1.25;letter-spacing:-.015em">Elizabeth Bennet <span style="color:var(--ink3);font-weight:400">is married to</span> Fitzwilliam Darcy</h2>
        <div style="display:flex;align-items:center;gap:12px;margin-top:11px">
          <span class="mono" style="font-size:12px;color:var(--ink2)">84 passages say so</span>
          <span style="color:var(--line)">|</span>
          <span class="mono" style="font-size:12px;color:var(--ok)">confidence 0.96</span>
          <span style="color:var(--line)">|</span>
          <span class="mono" style="font-size:12px;color:var(--ink2)">from ch. 58</span>
        </div>
      </div>
      <div style="width:28px;height:28px;border-radius:7px;border:1px solid var(--line);display:flex;align-items:center;justify-content:center;color:var(--ink3);flex:none">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg></div>
    </div>
  </div>

  <div style="padding:24px 30px;border-bottom:1px solid var(--line);display:flex;flex-direction:column;gap:14px">
    <div style="display:flex;align-items:baseline;gap:10px">
      <h3 class="serif" style="margin:0;font-size:16px;font-weight:600">It did not start there</h3>
      <span style="font-size:12px;color:var(--ink3);margin-left:auto">four turns, each one cited</span></div>
    ''' + arc() + '''
    <p style="margin:0;font-size:12.5px;line-height:1.65;color:var(--ink2);max-width:66ch">The earlier states are kept, not overwritten. Ask what they were to each other in chapter 20 and you get the answer that was true in chapter 20.</p>
  </div>

  <div style="padding:20px 30px 30px;display:flex;flex-direction:column">
    <div style="display:flex;align-items:baseline;gap:10px;padding-bottom:6px">
      <h3 class="serif" style="margin:0;font-size:16px;font-weight:600">The passages</h3>
      <span class="mono" style="font-size:12.5px;color:var(--ink3);margin-left:auto">showing 5 of 84</span></div>
    ''' + (
      ev("She is tolerable, but not handsome enough to tempt me; and I am in no humour at present to give consequence to young ladies who are slighted by other men.",
         "p. 13", "3", "dialogue", speaker="Mr Darcy, at the Meryton assembly")
    + ev("In vain have I struggled. It will not do. My feelings will not be repressed. You must allow me to tell you how ardently I admire and love you.",
         "p. 189", "34", "dialogue", speaker="Mr Darcy, at Hunsford")
    + ev("She respected, she esteemed, she was grateful to him, she felt a real interest in his welfare; and she only wanted to know how far she wished that welfare to depend upon herself.",
         "p. 294", "50", "narrated")
    + ev("Elizabeth’s spirits soon rising to playfulness again, she wanted Mr Darcy to account for his having ever fallen in love with her.",
         "p. 376", "58", "narrated")
    + ev("Oh! my sweetest Lizzy! how rich and how great you will be! What pin-money, what jewels, what carriages you will have!",
         "p. 378", "59", "dialogue", speaker="Mrs Bennet")
    ) + '''
    <div style="display:flex;align-items:center;justify-content:center;gap:8px;padding:20px 0 0;border-top:1px solid var(--line)">
      <a href="#" style="font-size:13px;font-weight:600">Show the other 79 passages</a></div>
  </div>
</div>'''

dc('EvidencePanel.dc.html', PANEL_BODY, w=760, h=1080)

# ───────────────────────────────── 8. Ask
def q(text):
    return ('<div style="display:flex;justify-content:flex-end"><div class="serif" style="max-width:74%;padding:12px 18px;'
            'border-radius:14px 14px 4px 14px;background:var(--accentSoft);color:var(--ink);font-size:16px;line-height:1.5">'
            + text + '</div></div>')

def route(label):
    return ('<div style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--ink3)">'
            + icon("graph", 13) + '<span>' + label + '</span></div>')

SUGG = [("Who is Mr Collins, and why is he so trying?", "he turns up in chapter 13 and never quite leaves"),
        ("How do Elizabeth and Darcy end up together?", "the arc across all 61 chapters"),
        ("Who are all five Bennet sisters?", "a complete list, not a plausible one")]

ASK_BODY = '''<div class="rt {{theme}}" style="width:1440px;display:flex;flex-direction:column">
''' + topbar() + '''
<div style="display:flex;min-height:1064px">
''' + sidenav("Ask") + '''
<main style="flex-grow:1;display:flex;flex-direction:column;min-width:0">

  <div style="display:flex;align-items:center;gap:14px;padding:14px 32px;border-bottom:1px solid var(--line);background:var(--surface)">
    <h1 class="serif" style="margin:0;font-size:19px;font-weight:600">Ask about this book</h1>
    <span class="mono" style="font-size:12px;color:var(--ink3)">Pride and Prejudice · read up to ch. 61</span>
    <div style="flex-grow:1"></div>
    <span style="display:flex;align-items:center;gap:7px;font-size:12px;color:var(--ok);font-weight:600">
      <span style="width:7px;height:7px;border-radius:50%;background:var(--ok);display:inline-block"></span>answering on this machine</span>
  </div>

  <div style="flex-grow:1;padding:30px 32px 0;display:flex;justify-content:center">
    <div style="width:100%;max-width:820px;display:flex;flex-direction:column;gap:26px">

      ''' + q("Who is Mr Collins, and why does everyone find him so trying?") + '''

      <div style="display:flex;flex-direction:column;gap:11px">
        ''' + route("answered from the character graph, then the passages behind it") + '''
        <div style="font-size:15.5px;line-height:1.75;color:var(--ink);max-width:70ch">
          <p style="margin:0 0 14px">Mr Collins is a clergyman and the Bennets’ cousin. Under the entail on Longbourn he stands to inherit the estate that Mr Bennet’s five daughters cannot ''' + pref("p. 62") + ''', which is why he arrives in chapter 13 openly intending to choose a wife among them ''' + pref("p. 64") + '''.</p>
          <p style="margin:0 0 14px">He proposes to Elizabeth in chapter 19 and is refused ''' + pref("p. 104") + '''. Three days later he proposes to Charlotte Lucas, who accepts him ''' + pref("p. 121") + ''' — a decision the book treats as prudence rather than affection ''' + pref("p. 123") + '''.</p>
          <p style="margin:0">As for why he grates: the book shows it rather than says it. His deference to his patroness, Lady Catherine de Bourgh, is quoted at length and entirely without irony on his part ''' + pref("p. 66") + ''', and his letter after Lydia’s elopement offers condolence and reproach in the same breath ''' + pref("p. 296") + '''. <span style="color:var(--ink2)">No passage calls him tiresome outright — that reading comes from what he is given to say.</span></p>
        </div>
        <div style="display:flex;align-items:center;gap:14px;padding-top:6px">
          <span class="mono" style="font-size:12.5px;color:var(--ink3)">6 citations · 1.2s</span>
          <a href="#" style="font-size:12.5px;font-weight:600">Show every passage about him</a>
        </div>
      </div>

      <div style="height:1px;background:var(--line)"></div>

      ''' + q("What happens to Elizabeth’s brother?") + '''

      <div style="display:flex;flex-direction:column;gap:11px">
        ''' + route("checked the roster and the household — no match") + '''
        <div class="card" style="padding:20px 22px;background:var(--sunken);border-style:dashed">
          <div style="font-size:15.5px;line-height:1.75;color:var(--ink);max-width:68ch">
            <p style="margin:0 0 12px"><strong>Elizabeth has no brother.</strong> The Bennets have five daughters and no son — which is the entire reason Longbourn is entailed away to Mr Collins ''' + pref("p. 62") + '''.</p>
            <p style="margin:0;color:var(--ink2)">If you have someone else in mind: <strong style="color:var(--ink)">Mr Gardiner</strong> is her uncle ''' + pref("p. 129") + ''', and <strong style="color:var(--ink)">Mr Bingley</strong> becomes her brother-in-law when he marries Jane in chapter 55 ''' + pref("p. 350") + '''.</p>
          </div>
        </div>
        <p style="margin:0;font-size:12px;color:var(--ink3);max-width:60ch">Nothing was invented to fill the gap. When the book does not say, neither does Traverse.</p>
      </div>

      <div style="height:1px;background:var(--line)"></div>

      <div style="display:flex;flex-direction:column;gap:14px;padding-bottom:10px">
        <div class="lbl long">First visit — nothing asked yet</div>
        <div class="card" style="padding:34px 32px;display:flex;flex-direction:column;gap:20px">
          <div>
            <h2 class="serif" style="margin:0;font-size:28px;font-weight:600;letter-spacing:-.02em;line-height:1.2">Ask anything about <em>Pride and Prejudice</em></h2>
            <p style="margin:9px 0 0;font-size:14px;line-height:1.65;color:var(--ink2);max-width:62ch">Every answer carries the pages it came from, and nothing is said that the book does not support. Start with one of these:</p>
          </div>
          <div style="display:flex;flex-direction:column;gap:9px">
          ''' + "".join(
            '<div style="display:flex;align-items:center;gap:13px;padding:13px 16px;border:1px solid var(--line);border-radius:9px;background:var(--surface)">'
            '<div style="flex-grow:1"><div class="serif" style="font-size:15px">' + t + '</div>'
            '<div style="font-size:12px;color:var(--ink3);margin-top:2px">' + s + '</div></div>'
            '<span style="color:var(--ink3)">' + '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>' + '</span></div>'
            for t, s in SUGG) + '''
          </div>
        </div>
      </div>

    </div>
  </div>

  <div style="padding:18px 32px 26px;display:flex;justify-content:center;border-top:1px solid var(--line);background:var(--surface)">
    <div style="width:100%;max-width:820px;display:flex;align-items:center;gap:12px;padding:12px 16px;border:1px solid var(--line);border-radius:11px;background:var(--sunken)">
      <span style="flex-grow:1;font-size:14.5px;color:var(--ink3)">Ask about a character, a connection, or a scene…</span>
      <span class="mono" style="font-size:12px;color:var(--ink3)">up to ch. 61</span>
      <div style="width:30px;height:30px;border-radius:8px;background:var(--accent);color:var(--accentInk);display:flex;align-items:center;justify-content:center">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg></div>
    </div>
  </div>

</main></div></div>'''

dc('Ask.dc.html', ASK_BODY, w=1440, h=1120)

# ───────────────────────────────── canvas layout
CANVAS = {
 "artboards": [
  {"file": "Main.dc.html",           "title": "Shell & foundations", "x": 0,    "y": 0,    "w": 1440, "h": 1500},
  {"file": "Library.dc.html",        "title": "Library",             "x": 1580, "y": 0,    "w": 1440, "h": 1080},
  {"file": "UploadProgress.dc.html", "title": "Adding a book",       "x": 3160, "y": 0,    "w": 1440, "h": 1080},
  {"file": "CharacterList.dc.html",  "title": "Everyone in the book","x": 0,    "y": 1660, "w": 1440, "h": 1190},
  {"file": "CharacterDetail.dc.html","title": "One character",       "x": 1580, "y": 1660, "w": 1440, "h": 1240},
  {"file": "GraphExplorer.dc.html",  "title": "Who knows whom",      "x": 3160, "y": 1660, "w": 1440, "h": 900},
  {"file": "EvidencePanel.dc.html",  "title": "The evidence",        "x": 0,    "y": 3060, "w": 760,  "h": 1080},
  {"file": "Ask.dc.html",            "title": "Ask",                 "x": 900,  "y": 3060, "w": 1440, "h": 1120},
 ],
 "annotations": [
  {"id": "note-direction", "x": 0, "y": -190, "w": 640,
   "text": "Traverse — literary / warm.\nParchment grounds, Literata for anything a reader reads (names, titles, quoted passages), IBM Plex Sans for chrome, IBM Plex Mono for pages and counts. One terracotta accent.\nThe graph is the only screen allowed to be loud."},
  {"id": "note-pageref", "x": 1580, "y": -190, "w": 560,
   "text": "The citation chip is the product.\nEvery stated fact carries one, it is a link rather than a button, and a fact the system cannot anchor to a page is not rendered at all."},
  {"id": "note-evidence", "x": 3160, "y": -190, "w": 560,
   "text": "Two things most tools get wrong, designed for here: a relationship is an arc across the book rather than one flat label, and something a character asserts in dialogue is attributed, never stated as fact."},
 ],
 "launch": {"view": "canvas"},
}
import json as _json
open('canvas.json', 'w').write(_json.dumps(CANVAS, indent=2))
print("wrote canvas.json")
