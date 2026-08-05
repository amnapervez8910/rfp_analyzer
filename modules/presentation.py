import re
from datetime import date, datetime, timedelta, timezone
from html import escape

def _pick_category_icon(name: str) -> str:
    """Pick a fitting icon for a parent category based on keywords in its name."""
    n = name.lower()
    if any(k in n for k in ["technical", "tech", "engineering", "system", "solution"]):
        return "🔧"
    if any(k in n for k in ["financial", "pricing", "price", "cost", "budget", "payment"]):
        return "💰"
    if any(k in n for k in ["compliance", "admin", "form", "certificat", "legal"]):
        return "📑"
    if any(k in n for k in ["submission", "cover", "envelope"]):
        return "📥"
    if any(k in n for k in ["security", "cyber", "access", "data protection"]):
        return "🔐"
    if any(k in n for k in ["report", "documentation", "record"]):
        return "📊"
    if any(k in n for k in ["staff", "personnel", "team", "resume", "resourc"]):
        return "👥"
    if any(k in n for k in ["contract", "terms", "agreement"]):
        return "📜"
    if any(k in n for k in ["timeline", "schedule", "implementation", "project management"]):
        return "🗓️"
    if any(k in n for k in ["survey", "site"]):
        return "📍"
    return "🗂️"


def _normalize_requirement_type(value: str, *context: str) -> str:
    """Return a clear label without treating an unspecified item as optional."""
    label = (value or '').strip().casefold()
    source = ' '.join(str(item or '') for item in context).casefold()
    if label == 'optional' or any(term in source for term in (' optional', 'at bidder discretion', 'may submit', 'if desired')):
        return 'Optional'
    return 'Mandatory'


