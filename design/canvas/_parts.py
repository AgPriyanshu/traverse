ICON = {
 "logo":'<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="6" r="2.2"/><circle cx="12" cy="18.5" r="2.2"/><path d="M7.2 6h9.6"/><path d="M6.4 8.1 10.6 16.6"/><path d="M17.6 8.1 13.4 16.6"/></svg>',
 "book":'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
 "users":'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
 "graph":'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="6" r="2.2"/><circle cx="12" cy="18.5" r="2.2"/><path d="M7.2 6h9.6"/><path d="M6.4 8.1 10.6 16.6"/><path d="M17.6 8.1 13.4 16.6"/></svg>',
 "ask":'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
 "review":'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11.5l2.5 2.5L21 4.5"/><path d="M21 12.5V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
 "ops":'<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
 "search":'<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>',
 "chev":'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>',
 "up":'<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/></svg>',
 "tick":'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>',
 "warn":'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
 "redo":'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/></svg>',
 "spin":'<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 3a9 9 0 1 0 9 9" opacity=".85"/></svg>',
}

def topbar(project="Pride and Prejudice", crumb=None):
    return f'''<header style="display:flex;align-items:center;gap:18px;height:56px;padding:0 20px;border-bottom:1px solid var(--line);background:var(--surface);flex:none">
  <div style="display:flex;align-items:center;gap:9px">{ICON["logo"]}<span class="serif" style="font-size:17px;font-weight:600;letter-spacing:-.01em">Traverse</span></div>
  <div style="width:1px;height:22px;background:var(--line)"></div>
  <div style="display:flex;align-items:center;gap:8px;padding:5px 10px;border:1px solid var(--line);border-radius:7px;background:var(--sunken)">
    <span class="serif" style="font-size:14px">{project}</span><span style="color:var(--ink3);display:flex">{ICON["chev"]}</span></div>
  <div style="flex-grow:1"></div>
  <div style="display:flex;align-items:center;gap:8px;width:250px;padding:6px 11px;border:1px solid var(--line);border-radius:7px;background:var(--sunken);color:var(--ink3)">{ICON["search"]}<span style="font-size:13px">Search characters, passages…</span></div>
  <div style="width:29px;height:29px;border-radius:50%;background:var(--accentSoft);color:var(--accent);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600">AR</div>
</header>'''

def sidenav(active="Characters"):
    items = [("Library","book"),("Characters","users"),("Graph","graph"),("Ask","ask"),("Review","review"),("Ops","ops")]
    rows = "".join(
      f'<div class="navit{" on" if n==active else ""}">{ICON[i]}<span>{n}</span>'
      + ('<span style="margin-left:auto;font-size:12px;font-weight:600;padding:1px 6px;border-radius:999px;background:var(--accent);color:var(--accentInk)">7</span>' if n=="Review" else '')
      + '</div>' for n,i in items)
    return f'''<nav style="width:212px;flex:none;border-right:1px solid var(--line);background:var(--surface);padding:16px 12px;display:flex;flex-direction:column;gap:2px">
  <div class="lbl" style="padding:4px 12px 8px">Project</div>{rows}
  <div style="flex-grow:1"></div>
  <div style="padding:10px 12px;border-top:1px solid var(--line);color:var(--ink3);font-size:12.5px;line-height:1.5">Running locally<br>Qwen3-8B · no data leaves this machine</div>
</nav>'''

def pref(txt, cls=""):
    return f'<span class="pref {cls}">{txt}</span>'


def spine(colors):
    """One band per book in the project — a standalone gets one. Data, not an accent rule."""
    n = len(colors)
    bars = "".join(
        f'<div style="flex-grow:1;background:{c}"></div>'
        + ('<div style="height:1px;background:rgba(0,0,0,.22)"></div>' if i < n - 1 else '')
        for i, c in enumerate(colors))
    return (f'<div title="{n} book' + ('s' if n > 1 else '') + f' in this project" '
            'style="display:flex;flex-direction:column;width:9px;flex:none;'
            'box-shadow:inset -2px 0 3px -1px rgba(0,0,0,.28)">' + bars + '</div>')
