"""Hub page (index.html) for the course site. Called from build_site.py.

Static HTML: every link is in the markup, so a crawler that does not run JavaScript
(ChatGPT / Claude link fetchers) sees the full file list. JS only adds filter + search + copy.
"""
import html
from pathlib import Path

KIND_LABEL = {"notes": "Study notes", "solutions": "Assignment solution",
              "slides": "Lecture slides", "transcript": "Lecture transcript"}
ORDER = ["notes", "solutions", "slides", "transcript"]
e = html.escape


def human(n):
    for u in ("B", "KB", "MB"):
        if n < 1024 or u == "MB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}".replace(".0 ", " ")
        n /= 1024


def file_row(out, r):
    text_size = human((out / r["text"]).stat().st_size)
    pdf_size = human((out / r["pdf"]).stat().st_size)
    is_html = r["pdf"].endswith(".html")
    pages = f" · {r['pages']} pages" if r.get("pages") else ""
    shared = ""
    if r.get("shared_with_weeks"):
        shared = " · shared by weeks " + " &amp; ".join(map(str, r["shared_with_weeks"]))
    return (f'<li class="file" data-kind="{r["kind"]}"><div class="info"><span class="kind">{e(r["label"])}</span>'
            f'<span class="meta">{pages[3:] if pages else ""}{shared}</span></div>'
            f'<div class="links"><a class="pri" href="{r["text"]}">Text <small>{text_size}</small></a>'
            f'<a href="{r["pdf"]}">{"Page" if is_html else "PDF"} <small>{pdf_size}</small></a></div></li>')


def write_hub(out, base, W, weeks, meta):
    n_lec = sum(len(W[w]["lectures"]) for w in weeks)
    n_files = sum(len(W[w]["files"]) for w in weeks)
    n_notes = sum(1 for w in weeks for r in W[w]["files"] if r["kind"] == "notes")
    total = sum((out / r[k]).stat().st_size for w in weeks for r in W[w]["files"] for k in ("pdf", "text"))

    sections = []
    for w in weeks:
        d = W[w]
        lec = "".join(
            f'<li><a href="3_Transcripts/Week_{w:02d}_Transcript.pdf#page={l["transcript_page"]}">'
            f'<b>{l["n"]}</b> {e(l["title"].split(" – Part")[0])}'
            f'{(" <i>" + e("Part " + l["title"].split("Part ")[-1]) + "</i>") if "Part " in l["title"] else ""}</a></li>'
            for l in d["lectures"])
        rows = "".join(file_row(out, r) for r in sorted(d["files"], key=lambda r: ORDER.index(r["kind"])))
        missing = "" if any(r["kind"] == "notes" for r in d["files"]) else \
            '<li class="file note-missing" data-kind="notes"><div class="info"><span class="kind">Study notes</span><span class="meta">not written yet</span></div></li>'
        first, last = d["lectures"][0]["n"], d["lectures"][-1]["n"]
        sections.append(f'''
<section class="week" id="week-{w}" data-search="{e((d["title"] + " " + " ".join(l["title"] for l in d["lectures"])).lower())}">
  <header>
    <a class="up" href="#weeks" aria-label="Back to week list">↑ weeks</a>
    <h2><span class="wk">Week {w}</span> {e(d["title"])}</h2>
    <p class="sub">Lectures {first}–{last}</p>
    <a class="all" href="{d["week_text"]}">Everything for week {w}, one text file <small>{human((out / d["week_text"]).stat().st_size)}</small></a>
  </header>
  <ul class="files">{rows}{missing}</ul>
  <details><summary>Lecture list (jump into the transcript PDF)</summary><ol class="lecs">{lec}</ol></details>
</section>''')

    page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#fbfaf7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#16151b" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="CV Notes">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="apple-touch-icon.png" type="image/png">
