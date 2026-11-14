"""Tables in text PDFs, read from pypdf's layout text (columns kept as character positions). Pure functions: no network.

A table row starts on an "anchor" line (a line the caller recognises, e.g. a serial number, or two dates). Its other lines are the
wrapped text of its cells. Column positions come from the anchor line with the most cells; each chunk of text (separated by 2 or
more spaces) goes to the nearest column.

  mode "below":   the lines after an anchor belong to it (text wraps downwards). Lines before the first anchor of a page continue
                  the last row of the page before.
  mode "nearest": a cell's text is centred on the anchor line, so lines above and below belong to the nearest anchor (a blank
                  line or a break line ends a row).
"""
import io
import re

_CHUNK = re.compile(r"\S+(?: \S+)*")


def layout_pages(data):
    """Layout text of each page of a PDF (bytes)."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(data), strict=False)
    out = []
    for p in reader.pages:
        try:
            out.append(p.extract_text(extraction_mode="layout") or "")
        except Exception:                      # a damaged page: keep the others
            out.append("")
    return out


def chunks(line):
    """[(start column, text)] of the parts of a line separated by 2 or more spaces."""
    return [(m.start(), m.group(0)) for m in _CHUNK.finditer(line)]


def _cols(anchor_lines):
    best = max(anchor_lines, key=lambda ln: len(chunks(ln)), default="")
    return [x for x, _ in chunks(best)]


def _nearest(cols, x):
    return min(range(len(cols)), key=lambda i: abs(cols[i] - x))


def rows(pages, is_anchor, mode="below", is_break=None, start=None):
    """Rows of a table as lists of cell texts (one per column of the fullest anchor line).

    pages: layout text per page. is_anchor(line) -> bool. is_break(line) -> bool: a line that is not table content (headers,
    section titles, page footers). start(line) -> bool: the table starts after this line on each page (e.g. the column header);
    lines before it are ignored. Without `start`, a page's lines are all candidates.
    """
    is_break = is_break or (lambda ln: False)
    lines, page_of = [], []                        # table content lines; None for a blank or break line, "PAGE" between pages
    for pi, text in enumerate(pages):
        on = start is None
        for ln in text.splitlines():
            if not on:
                on = bool(start(ln))
                continue
            lines.append(None if not ln.strip() or is_break(ln) else ln)
            page_of.append(pi)
        lines.append("PAGE")
        page_of.append(pi)
    anchors = [i for i, ln in enumerate(lines) if ln not in (None, "PAGE") and is_anchor(ln)]
    if not anchors:
        return []
    every = _cols([lines[i] for i in anchors])
    by_page = {}                                   # column positions of each page (the layout can shift between pages)
    for i in anchors:
        by_page.setdefault(page_of[i], []).append(lines[i])
    page_cols = {pg: _cols(lns) for pg, lns in by_page.items()}
    groups = {a: [a] for a in anchors}
    if mode == "below":
        cur = None
        for i, ln in enumerate(lines):
            if i in groups:
                cur = i
            elif ln is None:
                continue                            # blank or break: a wrapped cell can go on after a blank line
            elif ln == "PAGE":
                continue
            elif cur is not None:
                groups[cur].append(i)
    else:
        aset = set(anchors)
        for i, ln in enumerate(lines):
            if ln in (None, "PAGE") or i in aset:
                continue
            best, dist = None, None
            for step in (-1, 1):                    # walk up and down to the first anchor, stop at a blank or break line
                j = i + step
                while 0 <= j < len(lines) and lines[j] not in (None, "PAGE") and j not in aset:
                    j += step
                if 0 <= j < len(lines) and j in aset:
                    d = abs(j - i)
                    if dist is None or d < dist or (d == dist and step == -1):
                        best, dist = j, d
            if best is not None:
                groups[best].append(i)
    out = []
    for a in anchors:
        cols = page_cols.get(page_of[a], every)
        cells = [[] for _ in cols]
        for i in sorted(groups[a]):
            here = page_cols.get(page_of[i], every)
            for x, txt in chunks(lines[i]):
                k = _nearest(here, x)
                cells[min(k, len(cols) - 1)].append(txt)
        out.append([" ".join(c).strip() for c in cells])
    return out


def joined(cells):
    """The cells of a row as one string, in column order."""
    return re.sub(r"\s+", " ", " ".join(c for c in cells if c)).strip()
