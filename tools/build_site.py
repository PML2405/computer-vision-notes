#!/usr/bin/env python3
"""Build the AI-scrapable course site.

Takes the NPTEL source folder (Lecture Slides / Transcripts / Assignment Solutions
PDFs + the book PDF whose first pages hold the lecture index) and the handwritten
notes in notes/, and writes into the repo root:

  index.html                      hub page (static HTML, every link visible without JS)
  llms.txt  manifest.json  sitemap.xml  robots.txt  .nojekyll
  1_Assignment_Solutions/  2_Lecture_Slides/  3_Transcripts/     PDFs (copied)
  text/weeks/week-NN.txt          everything for one week in one plain-text file
  text/{notes,slides,transcripts,solutions}/...                  per-file plain-text twins
  text/all-notes.txt              all handwritten notes in one file

Needs: pymupdf (pip install pymupdf) and the `tesseract` CLI (OCR for image-only slides).

  python3 tools/build_site.py "/path/to/computer vision" \
      --base https://pml2405.github.io/computer-vision-notes/
"""
import argparse, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile
from html.parser import HTMLParser
from multiprocessing import Pool
from pathlib import Path

import pymupdf

COURSE = "Computer Vision"
INSTRUCTOR = "Prof. Jayanta Mukhopadhyay"
INSTITUTE = "IIT Kharagpur"
NPTEL_ID = "106105216"
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII"]

# ------------------------------------------------------------------ text helpers

MOJIBAKE = [("â€“", "–"), ("â€”", "—"), ("â€™", "’"), ("â€˜", "‘"), ("â€œ", "“"),
            ("â€\x9d", "”"), ("â€¦", "…"), ("Â€“", "–"), ("Â ", " "), ("Â", "")]


def fix(s):
    for a, b in MOJIBAKE:
        s = s.replace(a, b)
    return s.replace("\x00", "").replace("­", "")


def tidy(s):
    s = "\n".join(l.rstrip() for l in s.splitlines())
    return re.sub(r"\n{3,}", "\n\n", s).strip() + "\n"


def human(n):
    for u in ("B", "KB", "MB", "GB"):
        if n < 1024 or u == "GB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}".replace(".0 ", " ")
        n /= 1024


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ------------------------------------------------------------------ course index

def parse_book_index(book_pdf):
    """Lecture list from the index pages of the full-course transcript book."""
    doc = pymupdf.open(book_pdf)
    toks = []
    for p in range(1, 4):
        toks += [t.strip() for t in fix(doc[p].get_text()).splitlines() if t.strip()]
    weeks, week, i = {}, None, 0
    while i < len(toks):
        t = toks[i]
        m = re.fullmatch(r"Week (\d+)", t)
        if m:
            week = int(m.group(1)); weeks[week] = []; i += 1; continue
        if t.isdigit() and week and i + 2 < len(toks) and toks[i + 2].isdigit():
            weeks[week].append({"n": int(t), "title": toks[i + 1], "book_page": int(toks[i + 2])})
            i += 3; continue
        i += 1
    # the book's "Part" numerals have typos (e.g. Part VI before Part V) -> renumber per topic
    seen = {}
    for w in sorted(weeks):
        for l in weeks[w]:
            t = fix(l["title"]).replace("Imagr", "Image").replace("Dimensional", "Dimension")
            m = re.match(r"(.*?)\s*[–-]?\s*Part(?:\s+\S+)?$", t)
            if m:
                seen[m.group(1)] = seen.get(m.group(1), 0) + 1
                t = f"{m.group(1)} – Part {ROMAN[seen[m.group(1)]]}"
            l["title"] = t
    return weeks


# ------------------------------------------------------------------ PDF -> text

def pdf_pages(path):
    doc = pymupdf.open(path)
    return [fix(p.get_text()) for p in doc], len(doc)