<title>Computer Vision (NPTEL) — Slides, Transcripts, Solutions &amp; Notes</title>
<meta name="description" content="NPTEL Computer Vision ({meta["institute"]}, {meta["instructor"]}): lecture slides, transcripts, assignment solutions and handwritten-style study notes for weeks 1-12, each with a plain-text copy for ChatGPT / Claude.">
<link rel="alternate" type="text/plain" href="llms.txt" title="llms.txt">
<link rel="canonical" href="{base}">
<script type="application/ld+json">{{"@context":"https://schema.org","@type":"Course","name":"Computer Vision (NPTEL {meta["id"]})","provider":{{"@type":"CollegeOrUniversity","name":"{meta["institute"]}"}},"instructor":{{"@type":"Person","name":"{meta["instructor"]}"}},"url":"{base}"}}</script>
<style>
:root{{--bg:#fbfaf7;--ink:#1e1d24;--mute:#6a6877;--line:#e4e1d8;--card:#fff;--accent:#5b4bdb;--accent-ink:#fff;--tint:#f1eefc;--ok:#1d7a4d}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16151b;--ink:#ecebf2;--mute:#9b99aa;--line:#2c2a36;--card:#1e1d26;--accent:#9d90ff;--accent-ink:#16151b;--tint:#26233a;--ok:#5fd29a}}}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%;text-size-adjust:100%;scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-tap-highlight-color:transparent;touch-action:manipulation}}
main{{max-width:880px;margin:0 auto;padding:32px max(16px,env(safe-area-inset-right)) calc(64px + env(safe-area-inset-bottom)) max(16px,env(safe-area-inset-left))}}
h1{{font-size:clamp(1.7rem,4vw,2.3rem);line-height:1.15;margin:0 0 6px}}
.lede{{color:var(--mute);margin:0 0 20px}}
.stats{{display:flex;flex-wrap:wrap;gap:8px 18px;margin:0 0 24px;padding:0;list-style:none;font-size:.9rem;color:var(--mute)}}
.stats b{{color:var(--ink)}}
.ai{{background:var(--tint);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:26px}}
.ai h2{{margin:0 0 6px;font-size:1.05rem}}
.ai p{{margin:6px 0}}
.copyrow{{display:flex;gap:8px;flex-wrap:wrap;align-items:stretch;margin:8px 0}}
.copyrow code{{flex:1 1 260px;min-width:0;overflow-wrap:anywhere;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:.82rem;line-height:1.4;user-select:all;-webkit-user-select:all}}
button{{font:inherit;cursor:pointer;border-radius:10px;border:1px solid var(--accent);background:var(--accent);color:var(--accent-ink);padding:8px 16px;min-height:44px}}
.weeknav{{display:grid;grid-template-columns:repeat(12,1fr);gap:6px;margin:0 0 18px;scroll-margin-top:12px}}
.weeknav a{{display:flex;align-items:center;justify-content:center;min-height:44px;border:1px solid var(--line);border-radius:10px;background:var(--card);text-decoration:none;font-weight:600}}
.searchrow{{margin:0 0 12px}}
.pick{{display:block;font-weight:600;margin:10px 0 6px}}
select{{width:100%;font:inherit;font-size:16px;min-height:44px;padding:8px 36px 8px 12px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);-webkit-appearance:none;appearance:none;background-image:linear-gradient(45deg,transparent 50%,var(--mute) 50%),linear-gradient(135deg,var(--mute) 50%,transparent 50%);background-position:calc(100% - 20px) 50%,calc(100% - 14px) 50%;background-size:6px 6px,6px 6px;background-repeat:no-repeat}}
.alt{{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 8px}}
.alt a{{display:inline-flex;align-items:center;min-height:44px;padding:0 14px;border:1px solid var(--line);border-radius:10px;background:var(--card);text-decoration:none}}
input[type=search]{{width:100%;font:inherit;font-size:16px;min-height:44px;padding:8px 12px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);-webkit-appearance:none;appearance:none}}
.tools{{margin:0 0 14px;position:sticky;top:0;background:var(--bg);padding:8px 0;z-index:2;border-bottom:1px solid var(--line)}}
.tabs{{display:flex;gap:6px;overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:none}}
.tabs::-webkit-scrollbar{{display:none}}
.tabs button{{flex:0 0 auto;background:transparent;color:var(--ink);border-color:var(--line)}}
.tabs button[aria-pressed=true]{{background:var(--accent);color:var(--accent-ink);border-color:var(--accent)}}
.week{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 14px;scroll-margin-top:64px;position:relative}}
.up{{position:absolute;top:14px;right:16px;font-size:.78rem;color:var(--mute);text-decoration:none;padding:13px 6px;top:2px}}
.week h2{{margin:0;font-size:1.15rem}}
.wk{{display:inline-block;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;background:var(--tint);color:var(--accent);border-radius:6px;padding:2px 7px;margin-right:6px;vertical-align:middle}}
.sub{{margin:2px 0 8px;color:var(--mute);font-size:.88rem}}
a{{color:var(--accent)}}
.all{{display:inline-block;font-weight:600;text-decoration:none;border:1px solid var(--accent);border-radius:10px;padding:10px 14px;margin-bottom:8px}}
.all small,.links small{{font-weight:400;color:var(--mute);margin-left:3px}}
.files{{list-style:none;margin:0;padding:0}}
.file{{display:flex;gap:6px 12px;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--line)}}
.info{{display:flex;flex-direction:column;min-width:0}}
.kind{{font-weight:600}}
.meta{{color:var(--mute);font-size:.82rem}}
.links{{display:flex;gap:8px;flex:0 0 auto}}
.links a{{display:inline-flex;align-items:center;gap:4px;min-height:44px;padding:0 14px;border:1px solid var(--line);border-radius:10px;text-decoration:none;white-space:nowrap}}
.links a.pri{{border-color:var(--accent);font-weight:600}}
.note-missing .meta{{font-style:italic}}
details{{margin-top:8px;font-size:.92rem}}
summary{{cursor:pointer;color:var(--mute);display:flex;align-items:center;min-height:44px}}
.lecs{{margin:0;padding-left:0;list-style:none;columns:2 300px}}
.lecs li{{break-inside:avoid}}
.lecs a{{display:block;padding:12px 0;text-decoration:none}}
.lecs i{{color:var(--mute);font-size:.85em}}
.hide{{display:none!important}}
footer{{margin-top:30px;color:var(--mute);font-size:.85rem}}
footer a{{display:inline-block;margin-right:6px;padding:13px 6px}}
#empty{{display:none;color:var(--mute);padding:20px 0}}
@media (max-width:600px){{
  main{{padding-top:20px}}
  .lede{{font-size:.95rem}}
  .stats{{gap:2px 14px;font-size:.82rem;margin-bottom:16px}}
  .ai{{padding:14px}}
  .ai p{{font-size:.95rem}}
  .copyrow code{{flex-basis:100%}}
  .copyrow button{{flex:1 1 100%}}
  .weeknav{{grid-template-columns:repeat(6,1fr)}}
  .week{{padding:14px 14px 8px}}
  .week h2{{font-size:1.08rem;padding-right:58px}}
  .all{{display:block;text-align:center}}
  .file{{flex-direction:column;align-items:stretch;gap:6px}}
  .info{{flex-direction:row;justify-content:space-between;align-items:baseline;gap:8px}}
  .links{{display:grid;grid-template-columns:1fr 1fr}}
  .links a{{justify-content:center}}
  .note-missing{{padding:12px 0}}
}}
@media (hover:hover){{.links a:hover,.weeknav a:hover{{border-color:var(--accent)}}}}
</style>
</head>
<body>
<main>
<h1>Computer Vision — NPTEL</h1>
<p class="lede">{meta["institute"]} · {meta["instructor"]} · course {meta["id"]}. Lecture slides, lecture transcripts, assignment solutions and re-taught study notes, for all 12 weeks.</p>
<ul class="stats"><li><b>12</b> weeks</li><li><b>{n_lec}</b> lectures</li><li><b>{n_files}</b> files, each with a plain-text copy</li><li><b>{n_notes}</b> weeks of study notes</li><li><b>{human(total)}</b> in total</li></ul>

