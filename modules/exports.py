import json
import re
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from io import BytesIO

import markdown as _md_lib
from xhtml2pdf import pisa

from .presentation import (
    format_report, render_deliverables_section_pdf,
    _explicit_deadline_date, _normalize_requirement_type,
)

try:
    from rfp_json_formatter import report_to_json
except ImportError:
    report_to_json = None

def generate_json_report(raw_report_text: str) -> bytes:
    """Converts a raw markdown report into the same structured JSON the
    /api/rfp/{rfp_id}/analyze endpoint returns, as downloadable bytes."""
    try:
        structured = report_to_json(raw_report_text)
        return json.dumps(structured, indent=2, ensure_ascii=False).encode("utf-8")
    except Exception:
        return None


def _ics_escape(value: str) -> str:
    return str(value or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\n')


def _ics_fold(line: str) -> str:
    """Fold RFC 5545 content lines at 75 octets without splitting UTF-8 characters."""
    chunks, current, size = [], '', 0
    limit = 75
    for char in line:
        char_size = len(char.encode('utf-8'))
        if current and size + char_size > limit:
            chunks.append(current)
            current, size, limit = ' ' + char, 1 + char_size, 74
        else:
            current += char
            size += char_size
    if current:
        chunks.append(current)
    return '\r\n'.join(chunks)


def generate_deliverables_ics(raw_report_text: str, rfp_id: str = 'rfp') -> bytes:
    """Create a Google Calendar-compatible .ics file for explicitly dated deliverables."""
    match = re.search(r'^#{1,6}\s*DELIVERABLES\b.*?\n(.*?)(?=^#\s+|\Z)', raw_report_text or '', re.IGNORECASE | re.MULTILINE | re.DOTALL)
    deliverables_text = match.group(1) if match else ''
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    # The standard VCALENDAR/VEVENT fields below import cleanly into Google
    # Calendar and other calendar apps.  VALARM gives compatible apps a
    # one-day-before notification for each dated deliverable.
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//AI Proposal Capture System//Deliverables//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:RFP Deliverables',
    ]
    for line in deliverables_text.splitlines():
        if not line.strip().startswith('-'):
            continue
        parts = [part.strip() for part in line.strip().lstrip('-').split('::')]
        if len(parts) < 3:
            continue
        due_date = _explicit_deadline_date(parts[2])
        if not due_date:
            continue
        name = parts[0]
        description = parts[1] if len(parts) > 1 else ''
        document = parts[5] if len(parts) > 5 else ''
        section = parts[6] if len(parts) > 6 else ''
        requirement_type = _normalize_requirement_type(parts[7] if len(parts) > 7 else '', name, description)
        identity = '|'.join((str(rfp_id), name, parts[2], document, section))
        uid = hashlib.sha256(identity.encode('utf-8')).hexdigest()[:32] + '@ai-proposal-capture.local'
        event_description = f'{description}\nRequirement: {requirement_type}\nDeadline from RFP: {parts[2]}\nSource: {document} — {section}'
        lines.extend([
            'BEGIN:VEVENT', f'UID:{uid}', f'DTSTAMP:{stamp}',
            f'DTSTART;VALUE=DATE:{due_date.strftime("%Y%m%d")}',
            f'DTEND;VALUE=DATE:{(due_date + timedelta(days=1)).strftime("%Y%m%d")}',
            f'SUMMARY:{_ics_escape("RFP Deliverable: " + name)}',
            f'DESCRIPTION:{_ics_escape(event_description)}',
            'BEGIN:VALARM',
            'TRIGGER:-P1D',
            'ACTION:DISPLAY',
            f'DESCRIPTION:{_ics_escape("RFP deliverable due tomorrow: " + name)}',
            'END:VALARM',
            'END:VEVENT',
        ])
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(_ics_fold(line) for line in lines) + '\r\n').encode('utf-8')


def render_addendum_summary(change_summary_md: str) -> str:
    """Converts the raw markdown 'what changed' text into styled HTML."""
    if not change_summary_md:
        return ""
    html = _md_lib.markdown(change_summary_md, extensions=['tables', 'fenced_code', 'nl2br'])
    return f'<div class="addendum-summary">{html}</div>'

# =====================================================
# SHARED DATABASE (connects this Streamlit app to api.py)
#
# When an RFP is analyzed here with an rfp_id, the result is saved into
# the SAME SQLite database (rfp_results.db) that api.py reads from. So if
# someone later calls GET /api/rfp/analyze/{rfp_id} with that same id, they
# get this already-computed result instantly, instead of api.py re-running
# the whole pipeline from scratch.
# =====================================================

_DB_PATH = Path(__file__).resolve().parent.parent / "rfp_results.db"