def join_wrapped(text):
    """Re-flow hard-wrapped lines into paragraphs; slide-time markers get their own line."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            out.append("")
        elif re.match(r"\(Refer Slide Time", line):
            out += ["", line, ""]
        else:
            if out and out[-1] != "":
                out[-1] += " " + line
            else:
                out.append(line)
    return "\n".join(out)


def transcript_text(path, lectures, bs, next_bs):
    pages, total = pdf_pages(path)
    front = total - (next_bs - bs)                      # cover + index pages before week content
    starts = {front + (l["book_page"] - bs) + 1: l for l in lectures}   # 1-based pdf page -> lecture
    parts = []
    for pno in range(front + 1, total + 1):
        if pno in starts:
            l = starts[pno]
            parts.append(f"\n\n## Lecture {l['n']} — {l['title']}  (transcript PDF page {pno})\n")
        parts.append(f"[p.{pno}] " + join_wrapped(pages[pno - 1]))
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(parts))
    return body, total, {l["n"]: pno for pno, l in starts.items()}


_doc = None


def _init_doc(path):
    global _doc
    _doc = pymupdf.open(path)


def _ocr_page(i):
    page = _doc[i]
    layer = fix(page.get_text())
    ocr = ""
    if (page.get_images() or len(layer) < 200) and not os.environ.get("CV_SKIP_OCR"):
        with tempfile.TemporaryDirectory() as td:
            png = os.path.join(td, "p.png")
            page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY).save(png)
            r = subprocess.run(["tesseract", png, "stdout", "--psm", "6"], capture_output=True,
                               text=True, env={**os.environ, "OMP_THREAD_LIMIT": "1"})
            ocr = fix(r.stdout)
    return i, layer, ocr


def slide_text(path):
    with Pool(6, initializer=_init_doc, initargs=(path,)) as pool:
        n = len(pymupdf.open(path))
        res = sorted(pool.map(_ocr_page, range(n), chunksize=4))
    out, used_ocr = [], 0
    for i, layer, ocr in res:
        keep = lambda ls: [l.strip() for l in ls if len(re.findall(r"[A-Za-z0-9]", l)) >= 2]
        layer_lines, ocr_lines = keep(layer.splitlines()), keep(ocr.splitlines())
        use_ocr = len("".join(ocr_lines)) > 1.3 * len("".join(layer_lines)) + 20
        used_ocr += use_ocr
        out.append(f"### Slide {i + 1}" + (" (OCR)" if use_ocr else "") + "\n" +
                   "\n".join(ocr_lines if use_ocr else layer_lines))
    return "\n\n".join(out), n, used_ocr


def solution_text(path):
    pages, n = pdf_pages(path)
    clean = []
    for p in pages:
        lines = p.splitlines()
        if lines and lines[-1].strip().isdigit():       # trailing page number
            lines = lines[:-1]
        clean.append("\n".join(lines))
    return "\n".join(clean), n


# ------------------------------------------------------------------ notes HTML -> text

class NotesToText(HTMLParser):
    BLOCK = {"div", "p", "li", "ol", "ul", "table", "section", "h1", "h2", "h3", "h4", "thead", "tbody"}
    VOID = {"br", "hr", "img", "meta", "link", "input"}
    SKIP_TAGS = {"script", "style", "defs", "head", "filter", "marker"}
    SKIP_CLASS = {"margin-rule", "doodle", "backtop", "defs"}
    CLASS_PREFIX = {"lno": "\n\n# ", "lsub": "\n", "quiz": "\n\n### Self-check quiz\n",
                    "ans": "\n   → Answer: ", "banner": "\n\n", "signoff": "\n", "sticky": "\n\n",
                    "worked": "\n\n", "sketch-box": "\n\n", "bubble": "\n"}
    BOLD_CLASS = {"tag", "label", "say", "lead", "def-term"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.lists = [], [], []
        self.svg_depth, self.svg_texts, self.in_svg_text, self.svg_buf = 0, [], False, []
        self.in_lec, self.lec_depth = False, 0

    def skipping(self):
        return any(s[2] for s in self.stack)

    def emit(self, s):
        if not self.skipping():
            self.out.append(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if tag == "svg":
            self.svg_depth += 1
            if self.svg_depth == 1:
                self.svg_texts = []
        if self.svg_depth:
            if tag == "text":
                self.in_svg_text, self.svg_buf = True, []
            if tag != "svg":
                self.stack.append((tag, "", False)); return
        skip = tag in self.SKIP_TAGS or bool(classes & self.SKIP_CLASS) or \
            (tag == "svg" and "defs" in classes)
        if tag in self.VOID:
            self.emit("\n"); return
        pre = suf = ""
        if tag in self.BLOCK:
            pre = "\n"
        if tag in ("h2", "h3", "h4"):
            if tag == "h2" and self.in_lec:
                pre = " — "
            else:
                pre = "\n\n" + "#" * int(tag[1]) + " "
                if tag == "h2" and "section" not in classes and not self.in_lec:
                    pre = "\n\n## "
        if tag in ("b", "strong"):
            pre = suf = "**"
        if tag in ("ol", "ul"):
            self.lists.append([tag, 0])
        if tag == "li" and self.lists:
            l = self.lists[-1]; l[1] += 1
            pre = "\n" + (f"{l[1]}. " if l[0] == "ol" else "- ")
        if tag == "tr":
            pre = "\n| "
        if tag in ("td", "th"):
            suf = " | "
        for c in classes:
            if c in self.CLASS_PREFIX:
                pre += self.CLASS_PREFIX[c]
            if c in self.BOLD_CLASS and tag == "span":
                pre += "**"; suf = "**" + suf
            if c == "num":
                suf = ". " + suf
            if c == "lec-divider":
                self.in_lec, self.lec_depth = True, len(self.stack) + 1
        if tag == "svg":
            skip = skip or "doodle" in classes
            self.stack.append((tag, "", skip)); return
        self.stack.append((tag, suf, skip))
        self.emit(pre)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.svg_depth and tag != "svg":
            if tag == "text" and self.in_svg_text:
                t = re.sub(r"\s+", " ", "".join(self.svg_buf)).strip()
                if t:
                    self.svg_texts.append(t)
                self.in_svg_text = False
            for k in range(len(self.stack) - 1, -1, -1):
                if self.stack[k][0] == tag:
                    del self.stack[k:]; break
            return
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                _, suf, skip = self.stack[k]
                del self.stack[k:]
                if self.in_lec and len(self.stack) < self.lec_depth:
                    self.in_lec = False
                if tag == "svg":
                    self.svg_depth -= 1
                    if self.svg_depth == 0 and not skip and not self.skipping() and self.svg_texts:
                        self.emit("\n[diagram text: " + " | ".join(self.svg_texts) + "]\n")
                    break
                if tag in ("ol", "ul") and self.lists:
                    self.lists.pop()
                if tag == "div" and not any(s[0] == "div" for s in self.stack):
                    pass
                self.emit(suf + ("\n" if tag in self.BLOCK else ""))
                break

    def handle_data(self, data):
        if self.svg_depth:
            if self.in_svg_text:
                self.svg_buf.append(data)
            return
        if self.skipping() or not any(s[0] == "body" for s in self.stack):
            return
        self.emit(re.sub(r"[ \t\r\n]+", " ", data))

    def handle_entityref(self, name):  # pragma: no cover - convert_charrefs handles these
        pass

    def result(self):
        txt = "".join(self.out)
        txt = re.sub(r"[ \t]+\n", "\n", txt)
        txt = re.sub(r"\n[ \t]+(?=\S)", "\n", txt)
        txt = re.sub(r"\*\*\s*\*\*", "", txt)
        txt = re.sub(r"(# LECTURE \d+)\s*\n\s*— ", r"\1 — ", txt)
        txt = re.sub(r"\n{2,}(?=\| )", "\n", txt)
        return tidy(txt)


def notes_text(html_path):
    raw = html_path.read_text(encoding="utf-8")
    raw = re.sub(r"data:[a-z/+\-0-9]+;base64,[A-Za-z0-9+/=]+", "", raw)
    raw = re.sub(r"<script.*?</script>", "", raw, flags=re.S)
    raw = re.sub(r"<style.*?</style>", "", raw, flags=re.S)
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    p = NotesToText()
    p.feed(raw)
    return p.result()


def notes_cover(html_path):
    raw = html_path.read_text(encoding="utf-8")
    raw = re.sub(r"data:[a-z/+\-0-9]+;base64,[A-Za-z0-9+/=]+", "", raw)
    sub = re.search(r'<div class="sub">(.*?)</div>', raw, re.S)
    prof = re.search(r'<div class="prof">(.*?)</div>', raw, re.S)
    clean = lambda s: html.unescape(re.sub(r"<[^>]+>", "", s)).strip() if s else ""
    return clean(sub and sub.group(1)), clean(prof and prof.group(1))


# ------------------------------------------------------------------ main build

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="folder with Lecture Slides/, Transcripts/, Assignment Solutions/ and the book PDF")
    ap.add_argument("--base", default="https://pml2405.github.io/computer-vision-notes/")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--skip-ocr", action="store_true", help="text layer only (fast, for testing)")
    args = ap.parse_args()
    src, out, base = Path(args.src), Path(args.out), args.base.rstrip("/") + "/"

    book = next(src.glob("*.pdf"))
    lectures = parse_book_index(book)
    weeks = sorted(lectures)
    first_pg = {w: lectures[w][0]["book_page"] for w in weeks}
    total_book_pages = len(pymupdf.open(book)) - 4 + 1   # book page numbering ends here (exclusive)

    wk = lambda p: int(re.search(r"Week\s*(\d+)", p.name).group(1))
    titles = {wk(p): re.search(r"Week \d+ - (.*?) - Transcript", p.name).group(1)
              for p in (src / "Transcripts").glob("*.pdf")}

    W = {w: {"week": w, "title": titles[w], "lectures": lectures[w], "files": []} for w in weeks}
    manifest_files = []
    stage = {"slides": {}, "transcript": {}, "solutions": {}, "notes": {}}

    def register(w, kind, label, pdf, txt, pages, extra=None):
        rec = {"week": w, "kind": kind, "label": label, "pdf": pdf, "text": txt, "pages": pages}
        rec.update(extra or {})
        W[w]["files"].append(rec)

    # ---- assignment solutions
    for p in sorted((src / "Assignment Solutions").glob("*.pdf")):
        w = wk(p)
        name = f"Week_{w:02d}_Assignment_Solution"
        (out / "1_Assignment_Solutions").mkdir(parents=True, exist_ok=True)
        shutil.copy(p, out / "1_Assignment_Solutions" / f"{name}.pdf")
        t, n = solution_text(p)
        t = f"# Week {w} — {titles[w]} — assignment solution\n(source: NPTEL, {n} PDF pages; fractions/matrices from the PDF may be flattened in this text)\n\n" + t
        write(out / "text/solutions" / f"{name}.txt", tidy(t))
        stage["solutions"][w] = tidy(t)
        register(w, "solutions", "Assignment solution", f"1_Assignment_Solutions/{name}.pdf", f"text/solutions/{name}.txt", n)
        print("solution", w, n)

    # ---- transcripts
    for p in sorted((src / "Transcripts").glob("*.pdf")):
        w = wk(p)
        name = f"Week_{w:02d}_Transcript"
        (out / "3_Transcripts").mkdir(parents=True, exist_ok=True)
        shutil.copy(p, out / "3_Transcripts" / f"{name}.pdf")
        nxt = first_pg[w + 1] if w + 1 in first_pg else total_book_pages
        body, n, starts = transcript_text(p, lectures[w], first_pg[w], nxt)
        for l in lectures[w]:
            l["transcript_page"] = starts.get(l["n"])
        t = (f"# Week {w} — {titles[w]} — lecture transcript\n"
             f"(source: NPTEL, {n} PDF pages; [p.N] marks the page in the PDF)\n" + body)
        write(out / "text/transcripts" / f"{name}.txt", tidy(t))
        stage["transcript"][w] = tidy(t)
        register(w, "transcript", "Lecture transcript", f"3_Transcripts/{name}.pdf", f"text/transcripts/{name}.txt", n)
        print("transcript", w, n)

    # ---- slides (weeks 4 and 5 share one deck -> copy/extract once)
    by_hash = {}
    for p in sorted((src / "Lecture Slides").glob("*.pdf")):
        # weeks 4 and 5 ship the same deck (bytes differ only in metadata) -> key on size + extracted text
        doc = pymupdf.open(p)
        key = hashlib.sha1((str(p.stat().st_size) + "".join(pg.get_text() for pg in doc)).encode()).hexdigest()
        by_hash.setdefault(key, []).append(p)
    for group in by_hash.values():
        ws = sorted({wk(p) for p in group})
        p = group[0]
        part = re.search(r"\(Part (\d+)\)", p.name)
        tag = "-".join(f"{w:02d}" for w in ws)
        name = f"Week_{tag}_Slides" + (f"_Part{part.group(1)}" if part else "")
        (out / "2_Lecture_Slides").mkdir(parents=True, exist_ok=True)
        shutil.copy(p, out / "2_Lecture_Slides" / f"{name}.pdf")
        if args.skip_ocr:
            os.environ["CV_SKIP_OCR"] = "1"
        t, n, used = slide_text(p)
        head = (f"# {'Weeks ' + ' & '.join(map(str, ws)) if len(ws) > 1 else 'Week ' + str(ws[0])} — lecture slides"
                + (f" (part {part.group(1)})" if part else "") +
                f"\n(source: NPTEL, {n} slides; text layer, plus OCR on {used} image-heavy slides — "
                "OCR can contain errors and equations may be garbled; the transcript and notes are authoritative)\n\n")
        write(out / "text/slides" / f"{name}.txt", tidy(head + t))
        for w in ws:
            stage["slides"].setdefault(w, []).append(tidy(head + t))
            register(w, "slides", "Lecture slides" + (f" (part {part.group(1)})" if part else ""),
                     f"2_Lecture_Slides/{name}.pdf", f"text/slides/{name}.txt", n,
                     {"shared_with_weeks": ws} if len(ws) > 1 else None)
        print("slides", ws, n, "ocr", used)

    # ---- handwritten notes
    all_notes = []
    for w in weeks:
        f = out / "notes" / f"week{w}_notes.html"
        if not f.exists():
            continue
        sub, prof = notes_cover(f)
        name = f"Week_{w:02d}_Notes"
        t = (f"# Week {w} — {titles[w]} — study notes\n"
             f"({sub}; {prof}. Re-taught-from-scratch notes written from the slides + transcript; "
             f"math is LaTeX between $...$ / $$...$$. Pretty version: {base}notes/week{w}_notes.html)\n\n"
             + notes_text(f))
        write(out / "text/notes" / f"{name}.txt", tidy(t))
        stage["notes"][w] = tidy(t)
        all_notes.append(tidy(t))
        register(w, "notes", "Study notes", f"notes/week{w}_notes.html", f"text/notes/{name}.txt", None,
                 {"bytes_html": f.stat().st_size})
        print("notes", w, len(t))
    write(out / "text/all-notes.txt",
          f"# {COURSE} (NPTEL) — all study notes, weeks {', '.join(str(w) for w in stage['notes'])}\n\n" +
          "\n\n=====\n\n".join(all_notes))

    # ---- combined per-week files
    order = {"notes": 0, "solutions": 1, "slides": 2, "transcript": 3}
    for w in weeks:
        d = W[w]
        lec_lines = "\n".join(
            f"  - Lecture {l['n']}: {l['title']}" + (f" (transcript p.{l['transcript_page']})" if l.get("transcript_page") else "")
            for l in d["lectures"])
        sections = []
        for kind, label in (("notes", "STUDY NOTES"), ("solutions", "ASSIGNMENT SOLUTION"),
                            ("slides", "LECTURE SLIDES"), ("transcript", "LECTURE TRANSCRIPT")):
            parts = stage[kind].get(w)
            if parts is None:
                continue
            parts = parts if isinstance(parts, list) else [parts]
            sections.append(f"\n\n{'=' * 78}\nPART: {label}\n{'=' * 78}\n\n" + "\n\n".join(parts))
        avail = [l for k, l in (("notes", "study notes"), ("solutions", "assignment solution"),
                                ("slides", "slides"), ("transcript", "transcript")) if stage[k].get(w)]
        head = (f"{COURSE} (NPTEL {NPTEL_ID}, {INSTITUTE}, {INSTRUCTOR})\n"
                f"WEEK {w}: {d['title']}\nLectures:\n{lec_lines}\n\n"
                f"This file concatenates, in order: {', '.join(avail)}.\n"
                f"Hub: {base}")
        d["week_text"] = f"text/weeks/week-{w:02d}.txt"
        write(out / d["week_text"], tidy(head + "".join(sections)))

    # ---- manifest / llms / sitemap / robots
    for w in weeks:
        for r in sorted(W[w]["files"], key=lambda r: order[r["kind"]]):
            r["bytes"] = (out / r["pdf"]).stat().st_size
            r["text_bytes"] = (out / r["text"]).stat().st_size
            r["week_text"] = W[w]["week_text"]
            manifest_files.append({**r, "pdf": base + r["pdf"], "text": base + r["text"], "week_text": base + r["week_text"]})
    (out / "manifest.json").write_text(json.dumps({
        "course": f"{COURSE} (NPTEL {NPTEL_ID})", "instructor": INSTRUCTOR, "institute": INSTITUTE, "base": base,
        "all_notes_text": base + "text/all-notes.txt",
        "weeks": [{"week": w, "title": W[w]["title"], "week_text": base + W[w]["week_text"],
                   "lectures": W[w]["lectures"]} for w in weeks],
        "files": manifest_files}, indent=1, ensure_ascii=False), encoding="utf-8")

    L = [f"# {COURSE} — NPTEL {NPTEL_ID} study material ({INSTITUTE}, {INSTRUCTOR})", "",
         "> Lecture slides, lecture transcripts, assignment solutions and handwritten-style study notes for "
         "weeks 1-12 of the NPTEL Computer Vision course. Every PDF has a plain-text copy; the per-week "
         "files below concatenate everything for that week, so read the text files rather than the PDFs. "
         "Slide text is the PDF text layer plus OCR, so equations there may be garbled; the transcript and "
         "the study notes are the cleanest sources.", "",
         f"- Website: {base}", f"- Manifest (JSON): {base}manifest.json",
         f"- All study notes in one file: {base}text/all-notes.txt", ""]
    for w in weeks:
        d = W[w]
        L += [f"## Week {w}: {d['title']}", "",
              "Lectures: " + "; ".join(f"{l['n']} {l['title']}" for l in d["lectures"]), "",
              f"- [Everything for week {w} (one text file)]({base}{d['week_text']})"]
        for r in sorted(d["files"], key=lambda r: order[r["kind"]]):
            sz = f", {r['pages']} pages" if r["pages"] else ""
            L.append(f"- {r['label']}: [text]({base}{r['text']}) · [{'page' if r['kind'] == 'notes' else 'PDF'}]({base}{r['pdf']}){sz}")
        L.append("")
    write(out / "llms.txt", "\n".join(L))

    urls = [base, base + "llms.txt", base + "manifest.json", base + "text/all-notes.txt"]
    urls += [base + W[w]["week_text"] for w in weeks]
    urls += [base + r["text"] for w in weeks for r in W[w]["files"]]
    urls += [base + r["pdf"] for w in weeks for r in W[w]["files"]]
    write(out / "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "\n".join(f"  <url><loc>{html.escape(u)}</loc></url>" for u in dict.fromkeys(urls)) + "\n</urlset>\n")
    write(out / "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {base}sitemap.xml\n")
    (out / ".nojekyll").write_text("")

    from build_hub import write_hub          # hub page lives in its own module
    write_hub(out, base, W, weeks, {"course": COURSE, "instructor": INSTRUCTOR, "institute": INSTITUTE, "id": NPTEL_ID})
    print("done")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