def _explicit_deadline_date(deadline: str):
    """Parse only unambiguous, absolute calendar dates; never guess relative dates."""
    value = (deadline or '').strip()
    lower = value.casefold()
    if not value or any(term in lower for term in ('not specified', 'conditional', 'within ', 'after ', 'before notice', 'tbd', 'to be determined')):
        return None
    match = re.search(r'\b(20\d{2})-(\d{1,2})-(\d{1,2})\b', value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    cleaned = re.sub(r'(?<=\d)(st|nd|rd|th)\b', '', value, flags=re.IGNORECASE)
    patterns = (
        (r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{1,2},?\s+20\d{2}\b',
         ('%B %d, %Y', '%b %d, %Y', '%B %d %Y', '%b %d %Y')),
        (r'\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+20\d{2}\b',
         ('%d %B %Y', '%d %b %Y')),
    )
    for regex, formats in patterns:
        found = re.search(regex, cleaned, flags=re.IGNORECASE)
        if not found:
            continue
        candidate = found.group(0)
        for fmt in formats:
            try:
                return datetime.strptime(candidate.title(), fmt).date()
            except ValueError:
                pass
    # Numeric M/D/YYYY or MM/DD/YYYY (US convention, matches these RFPs'
    # "7/16/2026" style dates). Day-first is tried as a fallback only if
    # month-first is not a valid calendar date, to stay unambiguous.
    numeric = re.search(r'\b(\d{1,2})/(\d{1,2})/(20\d{2})\b', value)
    if numeric:
        a, b, year = int(numeric.group(1)), int(numeric.group(2)), int(numeric.group(3))
        try:
            return date(year, a, b)
        except ValueError:
            try:
                return date(year, b, a)
            except ValueError:
                return None
    return None


def _deadline_status(deadline: str) -> str:
    due_date = _explicit_deadline_date(deadline)
    return 'Overdue' if due_date and due_date < datetime.now(timezone.utc).date() else ''


def render_deliverables_section(section_text: str) -> str:
    """
    Parses the '## Parent' / '- Child :: Description :: Deadline :: Page :: Reference :: Document :: Section'
    structure that Gemini outputs for the Deliverables section and renders it as a
    NUMBERED OUTLINE (1, 1.1, 1.2 ... / 2, 2.1 ...):
      - each parent category gets a distinct color + a smart icon
      - each child row shows a "Document → Section" column indicating which RFP file
        AND which SECTION of that document this deliverable came from
      - deadlines marked "(Conditional)" get a visually distinct badge
      - each child row also shows a "Reference from RFP" line

    Falls back to returning the section mostly as-is if the expected
    structure isn't found, so the app never breaks even if the model
    drifts from the requested format.
    """
    parent_pattern = re.compile(r'^##\s*(.+?)\s*$', re.MULTILINE)
    matches = list(parent_pattern.finditer(section_text))

    if not matches:
        return section_text

    groups_html = []
    parent_num = 0
    palette_size = 5

    for i, m in enumerate(matches):
        parent_name = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        body = section_text[start:end]

        color_idx = parent_num % palette_size

        child_rows = []
        child_idx = 0
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            line = line.lstrip("-").strip()
            parts = [p.strip() for p in line.split("::")]
            name = parts[0] if len(parts) > 0 else ""
            desc = parts[1] if len(parts) > 1 else ""
            deadline = parts[2] if len(parts) > 2 else "Not specified in RFP"
            page = parts[3] if len(parts) > 3 and parts[3] else "N/A"
            reference = parts[4] if len(parts) > 4 and parts[4] else "See page reference above"
            reference = reference.strip().strip('"').strip("'").strip()
            document = parts[5] if len(parts) > 5 and parts[5] else "Unknown Document"
            section_name = parts[6] if len(parts) > 6 and parts[6] else "N/A"
            requirement_type = _normalize_requirement_type(parts[7] if len(parts) > 7 else "", name, desc, reference)
            if not name:
                continue
            child_idx += 1
            is_conditional = "conditional" in deadline.lower()
            overdue = _deadline_status(deadline)
            deadline_class = "deliverable-deadline deadline-conditional" if is_conditional else "deliverable-deadline"
            if overdue:
                deadline_class += " deadline-overdue"
            deadline_display = f"⚠ {overdue} · {deadline}" if overdue else f"⏰ {deadline}"
            page_label = page if page.lower().startswith("page") or page.upper() == "N/A" else f"Page {page}"
            requirement_class = "requirement-optional" if requirement_type == "Optional" else "requirement-mandatory"

            doc_display = document

            if section_name and section_name.strip() and section_name.strip().upper() != "N/A":
                sec_display = section_name.strip()
            else:
                sec_display = "General Requirements"
            doc_section_display = f'<span class="doc-name">📄 {escape(doc_display)}</span><br><span class="sec-name">→ 📑 {escape(sec_display)}</span>'
            child_rows.append(
                f'<tr class="deliv-child-row deliv-child-c{color_idx}">'
                f'<td class="deliv-num">{parent_num + 1}.{child_idx}</td>'
                f'<td class="deliv-name">{escape(name)}<br><span class="requirement-label {requirement_class}">{requirement_type}</span></td>'
                f'<td class="deliv-doc">{doc_section_display}</td>'
                f'<td class="deliv-desc">{escape(desc)}</td>'
                f'<td class="deliv-deadline-cell"><span class="{deadline_class}">{escape(deadline_display)}</span>'
                f'<br><span class="deliverable-page">📄 {escape(page_label)}</span></td>'
                '</tr>'
            )
            child_rows.append(
                f'<tr class="deliv-evidence-row deliv-child-c{color_idx}">'
                '<td></td>'
                '<td colspan="4">'
                '<span class="deliverable-evidence">'
                '<span class="ev-label">🔎 Reference from RFP:</span>'
                f'<span class="ev-text">"{escape(reference)}"</span>'
                '</span>'
                '</td>'
                '</tr>'
            )

        if not child_rows:
            continue

        parent_num += 1
        icon = _pick_category_icon(parent_name)
        groups_html.append(
            f'<details class="deliv-group deliv-group-c{color_idx}" open>'
            '<summary>'
            '<span class="deliv-toggle-icon">▶</span>'
            f'<span class="deliv-num">{parent_num}</span>'
            f'<span class="dp-icon">{icon}</span>'
            f'<span>{parent_name}</span>'
            '</summary>'
            '<table class="deliverable-table">'
            '<colgroup>'
            '<col style="width:60px">'
            '<col style="width:16%">'
            '<col style="width:18%">'
            '<col style="width:auto">'
            '<col style="width:170px">'
            '</colgroup>'
            '<thead><tr>'
            '<th>#</th>'
            '<th>Deliverable</th>'
            '<th>Document / Section</th>'
            '<th>Description</th>'
            '<th>Deadline / Page</th>'
            '</tr></thead>'
            '<tbody>'
            + "".join(child_rows) +
            '</tbody></table>'
            '</details>'
        )

    if not groups_html:
        return section_text

    return '<div class="deliverable-groups">' + "".join(groups_html) + '</div>'


# =====================================================
# COMPLIANCE CHECKLIST — DOCUMENT/SECTION STYLING
# =====================================================
#
# The checklist prompt now asks Gemini for 8 raw columns per row:
# Item | Status | Decision | Explanation | Reference from RFP | Page No |
# Document Name | Section Name
#
# This merges the last two raw columns (Document Name, Section Name) into a
# single nicely-styled "Document / Section" column — reusing the exact same
# doc-name/sec-name badge styling already used in the Deliverables tab — so
# the checklist visually matches it. Everything else in the row (Item,
# Status, Decision, Explanation, Reference from RFP, Page No) is left
# completely untouched.
#
# Falls back to leaving a row unchanged if it doesn't have the expected
# column count, so nothing ever silently breaks or disappears.

def style_checklist_documents(checklist_text: str) -> str:
    lines = checklist_text.split('\n')
    out_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped.startswith('|') or not stripped.endswith('|'):
            out_lines.append(line)
            continue

        cols = [c.strip() for c in stripped.strip('|').split('|')]

        # Header row
        if len(cols) >= 8 and cols[0].lower() == 'item':
            new_cols = cols[:6] + ['Document / Section']
            out_lines.append('| ' + ' | '.join(new_cols) + ' |')
            continue

        # Separator row (e.g. |------|------|...)
        if len(cols) >= 8 and all(re.fullmatch(r'-+', c.replace(' ', '')) for c in cols):
            new_cols = cols[:6] + ['-' * 20]
            out_lines.append('|' + '|'.join(new_cols) + '|')
            continue

        # Data row
        if len(cols) >= 8:
            item, status, decision, explanation, reference, page_no = cols[:6]
            document = cols[6] if len(cols) > 6 and cols[6] else 'N/A'
            section = cols[7] if len(cols) > 7 and cols[7] else 'N/A'
            if document.upper() == 'N/A':
                doc_section_html = '<span class="deliv-doc">N/A</span>'
            else:
                if not section or section.upper() == 'N/A':
                    section = 'General Requirements'
                # "word-break: break-all" forces the browser to wrap the text
                # at ANY character (not just at spaces/underscores), so even
                # one long unbroken filename gets its minimum required width
                # shrunk down to a single character. That is what keeps this
                # column's width fixed and stops it from ever stretching the
                # other columns — while still showing the FULL name (wrapped
                # across a couple of lines) instead of cutting it short.
                doc_section_html = (
                    '<span class="deliv-doc" style="max-width:150px; display:inline-block; '
                    'width:150px; box-sizing:border-box; font-size:0.72rem; line-height:1.4; '
                    'white-space:normal; word-break:break-all; overflow-wrap:anywhere;">'
                    f'<span class="doc-name" style="word-break:break-all; overflow-wrap:anywhere;">📄 {document}</span><br>'
                    f'<span class="sec-name" style="word-break:break-all; overflow-wrap:anywhere;">→ 📑 {section}</span>'
                    '</span>'
                )
            new_cols = [item, status, decision, explanation, reference, page_no, doc_section_html]
            out_lines.append('| ' + ' | '.join(new_cols) + ' |')
            continue

        out_lines.append(line)

    return '\n'.join(out_lines)


def render_deliverables_section_pdf(section_text: str) -> str:
    """
    PDF-only version of render_deliverables_section().
    FIX: xhtml2pdf garbles/overlaps text when a table row splits across a
    page boundary. Adding page-break-inside:avoid on every <tr> stops rows
    from being cut mid-way, and table-layout:fixed forces column widths to
    be respected exactly, instead of xhtml2pdf recalculating them and
    mis-positioning text (which caused the overlapping/mixed text bug).
    """

    def _sanitize(text: str) -> str:
        if not text:
            return text
        replacements = {
            '\u201c': '"', '\u201d': '"',   # " "
            '\u2018': "'", '\u2019': "'",   # ' '
            '\u2013': '-', '\u2014': '-',   # – —
            '\u2026': '...',                # …
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)
        return text

    def _strip_quotes(text: str) -> str:
        if not text:
            return text
        return text.strip().strip('"').strip("'").strip()

    parent_pattern = re.compile(r'^##\s*(.+?)\s*$', re.MULTILINE)
    matches = list(parent_pattern.finditer(section_text))

    if not matches:
        return section_text

    rows_html = []
    parent_num = 0

    for i, m in enumerate(matches):
        parent_name = _sanitize(m.group(1).strip())
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section_text)
        body = section_text[start:end]

        child_rows = []
        child_idx = 0
        for line in body.splitlines():
            line = line.strip()
            if not line.startswith("-"):
                continue
            line = line.lstrip("-").strip()
            parts = [p.strip() for p in line.split("::")]
            name = _sanitize(parts[0] if len(parts) > 0 else "")
            desc = _sanitize(parts[1] if len(parts) > 1 else "")
            deadline = _sanitize(parts[2] if len(parts) > 2 else "Not specified in RFP")
            page = parts[3] if len(parts) > 3 and parts[3] else "N/A"
            reference = _strip_quotes(_sanitize(parts[4] if len(parts) > 4 and parts[4] else ""))
            document = _sanitize(parts[5] if len(parts) > 5 and parts[5] else "Unknown Document")
            # FIX: xhtml2pdf doesn't wrap long underscore-filled filenames
            # (no spaces = no break point), which caused text to overflow
            # into the next column. Inserting a space after every
            # underscore gives the renderer a valid wrap point.
            document = document.replace('_', '_ ')
            section_name = _sanitize(parts[6] if len(parts) > 6 and parts[6] else "N/A")
            requirement_type = _normalize_requirement_type(parts[7] if len(parts) > 7 else "", name, desc, reference)
            if not name:
                continue
            child_idx += 1
            overdue = _deadline_status(deadline)
            deadline_display = f"OVERDUE — {deadline}" if overdue else deadline
            page_label = page if page.lower().startswith("page") or page.upper() == "N/A" else f"Page {page}"
            sec_display = section_name.strip() if section_name and section_name.strip().upper() != "N/A" else "General Requirements"

            # page-break-inside:avoid on the <tr> = the actual fix for the
            # overlapping/garbled text bug.
            child_rows.append(
                '<tr style="page-break-inside: avoid;">'
                f'<td style="word-break:break-all;"><b>{parent_num + 1}.{child_idx}</b></td>'
                f'<td style="word-break:break-all;"><b>{escape(name)}</b><br/><small>{requirement_type}</small></td>'
                f'<td style="word-break:break-all; font-size:8px;">{escape(document)} ({escape(sec_display)})</td>'
                f'<td style="word-break:break-word;">{escape(desc)}</td>'
                f'<td style="word-break:break-word;">{escape(deadline_display)} ({escape(page_label)})</td>'
                '</tr>'
            )
            if reference:
                child_rows.append(
                    '<tr style="page-break-inside: avoid;"><td colspan="5" style="background:#eafaf5; color:#0a7a63; '
                    f'font-size:8px; padding:4px 7px;">Ref: "{escape(reference)}"</td></tr>'
                )

        if not child_rows:
            continue

        parent_num += 1
        rows_html.append(
            '<tr style="page-break-inside: avoid;">'
            f'<td colspan="5" style="background:#e8e8f5; font-weight:bold; padding:6px;">'
            f'{parent_num}. {parent_name}</td></tr>'
        )
        rows_html.extend(child_rows)

    if not rows_html:
        return section_text

    table = (
        '<table style="width:100%; border-collapse:collapse; table-layout:fixed;" border="1">'
        '<colgroup>'
        '<col style="width:6%;"/>'
        '<col style="width:16%;"/>'
        '<col style="width:22%;"/>'
        '<col style="width:32%;"/>'
        '<col style="width:24%;"/>'
        '</colgroup>'
        '<tr style="background:#dddddd;">'
        '<th>#</th>'
        '<th>Deliverable</th>'
        '<th>Document / Section</th>'
        '<th>Description</th>'
        '<th>Deadline / Page</th>'
        '</tr>'
        + "".join(rows_html) +
        '</table>'
    )
    return table