def _get_shared_db():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rfp_results (
            rfp_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            generated_at TEXT NOT NULL
        )
        """
    )
    return conn


def save_result_to_shared_db(rfp_id: str, source_filenames, raw_report_text: str):
    """Saves this Streamlit analysis into the shared database under rfp_id,
    in the exact same JSON shape api.py produces, so the API endpoint can
    serve it directly without re-analyzing."""
    if not rfp_id or not rfp_id.strip():
        return False
    rfp_id = rfp_id.strip()
    try:
        structured = report_to_json(raw_report_text)
        payload = {
            "rfp_id": rfp_id,
            "source_documents": list(source_filenames),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cached": False,
            "result": structured,
        }
        conn = _get_shared_db()
        conn.execute(
            """
            INSERT INTO rfp_results (rfp_id, payload, generated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(rfp_id) DO UPDATE SET
                payload = excluded.payload,
                generated_at = excluded.generated_at
            """,
            (rfp_id, json.dumps(payload, ensure_ascii=False), payload["generated_at"]),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


# =====================================================
# COMPLIANCE CHECKLIST — PDF-SAFE TABLE REBUILD
# =====================================================
#
# The on-screen Document/Section badge relies on CSS (word-break,
# overflow-wrap, max-width) to keep long, underscore-filled filenames from
# stretching their table column. xhtml2pdf (the PDF engine used here)
# doesn't respect those CSS rules, so in the exported PDF the same badge
# overflows outside its cell. This rebuilds each Compliance Checklist team
# table as a real HTML <table> with a FIXED column-width layout
# (table-layout:fixed + colgroup) and inserts a real space after every
# underscore in the filename — the exact same trick already used for the
# Deliverables PDF export — so the filename always has a real place to
# wrap. Nothing else in the row (Item, Status, Decision, Explanation,
# Reference from RFP, Page No) is touched.

def _pipe_table_to_fixed_html_pdf(text: str) -> str:
    lines = text.split('\n')
    rows_html = []
    pre_lines = []
    post_lines = []
    seen_table = False
    header_seen = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|'):
            seen_table = True
            cols = [c.strip() for c in stripped.strip('|').split('|')]

            if not header_seen and cols and cols[0].lower() == 'item':
                header_seen = True
                continue
            if all(re.fullmatch(r'-+', c.replace(' ', '')) for c in cols):
                continue
            if len(cols) < 7:
                continue

            item, status, decision, explanation, reference, page_no = cols[:6]
            doc_section = cols[6]

            # Insert a real space after every underscore inside the
            # doc-name span's text so xhtml2pdf has an actual break point.
            doc_section = re.sub(
                r'(<span class="doc-name">)(.*?)(</span>)',
                lambda m: m.group(1) + m.group(2).replace('_', '_ ') + m.group(3),
                doc_section, flags=re.DOTALL
            )
            # Strip the on-screen CSS (max-width/word-break/overflow-wrap)
            # that xhtml2pdf ignores, keep only a small font-size, which IS
            # respected.
            doc_section = re.sub(r'\sstyle="[^"]*"', '', doc_section)
            doc_section = doc_section.replace(
                '<span class="deliv-doc">', '<span class="deliv-doc" style="font-size:8px;">'
            )

            rows_html.append(
                '<tr style="page-break-inside: avoid;">'
                f'<td>{item}</td>'
                f'<td>{status}</td>'
                f'<td>{decision}</td>'
                f'<td>{explanation}</td>'
                f'<td>{reference}</td>'
                f'<td>{page_no}</td>'
                f'<td style="word-break:break-all; font-size:8px;">{doc_section}</td>'
                '</tr>'
            )
        else:
            (post_lines if seen_table else pre_lines).append(line)

    if not rows_html:
        return text

    header_row = (
        '<tr>'
        '<th style="width:11%;">Item</th>'
        '<th style="width:8%;">Status</th>'
        '<th style="width:8%;">Decision</th>'
        '<th style="width:25%;">Explanation</th>'
        '<th style="width:21%;">Reference from RFP</th>'
        '<th style="width:6%;">Page No</th>'
        '<th style="width:21%;">Document / Section</th>'
        '</tr>'
    )

    table_html = (
        '<table style="width:100%; border-collapse:collapse; table-layout:fixed;" border="1">'
        '<colgroup>'
        '<col style="width:11%;"/><col style="width:8%;"/><col style="width:8%;"/>'
        '<col style="width:25%;"/><col style="width:21%;"/><col style="width:6%;"/>'
        '<col style="width:21%;"/>'
        '</colgroup>'
        + header_row
        + ''.join(rows_html)
        + '</table>'
    )

    return '\n'.join(pre_lines) + table_html + '\n'.join(post_lines)


def checklist_pdf_safe_tables(formatted_text: str) -> str:
    checklist_match = re.search(
        r'<div class="section-banner sec-checklist">.*?</div>',
        formatted_text, re.DOTALL
    )
    if not checklist_match:
        return formatted_text

    search_from = checklist_match.end()
    next_banner_match = re.search(r'<div class="section-banner ', formatted_text[search_from:])
    body_end = search_from + next_banner_match.start() if next_banner_match else len(formatted_text)
    body = formatted_text[search_from:body_end]

    team_pattern = re.compile(r'(<div class="team-banner[^>]*>.*?</div>)', re.DOTALL)
    parts = team_pattern.split(body)

    rebuilt = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if team_pattern.match(chunk):
            rebuilt.append(chunk)
            i += 1
            if i < len(parts):
                rebuilt.append(_pipe_table_to_fixed_html_pdf(parts[i]))
                i += 1
        else:
            rebuilt.append(chunk)
            i += 1

    new_body = ''.join(rebuilt)
    return formatted_text[:checklist_match.end()] + new_body + formatted_text[body_end:]


def generate_pdf_report(raw_report_text: str):
    """
    Builds a downloadable PDF from the same raw_report text used for the
    .md download. Internally reuses format_report() (already produced by
    the existing pipeline) so the PDF matches what's shown on screen,
    then converts the markdown/HTML into a clean printable PDF via
    xhtml2pdf. Returns PDF bytes, or None if generation fails.
    """
    try:
        formatted = format_report(raw_report_text)
        # PDF-only fix: rebuild the Compliance Checklist tables with a fixed
        # column layout + real space-inserted filenames, so the Document /
        # Section column wraps correctly instead of overflowing.
        formatted = checklist_pdf_safe_tables(formatted)
        # PDF-only fix: swap the <details>/emoji-based deliverables HTML
        # for a plain-table version xhtml2pdf can actually render correctly.
        deliv_match = re.search(
            r'<div class="deliverable-groups">.*?</div>\s*(?=<div class="section-banner|\Z)',
            formatted, re.DOTALL
        )
        if deliv_match:
            raw_deliv_match = re.search(
                r'^#{1,6}\s*DELIVERABLES\b.*?(?=^#{1,6}\s*(EVALUATION CRITERIA|COMPLIANCE CHECKLIST))',
                raw_report_text, re.MULTILINE | re.IGNORECASE | re.DOTALL
            )
            if raw_deliv_match:
                pdf_table = render_deliverables_section_pdf(raw_deliv_match.group(0))
                formatted = formatted[:deliv_match.start()] + pdf_table + formatted[deliv_match.end():]
        # Convert any remaining markdown (tables, headers, etc.) to HTML.
        body_html = _md_lib.markdown(formatted, extensions=['tables', 'fenced_code', 'nl2br'])

        html_doc = f"""
        <html>
        <head>
        <meta charset="utf-8" />
        <style>
            @page {{ size: A4; margin: 1.6cm; }}
            body {{ font-family: Helvetica, Arial, sans-serif; font-size: 10px; color: #1a1a1a; }}
            h1 {{ font-size: 18px; margin: 14px 0 8px 0; }}
            h2 {{ font-size: 15px; margin: 12px 0 6px 0; }}
            h3 {{ font-size: 13px; margin: 10px 0 5px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin: 8px 0 14px 0; }}
            th, td {{ border: 1px solid #999; padding: 5px 7px; text-align: left; font-size: 9px; vertical-align: top; }}
            th {{ background-color: #eeeeee; font-weight: bold; }}
            div {{ font-size: 10px; }}
            .section-banner {{ font-size: 14px; font-weight: bold; margin: 16px 0 8px 0; padding: 6px 0; border-bottom: 2px solid #333; }}
            .team-banner {{ font-size: 11px; font-weight: bold; margin: 10px 0 4px 0; text-transform: uppercase; }}
            .verdict-label {{ font-size: 20px; font-weight: bold; }}
            .justification-card {{ border: 1px solid #999; padding: 8px; margin: 8px 0; }}
            .status-found, .status-action, .status-not-found,
            .decision-go, .decision-maybe, .decision-no-go {{
                padding: 2px 6px; font-weight: bold; font-size: 8px;
            }}
        </style>
        </head>
        <body>
        {body_html}
        </body>
        </html>
        """

        pdf_buffer = BytesIO()
        result = pisa.CreatePDF(src=html_doc, dest=pdf_buffer, encoding='utf-8')
        if result.err:
            return None
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()
    except Exception:
        return None