<div class="ai" id="ai">
  <h2>Asking ChatGPT or Claude about this course</h2>
  <p>Paste one of these links into the chat and ask your question — no need to upload anything. The text files are plain text, so the AI can read them directly (the PDFs are only there for you).</p>
  <label class="pick" for="wsel">Which week is your doubt from?</label>
  <select id="wsel" aria-label="Pick a week for the link">{"".join(f'<option value="{w:02d}">Week {w} — {e(W[w]["title"])}</option>' for w in weeks)}</select>
  <div class="copyrow"><code id="u1">{base}text/weeks/week-01.txt</code><button type="button" data-copy="u1">Copy link</button></div>
  <p class="sub">↑ One week = notes + assignment solution + slides + transcript in one file.</p>
  <div class="copyrow"><code id="u2">{base}llms.txt</code><button type="button" data-copy="u2">Copy link</button></div>
  <p class="sub">↑ The index of everything, for when you do not know which week the doubt is from.</p>
  <div class="alt"><a href="{base}text/all-notes.txt">All study notes, one file</a><a href="manifest.json">manifest.json</a></div>
  <p class="sub">Example: <i>“Read {base}text/weeks/week-03.txt and explain how the camera matrix P is decomposed into K, R and t, with the assignment's Q2 as an example.”</i></p>