# =====================================================
# ROBUST HEADING HELPERS (fixes "No deliverables found" bug)
# =====================================================
#
# BUG THAT WAS HAPPENING: format_report() used to detect the "# DELIVERABLES"
# (and other) headings with a case-insensitive REGEX first, but then did the
# actual banner swap with a plain, case-SENSITIVE Python .replace('# DELIVERABLES', ...).
# Whenever Gemini printed the heading with a different number of leading "#"
# characters (e.g. "## DELIVERABLES") or different casing, the first regex step
# could silently fail to match (since it only allowed exactly one leading "#"),
# leaving the heading exactly as Gemini wrote it — and the later literal
# .replace() call (or even the regex-based ones) would then not reliably turn
# it into a "sec-deliverables" banner. Net effect: split_report_sections()
# never found a "sec-deliverables" div, so the Deliverables tab fell back to
# the "No deliverables section found in the report." placeholder even though
# Gemini DID return deliverables content.
#
# FIX: every heading is now matched with ONE tolerant regex (1-6 leading "#",
# case-insensitive) and swapped for its banner in a single regex substitution,
# so variations in heading level/case can no longer cause a missing section.

def _swap_heading_for_banner(report: str, keyword_pattern: str, banner_html: str) -> str:
    """Find a top-level heading like '# DELIVERABLES' (allowing 1-6 '#' and any
    case) and replace it with the given banner HTML. Returns the report
    unchanged if the heading truly isn't present anywhere."""
    pattern = rf'^#{{1,6}}\s*{keyword_pattern}\b.*$'
    return re.sub(pattern, banner_html, report, count=1, flags=re.MULTILINE | re.IGNORECASE)