</div>

<nav class="weeknav" id="weeks" aria-label="Jump to week">{"".join(f'<a href="#week-{w}" data-week="{w}">{w}</a>' for w in weeks)}</nav>

<div class="searchrow"><input type="search" id="q" placeholder="Search topics, e.g. homography" aria-label="Search weeks and lectures" enterkeyhint="search" autocomplete="off" autocapitalize="off" spellcheck="false"></div>

<div class="tools">
  <div class="tabs" role="group" aria-label="Filter by file type">
    <button type="button" data-filter="all" aria-pressed="true">All</button>
    <button type="button" data-filter="notes" aria-pressed="false">Notes</button>
    <button type="button" data-filter="slides" aria-pressed="false">Slides</button>
    <button type="button" data-filter="transcript" aria-pressed="false">Transcripts</button>
    <button type="button" data-filter="solutions" aria-pressed="false">Solutions</button>
  </div>
</div>

{"".join(sections)}
<p id="empty">Nothing matches that search.</p>

<footer>
  <p>Lecture numbers follow the NPTEL transcript book. Slide text is the PDF text layer plus OCR, so equations can be garbled there; the transcripts and study notes are the cleanest sources. Weeks 4 and 5 share one slide deck.</p>
  <p><a href="llms.txt">llms.txt</a><a href="manifest.json">manifest.json</a><a href="sitemap.xml">sitemap.xml</a><a href="notes/index.html">Notes (original notebook view)</a><a href="https://github.com/PML2405/computer-vision-notes">GitHub</a></p>
</footer>
</main>
<script>
(function(){{
  var filter='all', q='';
  function apply(){{
    var shown=0;
    document.querySelectorAll('.week').forEach(function(w){{
      var match=!q||w.dataset.search.indexOf(q)>-1;
      w.classList.toggle('hide',!match);
      var chip=document.querySelector('.weeknav [data-week="'+w.id.slice(5)+'"]'); if(chip) chip.classList.toggle('hide',!match);
      w.querySelectorAll('.file').forEach(function(f){{f.classList.toggle('hide',filter!=='all'&&f.dataset.kind!==filter)}});
      var all=w.querySelector('.all'); if(all) all.classList.toggle('hide',filter!=='all');
      if(match) shown++;
    }});
    document.getElementById('empty').style.display=shown?'none':'block';
  }}
  document.querySelectorAll('[data-filter]').forEach(function(b){{b.addEventListener('click',function(){{
    filter=b.dataset.filter;
    document.querySelectorAll('[data-filter]').forEach(function(x){{x.setAttribute('aria-pressed',x===b)}});apply();}})}});
  document.getElementById('q').addEventListener('input',function(e){{q=e.target.value.trim().toLowerCase();apply();}});
  var sel=document.getElementById('wsel');
  if(sel) sel.addEventListener('change',function(){{document.getElementById('u1').textContent='{base}text/weeks/week-'+sel.value+'.txt';}});
  document.querySelectorAll('[data-copy]').forEach(function(b){{b.addEventListener('click',function(){{
    var t=document.getElementById(b.dataset.copy).textContent;
    (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){{b.textContent='Copied ✓';setTimeout(function(){{b.textContent='Copy link'}},1500)}},function(){{
      var r=document.createRange();r.selectNodeContents(document.getElementById(b.dataset.copy));var s=getSelection();s.removeAllRanges();s.addRange(r);}});}})}});
}})();
</script>
</body>
</html>
'''
    (out / "index.html").write_text(page, encoding="utf-8")
    write_icon(out / "apple-touch-icon.png")


def write_icon(path):
    """180x180 home-screen icon (iOS 'Add to Home Screen') rendered from an inline SVG."""
    import pymupdf
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" width="180" height="180" viewBox="0 0 180 180">'
           b'<rect width="180" height="180" fill="#5b4bdb"/>'
           b'<rect x="38" y="46" width="104" height="88" rx="14" fill="none" stroke="#fff" stroke-width="9"/>'
           b'<circle cx="90" cy="90" r="22" fill="none" stroke="#fff" stroke-width="9"/>'
           b'<circle cx="90" cy="90" r="7" fill="#fff"/><rect x="62" y="34" width="26" height="14" rx="5" fill="#fff"/></svg>')
    doc = pymupdf.open(stream=svg, filetype="svg")
    pdf = pymupdf.open("pdf", doc.convert_to_pdf())
    pdf[0].get_pixmap(dpi=72).save(str(path))