def _find_heading(report: str, keyword_pattern: str, start: int = 0):
    """Case/level-tolerant search for a top-level heading, used to find section
    boundaries. Returns the match object or None."""
    pattern = rf'^#{{1,6}}\s*{keyword_pattern}\b.*$'
    return re.search(pattern, report[start:], re.MULTILINE | re.IGNORECASE)

# =====================================================
# FORMAT REPORT
# =====================================================

def format_report(report):
    """Format the report with clean markdown"""

    report = re.sub(r'[»›•]', '', report)
    report = report.replace('**', '')

    # ---- Render the Deliverables section as a two-level parent-child list ----
    deliv_start_match = re.search(
        r'^#{1,6}\s*DELIVERABLES\b.*$',
        report,
        re.MULTILINE | re.IGNORECASE,
    )

    if deliv_start_match:
        search_from = deliv_start_match.end()
        next_heading_match = re.search(
            r'^#{1,6}\s*(EVALUATION CRITERIA|COMPLIANCE CHECKLIST|SCORING SUMMARY|QUALIFICATION DECISION)\b.*$',
            report[search_from:],
            re.MULTILINE | re.IGNORECASE,
        )
        body_end = search_from + next_heading_match.start() if next_heading_match else len(report)
        body = report[search_from:body_end]
        rendered = render_deliverables_section(body)
        report = (
            report[:deliv_start_match.start()]
            + '# DELIVERABLES\n' + rendered + '\n'
            + report[body_end:]
        )
    else:
        # SAFETY NET: the exact "# DELIVERABLES" heading (in any hash-count /
        # case) truly isn't there. Rather than silently losing the content,
        # look for the tell-tale deliverable line pattern
        # ("- Name :: Description :: ...") and treat everything from the
        # nearest preceding "##" category heading up to the next known
        # top-level heading as the Deliverables body, so the tab still shows
        # real content instead of "No deliverables found".
        fallback_line_match = re.search(r'^-\s*[^\n]*::[^\n]*::', report, re.MULTILINE)
        if fallback_line_match:
            preceding_hash = report.rfind('##', 0, fallback_line_match.start())
            search_from = preceding_hash if preceding_hash != -1 else fallback_line_match.start()
            next_heading_match = _find_heading(
                report,
                r'(EVALUATION CRITERIA|COMPLIANCE CHECKLIST|SCORING SUMMARY|QUALIFICATION DECISION)',
                search_from,
            )
            body_end = search_from + next_heading_match.start() if next_heading_match else len(report)
            body = report[search_from:body_end]
            rendered = render_deliverables_section(body)
            report = (
                report[:search_from]
                + '# DELIVERABLES\n' + rendered + '\n'
                + report[body_end:]
            )

    # ---- Style the Document/Section columns in the Compliance Checklist tables ----
    checklist_start_match = re.search(
        r'^#{1,6}\s*COMPLIANCE CHECKLIST\b.*$',
        report,
        re.MULTILINE | re.IGNORECASE,
    )
    if checklist_start_match:
        search_from = checklist_start_match.end()
        next_heading_match = re.search(
            r'^#{1,6}\s*(SCORING SUMMARY|QUALIFICATION DECISION)\b.*$',
            report[search_from:],
            re.MULTILINE | re.IGNORECASE,
        )
        body_end = search_from + next_heading_match.start() if next_heading_match else len(report)
        body = report[search_from:body_end]
        styled_body = style_checklist_documents(body)
        report = (
            report[:checklist_start_match.start()]
            + '# COMPLIANCE CHECKLIST\n' + styled_body + '\n'
            + report[body_end:]
        )

    report = _swap_heading_for_banner(
        report, 'DELIVERABLES',
        '\n\n<div class="section-banner sec-deliverables"><span class="section-icon">📋</span><span class="section-title">Deliverables</span></div>\n\n'
    )
    report = _swap_heading_for_banner(
        report, 'EVALUATION CRITERIA',
        '\n\n<div class="section-banner sec-evaluation"><span class="section-icon">⚖️</span><span class="section-title">Evaluation Criteria</span></div>\n\n'
    )
    report = _swap_heading_for_banner(
        report, 'COMPLIANCE CHECKLIST',
        '\n\n<div class="section-banner sec-checklist"><span class="section-icon">✅</span><span class="section-title">Compliance Checklist</span></div>\n\n'
    )
    report = _swap_heading_for_banner(
        report, 'SCORING SUMMARY',
        '\n\n<div class="section-banner sec-scoring"><span class="section-icon">📊</span><span class="section-title">Scoring Summary</span></div>\n\n'
    )
    report = _swap_heading_for_banner(
        report, 'QUALIFICATION DECISION',
        '\n\n<div class="section-banner sec-decision"><span class="section-icon">🎯</span><span class="section-title">Qualification Decision</span></div>\n\n'
    )

    report = _swap_heading_for_banner(
        report, 'FINANCE TEAM',
        '\n\n<div class="team-banner team-finance"><span class="team-icon">💰</span>Finance Team</div>\n\n'
    )
    report = _swap_heading_for_banner(
        report, 'LEGAL TEAM',
        '\n\n<div class="team-banner team-legal"><span class="team-icon">⚖️</span>Legal Team</div>\n\n'
    )
    report = _swap_heading_for_banner(
        report, 'OPERATIONS TEAM',
        '\n\n<div class="team-banner team-ops"><span class="team-icon">📋</span>Operations Team</div>\n\n'
    )
    report = _swap_heading_for_banner(
        report, 'TECHNICAL TEAM',
        '\n\n<div class="team-banner team-tech"><span class="team-icon">🔧</span>Technical Team</div>\n\n'
    )

    finance = re.search(r'Finance Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)
    legal = re.search(r'Legal Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)
    ops = re.search(r'Operations Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)
    tech = re.search(r'Technical Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)
    overall = re.search(r'Overall Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)

    def get_color(score_str):
        try:
            num = float(score_str.replace('%', ''))
            if num >= 80:
                return '#2fe6b8'
            elif num >= 60:
                return '#ffc857'
            else:
                return '#ff6b81'
        except:
            return '#cdd2ef'

    def _score_card(label, icon, score, color):
        return (
            f'<div style="background: linear-gradient(160deg, #12132a, #181a35); padding: 1.4rem 1rem; '
            f'border-radius: 16px; border: 1px solid rgba(255,255,255,0.07); text-align: center; '
            f'position: relative; overflow: hidden; box-shadow: 0 6px 18px rgba(0,0,0,0.3);">'
            f'<div style="position:absolute; top:0; left:0; right:0; height:3px; background:{color};"></div>'
            f'<div style="color: #a6acd4; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1px; '
            f'margin-bottom: 0.5rem; font-weight:600;">{icon} {label}</div>'
            f'<div style="font-size: 2.1rem; font-weight: 800; color: {color}; font-family: \'Sora\', sans-serif;">{score}</div>'
            f'</div>'
        )

    score_html = '<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1.5rem 0;">'

    if finance:
        score = finance.group(1)
        score_html += _score_card('Finance', '💰', score, get_color(score))

    if legal:
        score = legal.group(1)
        score_html += _score_card('Legal', '⚖️', score, get_color(score))

    if ops:
        score = ops.group(1)
        score_html += _score_card('Operations', '📋', score, get_color(score))

    if tech:
        score = tech.group(1)
        score_html += _score_card('Technical', '🔧', score, get_color(score))

    score_html += '</div>'

    if overall:
        score = overall.group(1)
        color = get_color(score)
        score_html += (
            f'<div style="background: linear-gradient(135deg, #12132a, #181a35); padding: 2.2rem; '
            f'border-radius: 20px; border: 1px solid rgba(255,255,255,0.07); text-align: center; margin: 1.5rem 0; '
            f'box-shadow: 0 0 0 1px rgba(124,108,255,0.15), 0 14px 36px rgba(124,108,255,0.15); position:relative; overflow:hidden;">'
            f'<div style="position:absolute; inset:0; background: linear-gradient(135deg, #7c6cff, #b06cff, #ff6cd6); opacity:0.06;"></div>'
            f'<div style="color: #a6acd4; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 3px; position:relative; z-index:1;">📊 Overall Score</div>'
            f'<div style="font-size: 4rem; font-weight: 800; color: {color}; font-family: \'Sora\', sans-serif; position:relative; z-index:1;">{score}</div>'
            f'</div>'
        )

    scoring_banner = '<div class="section-banner sec-scoring"><span class="section-icon">📊</span><span class="section-title">Scoring Summary</span></div>'

    report = re.sub(
        r'# SCORING SUMMARY.*?(?=# QUALIFICATION DECISION)',
        '',
        report,
        flags=re.DOTALL | re.IGNORECASE
    )

    report = re.sub(
        r'<div class="section-banner sec-scoring">.*?</div>',
        f'{scoring_banner}\n\n{score_html}',
        report,
        flags=re.DOTALL
    )

    report = report.replace('Strategic Fit: Strong', '✅ Strategic Fit: Strong')
    report = report.replace('Strategic Fit: Moderate', '⚠️ Strategic Fit: Moderate')
    report = report.replace('Strategic Fit: Poor', '❌ Strategic Fit: Poor')

    report = report.replace('Capability Alignment: Strong', '✅ Capability Alignment: Strong')
    report = report.replace('Capability Alignment: Moderate', '⚠️ Capability Alignment: Moderate')
    report = report.replace('Capability Alignment: Poor', '❌ Capability Alignment: Poor')

    report = report.replace('Financial Viability: Viable', '✅ Financial Viability: Viable')
    report = report.replace('Financial Viability: Needs Review', '⚠️ Financial Viability: Needs Review')
    report = report.replace('Financial Viability: Not Viable', '❌ Financial Viability: Not Viable')

    report = report.replace('Risk Assessment: Low', '✅ Risk Assessment: Low')
    report = report.replace('Risk Assessment: Medium', '⚠️ Risk Assessment: Medium')
    report = report.replace('Risk Assessment: High', '❌ Risk Assessment: High')

    decision_match = re.search(r'Final Decision:\s*[^\w]*([\w-]+(?:\s+\w+)?)', report, re.IGNORECASE)
    if decision_match:
        decision = decision_match.group(1).strip().upper()

        if 'NO-GO' in decision or 'NO GO' in decision or 'NOGO' in decision:
            decision_text = (
                '\n\n<div class="verdict-card verdict-nogo">'
                '<span class="verdict-icon">🚫</span>'
                '<div class="verdict-label">NO-GO</div>'
                '<div class="verdict-msg">Do not pursue this proposal</div>'
                '<div class="verdict-next">📋 Next Step: Allocate resources to other opportunities</div>'
                '</div>\n\n'
            )
        elif 'MAYBE' in decision:
            decision_text = (
                '\n\n<div class="verdict-card verdict-maybe">'
                '<span class="verdict-icon">🤔</span>'
                '<div class="verdict-label">MAYBE</div>'
                '<div class="verdict-msg">Proceed with caution — risk mitigation needed</div>'
                '<div class="verdict-next">📋 Next Step: Conduct further assessment and get clarifications</div>'
                '</div>\n\n'
            )
        elif 'GO' in decision:
            decision_text = (
                '\n\n<div class="verdict-card verdict-go">'
                '<span class="verdict-icon">🎯</span>'
                '<div class="verdict-label">GO</div>'
                '<div class="verdict-msg">Strongly recommend pursuing this proposal</div>'
                '<div class="verdict-next">📋 Next Step: Proceed with proposal development immediately</div>'
                '</div>\n\n'
            )
        else:
            decision_text = (
                f'\n\n<div class="verdict-card verdict-maybe">'
                f'<span class="verdict-icon">🤔</span>'
                f'<div class="verdict-label">{decision}</div>'
                f'<div class="verdict-msg">Need further review</div>'
                f'</div>\n\n'
            )

        report = re.sub(
            r'## FINAL RECOMMENDATION.*?Final Decision:.*?(?=\n\n|\Z)',
            '',
            report,
            flags=re.DOTALL | re.IGNORECASE
        )

        report += (
            '\n\n<div class="section-banner sec-decision">'
            '<span class="section-icon">🎯</span>'
            '<span class="section-title">Final Recommendation</span></div>\n\n'
            f'{decision_text}'
        )

    report = re.sub(r'Final Decision:.*?(?=\n|$)', '', report)

    just_match = re.search(r'##?\s*JUSTIFICATION\s*\n+(.+?)(?=\n\n|\Z)', report, re.DOTALL | re.IGNORECASE)
    if just_match:
        just_text = just_match.group(1).strip()
        if just_text:
            report = re.sub(
                r'##?\s*JUSTIFICATION\s*\n+.+?(?=\n\n|\Z)',
                '',
                report,
                flags=re.DOTALL | re.IGNORECASE
            )
            just_html = just_text.replace('\n', '<br>')
            report += (
                '\n\n<div class="justification-card">'
                '<span class="jc-title">📝 Justification</span>'
                f'{just_html}'
                '</div>\n'
            )

    report = report.replace('✅ FOUND', '<span class="status-found">✅ FOUND</span>')
    report = report.replace('❌ NOT FOUND', '<span class="status-not-found">❌ NOT FOUND</span>')
    report = report.replace('⚠️ ACTION REQUIRED', '<span class="status-action">⚠️ ACTION REQUIRED</span>')

    def _decision_cell(match):
        value = match.group(1).strip().upper()
        if 'NO-GO' in value or 'NO GO' in value:
            return f'| <span class="decision-no-go">❌ NO-GO</span> |'
        elif 'MAYBE' in value:
            return f'| <span class="decision-maybe">⚠️ MAYBE</span> |'
        elif 'GO' in value:
            return f'| <span class="decision-go">✅ GO</span> |'
        return match.group(0)

    report = re.sub(r'\|\s*(NO-GO|NO GO|MAYBE|GO)\s*\|', _decision_cell, report, flags=re.IGNORECASE)

    lines = report.split('\n')
    report = '\n'.join(line.lstrip() for line in lines)

    return report

# =====================================================
# SPLIT REPORT INTO SECTIONS
# =====================================================

def split_report_sections(formatted_report):
    banner_pattern = re.compile(r'<div class="section-banner (sec-[\w-]+)">')
    matches = list(banner_pattern.finditer(formatted_report))

    sections = {}
    for i, m in enumerate(matches):
        key = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(formatted_report)
        chunk = formatted_report[start:end]
        sections[key] = sections.get(key, "") + chunk

    return sections
