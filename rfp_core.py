"""
rfp_core.py
=====================================================
SHARED, UI-FREE RFP ANALYSIS LOGIC.

This module mirrors the CURRENT app.py analysis pipeline (multi-agent
extraction, exhaustive deliverables scan, requirement-type field, deadline
-override GO/NO-GO logic, independent verification pass) but with ZERO
Streamlit (st.*) calls anywhere, so it can be imported safely from a
non-Streamlit process (the FastAPI server in api.py).

app.py keeps its own copies of this logic for the UI (progress bars, live
agent cards, amendment/history workflow) — this file exists purely so the
JSON API endpoint has a headless, up-to-date equivalent to import. Nothing
in app.py is changed by this file.

PUBLIC ENTRY POINTS (used by api.py):
    extract_text_headless(pdf_paths)         -> str
    analyze_rfp_headless(document_text, ...) -> str (raw markdown report)
=====================================================
"""

import os
import re
import time
import random
import threading
import concurrent.futures
from pathlib import Path
from datetime import date, datetime, timezone
from collections import Counter

from pypdf import PdfReader
import google.generativeai as genai
from google.api_core import exceptions
from dotenv import load_dotenv

load_dotenv()

# =====================================================
# GEMINI CONFIG
# =====================================================

_api_key = os.getenv("GOOGLE_API_KEY")
if not _api_key:
    raise RuntimeError(
        "GOOGLE_API_KEY not found in environment (.env). "
        "Set it before starting the API server."
    )

genai.configure(api_key=_api_key)

# Same multi-agent model split as app.py: "fast" and "pro" currently point
# at the same GA model (gemini-3.6-flash) and share one rate-limit gate;
# "lite" is a genuinely different, cheaper model used only for the narrow
# per-chunk deliverables scan, and paces independently.
MODELS = {
    "fast": genai.GenerativeModel("models/gemini-3.6-flash"),
    "pro": genai.GenerativeModel("models/gemini-3.6-flash"),
    "lite": genai.GenerativeModel("models/gemini-3.5-flash-lite"),
}

# =====================================================
# PDF TEXT EXTRACTION (headless — no st.progress/st.empty)
# =====================================================


def extract_text_headless(pdf_paths):
    """
    Same behavior as app.py's extract_text_with_context, but takes a list
    of file paths (not Streamlit UploadedFile objects) and does not touch
    any Streamlit UI element.
    """
    all_text = ""
    for pdf_path in pdf_paths:
        pdf_path = Path(pdf_path)
        filename = pdf_path.name

        reader = PdfReader(str(pdf_path))
        text = ""
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n\n[PAGE {i+1}]\n" + page_text + "\n"

        all_text += f"\n\n{'='*60}\n[START OF DOCUMENT: {filename}]\n{'='*60}\n"
        all_text += text
        all_text += f"\n{'='*60}\n[END OF DOCUMENT: {filename}]\n{'='*60}\n"

    return all_text


# =====================================================
# SCORE RECOMPUTATION (SOURCE OF TRUTH — identical logic to app.py)
# =====================================================

TEAM_HEADERS = [
    ("FINANCE TEAM", "Finance Score"),
    ("LEGAL TEAM", "Legal Score"),
    ("OPERATIONS TEAM", "Operations Score"),
    ("TECHNICAL TEAM", "Technical Score"),
]


def _format_pct(value: float) -> str:
    rounded = round(value, 1)
    if rounded == int(rounded):
        return f"{int(rounded)}%"
    return f"{rounded}%"


def _count_decisions_in_section(section_text: str):
    go = maybe = nogo = 0
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 3:
            continue
        if cols[0].lower() == "item":
            continue
        if re.fullmatch(r"-+", cols[0].replace(" ", "")):
            continue
        decision_col = cols[2].upper()
        if "NO-GO" in decision_col or "NO GO" in decision_col or "NOGO" in decision_col:
            nogo += 1
        elif "MAYBE" in decision_col:
            maybe += 1
        elif "GO" in decision_col:
            go += 1
    total = go + maybe + nogo
    return go, maybe, nogo, total


def recompute_scores(report_text: str):
    scores = {}
    header_positions = []
    for header, label in TEAM_HEADERS:
        m = re.search(r"##\s*" + re.escape(header), report_text, re.IGNORECASE)
        if m:
            header_positions.append((m.start(), m.end(), label))
    header_positions.sort(key=lambda x: x[0])

    scoring_summary_match = re.search(r"#\s*SCORING SUMMARY", report_text, re.IGNORECASE)
    doc_end = scoring_summary_match.start() if scoring_summary_match else len(report_text)

    for i, (start, end, label) in enumerate(header_positions):
        next_start = header_positions[i + 1][0] if i + 1 < len(header_positions) else doc_end
        section = report_text[end:next_start]
        go, maybe, nogo, total = _count_decisions_in_section(section)
        if total == 0:
            continue
        pct = (go * 1.0 + maybe * 0.5) / total * 100
        scores[label] = {"pct": pct, "go": go, "maybe": maybe, "nogo": nogo, "total": total}

    return scores


def _explicit_deadline_date(deadline: str):
    """Parse only unambiguous, absolute calendar dates; never guess relative dates."""
    value = (deadline or "").strip()
    lower = value.casefold()
    if not value or any(term in lower for term in (
        "not specified", "conditional", "within ", "after ", "before notice",
        "tbd", "to be determined",
    )):
        return None
    match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    cleaned = re.sub(r"(?<=\d)(st|nd|rd|th)\b", "", value, flags=re.IGNORECASE)
    patterns = (
        (r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{1,2},?\s+20\d{2}\b",
         ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y")),
        (r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+20\d{2}\b",
         ("%d %B %Y", "%d %b %Y")),
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
    numeric = re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b", value)
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
    return "Overdue" if due_date and due_date < datetime.now(timezone.utc).date() else ""


def _primary_deadline_overdue(deliverables_text: str) -> bool:
    """Detect whether the RFP's PRIMARY bid-submission deadline has already
    passed (same rule as app.py): 2+ Mandatory deliverables sharing the same
    absolute deadline, and that deadline is in the past."""
    deadlines = []
    for line in deliverables_text.splitlines():
        line = line.strip()
        if not line.startswith("-") or "::" not in line:
            continue
        parts = [p.strip() for p in line.lstrip("-").split("::")]
        if len(parts) < 8:
            continue
        deadline, requirement_type = parts[2], parts[7]
        if requirement_type.strip().casefold() != "mandatory":
            continue
        if _explicit_deadline_date(deadline):
            deadlines.append(deadline)
    if len(deadlines) < 2:
        return False
    common_deadline, count = Counter(deadlines).most_common(1)[0]
    if count < 2:
        return False
    return _deadline_status(common_deadline) == "Overdue"


def determine_final_decision(overall_pct: float, finance_maybe: int, finance_nogo: int,
                              deadline_overdue: bool = False) -> str:
    """
    Priority order:
      1. Primary bid-submission deadline already passed -> automatic NO-GO.
      2. Under 60% -> automatic NO-GO.
      3. 80%+ AND every Finance row is GO -> GO.
      4. Everything else -> MAYBE.
    """
    if deadline_overdue:
        return "NO-GO"
    if overall_pct < 60:
        return "NO-GO"
    if overall_pct >= 80 and finance_maybe == 0 and finance_nogo == 0:
        return "GO"
    return "MAYBE"


def sync_justification_score(report_text: str, overall_pct: float, correct_decision: str,
                              deadline_overdue: bool = False) -> str:
    correct = _format_pct(overall_pct)
    match = re.search(
        r"(##?\s*JUSTIFICATION\s*\n+)(.+?)(?=\n\n|\Z)",
        report_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return report_text

    just_text = match.group(2)

    fixed_just = re.sub(
        r"score\s*(?:of|is|:)?\s*\d+\.?\d*%",
        f"score of {correct}",
        just_text,
        flags=re.IGNORECASE,
    )

    fixed_just = re.sub(
        r"(recommendation|decision)\s+is\s+(?:a\s+)?(?:GO|NO-GO|NO GO|MAYBE)\b",
        rf"\1 is {correct_decision}",
        fixed_just,
        flags=re.IGNORECASE,
    )

    if deadline_overdue:
        override_note = (
            "⚠️ OVERRIDE: The primary bid submission deadline stated in this "
            "RFP has already passed as of today, so the bid window is closed "
            "and this opportunity cannot be submitted regardless of the score "
            "below — this is why the Final Decision is NO-GO even though the "
            "compliance score may look strong. "
        )
        if override_note.strip() not in fixed_just:
            fixed_just = override_note + fixed_just

    return report_text[:match.start(2)] + fixed_just + report_text[match.end(2):]


def _ensure_decision_rationale(report_text: str) -> str:
    """Guarantee every checklist row's Explanation ends with a short clause
    naming the Decision it led to, purely additive."""
    lines = report_text.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            out.append(line)
            continue
        cols = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cols) < 4:
            out.append(line)
            continue
        if cols[0].casefold() == "item" or re.fullmatch(r"-+", cols[0].replace(" ", "")):
            out.append(line)
            continue
        decision_col = cols[2].upper()
        if "NO-GO" in decision_col or "NO GO" in decision_col or "NOGO" in decision_col:
            decision_word = "NO-GO"
        elif "MAYBE" in decision_col:
            decision_word = "MAYBE"
        elif re.search(r"\bGO\b", decision_col):
            decision_word = "GO"
        else:
            out.append(line)
            continue

        explanation = cols[3]
        already_present = re.search(
            r"\b(GO|NO-GO|NO GO|MAYBE)\s*decision\b|\bdecision\s*(?:of|is)?\s*(?:a\s*)?(GO|NO-GO|NO GO|MAYBE)\b",
            explanation, re.IGNORECASE,
        )
        if not already_present and explanation and "not specified" not in explanation.casefold():
            cols[3] = explanation.rstrip(".").rstrip() + f", leading to a **{decision_word}** decision."
            leading_ws = line[:len(line) - len(line.lstrip())]
            out.append(leading_ws + "| " + " | ".join(cols) + " |")
        else:
            out.append(line)
    return "\n".join(out)


def apply_score_fix(report_text: str) -> str:
    """Single source of truth for every number/decision in the report."""
    scores = recompute_scores(report_text)
    if not scores:
        return report_text

    fixed = report_text
    for header, label in TEAM_HEADERS:
        if label in scores:
            new_line = f"{label}: {_format_pct(scores[label]['pct'])}"
            fixed = re.sub(
                rf"{re.escape(label)}:\s*\d+\.?\d*%",
                new_line,
                fixed,
                flags=re.IGNORECASE,
            )

    overall_pct = sum(v["pct"] for v in scores.values()) / len(scores)
    fixed = re.sub(
        r"Overall Score:\s*\d+\.?\d*%",
        f"Overall Score: {_format_pct(overall_pct)}",
        fixed,
        flags=re.IGNORECASE,
    )

    finance = scores.get("Finance Score")
    finance_maybe = finance["maybe"] if finance else 0
    finance_nogo = finance["nogo"] if finance else 0
    deadline_overdue = _primary_deadline_overdue(fixed)
    correct_decision = determine_final_decision(overall_pct, finance_maybe, finance_nogo, deadline_overdue)

    if re.search(r"Final Decision:\s*[^\n]*", fixed, re.IGNORECASE):
        fixed = re.sub(
            r"Final Decision:\s*[^\n]*",
            f"Final Decision: {correct_decision}",
            fixed,
            flags=re.IGNORECASE,
        )
    else:
        fixed += f"\n\nFinal Decision: {correct_decision}\n"

    fixed = sync_justification_score(fixed, overall_pct, correct_decision, deadline_overdue)
    fixed = _ensure_decision_rationale(fixed)

    return fixed


def _normalize_requirement_type(value: str, *context: str) -> str:
    label = (value or "").strip().casefold()
    source = " ".join(str(item or "") for item in context).casefold()
    if label == "optional" or any(term in source for term in (" optional", "at bidder discretion", "may submit", "if desired")):
        return "Optional"
    return "Mandatory"


# =====================================================
# GENERIC GEMINI CALLER (headless — no Streamlit status UI)
# =====================================================

GEMINI_MIN_INTERVAL_SECONDS = max(0.5, float(os.getenv("GEMINI_MIN_INTERVAL_SECONDS", "6.0")))
_gemini_pacing_lock = threading.Lock()
_gemini_next_request_at = {}  # model_name -> monotonic timestamp


def _acquire_gemini_slot(model_name):
    global _gemini_next_request_at
    while True:
        with _gemini_pacing_lock:
            now = time.monotonic()
            next_at = _gemini_next_request_at.get(model_name, 0.0)
            delay = next_at - now
            if delay <= 0:
                _gemini_next_request_at[model_name] = now + GEMINI_MIN_INTERVAL_SECONDS
                return
        time.sleep(min(delay, 1.0))


def _apply_gemini_cooldown(model_name, seconds):
    global _gemini_next_request_at
    with _gemini_pacing_lock:
        current = _gemini_next_request_at.get(model_name, 0.0)
        _gemini_next_request_at[model_name] = max(current, time.monotonic() + max(0, seconds))


def _retry_delay_seconds(error, attempt):
    retry_delay = getattr(error, "retry_delay", None)
    if retry_delay is not None:
        seconds = float(getattr(retry_delay, "seconds", 0) or 0)
        seconds += float(getattr(retry_delay, "nanos", 0) or 0) / 1_000_000_000
        if seconds > 0:
            return seconds + random.uniform(1.0, 3.0)
    return min(120, (2 ** attempt) * 10) + random.uniform(1.0, 3.0)


def call_gemini_with_retry(prompt, status_label="Analyzing...", max_retries=5, model_key="fast"):
    """Headless Gemini caller with the same coordinated quota pacing/retry
    cooldowns as app.py, minus any Streamlit UI updates (prints instead)."""
    agent_model = MODELS.get(model_key, MODELS["fast"])
    model_name = getattr(agent_model, "model_name", model_key)
    for attempt in range(max_retries):
        _acquire_gemini_slot(model_name)
        try:
            response = agent_model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0,
                    "top_p": 1,
                    "top_k": 1,
                    "candidate_count": 1,
                    "max_output_tokens": 65536,
                },
            )
            return response.text
        except exceptions.ResourceExhausted as e:
            wait_time = _retry_delay_seconds(e, attempt)
            _apply_gemini_cooldown(model_name, wait_time)
            print(f"⏳ Rate limit reached ({status_label}). Retrying in {wait_time:.0f}s... "
                  f"(Attempt {attempt + 1}/{max_retries})")
            time.sleep(wait_time)
        except Exception as e:
            print(f"❌ Error during {status_label}: {e}")
            raise
    return None


# =====================================================
# PROMPT 1: DELIVERABLES — exhaustive, chunked, page-scanned
# =====================================================

DELIVERABLE_CATEGORIES = (
    "Proposal Submission Package",
    "Required Forms, Certifications & Disclosures",
    "Technical Solution & Service Requirements",
    "Pricing & Commercial Response",
    "Bidder Qualifications, Experience & References",
    "Contract, Legal & Compliance Commitments",
    "Implementation, Transition & Project Delivery",
    "Post-Award Reporting & Ongoing Obligations",
    "Meetings, Questions & Pre-Submission Actions",
    "Other Required Proposal Commitments",
)


def split_rfp_for_deliverables(document_text, target_chars=24000):
    """Split on page boundaries; every form and attachment remains visible."""
    doc_re = re.compile(r"(\[START OF DOCUMENT:.*?\].*?\[END OF DOCUMENT:.*?\])", re.DOTALL)
    documents = doc_re.findall(document_text) or [document_text]
    chunks = []
    for document in documents:
        marker = re.search(r"\[START OF DOCUMENT:.*?\]", document)
        header = marker.group(0) + "\n" if marker else ""
        pages = re.split(r"(?=\[PAGE\s+\d+\])", document)
        buffer = ""
        for page in pages:
            if buffer and len(buffer) + len(page) > target_chars:
                chunks.append(header + buffer + "\n[END OF CHUNK]")
                buffer = ""
            buffer += page
        if buffer.strip():
            chunks.append(header + buffer + "\n[END OF CHUNK]")
    return chunks


def build_deliverables_page_prompt(source_chunk, chunk_no, chunk_count):
    return f"""
You are extracting source-grounded RFP deliverable records from chunk {chunk_no} of {chunk_count}.
Read EVERY line, table, attachment, form, signature page and appendix in this chunk.

Extract EACH distinct thing a bidder, proposer or contractor must submit, sign,
provide, acknowledge, complete, maintain or produce. Include minor forms,
attachments and post-award obligations. Do not merge separate requirements.
Use only facts in this chunk. If there are none, return exactly "# DELIVERABLES".

Do NOT create parent categories. Categories are handled separately. Return only:
# DELIVERABLES
- [Name] :: [Concise requirement] :: [Deadline or Not specified in RFP] :: [Page n or N/A] :: [8-20 word evidence] :: [Exact document filename] :: [Exact source section/heading] :: [Mandatory or Optional]

Exactly eight fields are mandatory, separated by ::. Never leave a field blank.
The seventh field is source provenance only; retain the exact useful heading even if it
is a raw section or attachment label. The eighth field must be exactly "Mandatory"
for an explicitly required item, or "Optional" only when the RFP explicitly permits
it as optional/discretionary.

SOURCE CHUNK:
{source_chunk}
"""


def _clean_deliverable_field(value):
    return re.sub(r"\s+", " ", value.replace("::", "—").strip())


def _parse_deliverable_candidates(candidates):
    records, seen = [], set()
    for candidate in candidates:
        if not candidate:
            continue
        for line in candidate.splitlines():
            raw = line.strip()
            if not raw.startswith("-") or raw.count("::") < 6:
                continue
            parts = [_clean_deliverable_field(part) for part in raw.lstrip("-").split("::")]
            if len(parts) < 7:
                continue
            if len(parts) == 7:
                parts.append("")
            elif len(parts) > 8:
                parts = parts[:6] + [" — ".join(parts[6:-1]), parts[-1]]
            if not all(parts[:7]):
                continue
            requirement_type = _normalize_requirement_type(parts[7], *parts[:5])
            fingerprint = "|".join(part.casefold() for part in parts[:7])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            records.append({
                "name": parts[0], "description": parts[1], "deadline": parts[2],
                "page": parts[3], "evidence": parts[4], "document": parts[5],
                "section": parts[6], "requirement_type": requirement_type,
            })
    return records


_ATTACHMENT_LABEL_RE = re.compile(r"\battachment\s+([a-z](?:[-\s]?\d+)?)\b", re.IGNORECASE)


def _normalize_deliverable_name(name):
    text = re.sub(r"^\[|\]$", "", name.strip())
    text = re.sub(r"\s+", " ", text)
    match = _ATTACHMENT_LABEL_RE.search(text)
    if match:
        return "attachment " + re.sub(r"[-\s]", "", match.group(1)).casefold()
    return text.casefold()


def _merge_duplicate_deliverables(records):
    groups, order = {}, []
    for record in records:
        key = (_normalize_deliverable_name(record["name"]), record["document"].casefold())
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(record)

    merged = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            merged.append(group[0])
            continue

        real_deadlines = [r["deadline"] for r in group
                           if r["deadline"] and "not specified" not in r["deadline"].casefold()]
        deadline = real_deadlines[0] if real_deadlines else group[0]["deadline"]

        base = dict(max(group, key=lambda r: len(r["description"])))

        section_tags, seen_tags = [], set()
        for r in group:
            tag = r["section"] if r["page"] in ("", "N/A") else f"{r['section']} ({r['page']})"
            if tag.casefold() not in seen_tags:
                seen_tags.add(tag.casefold())
                section_tags.append(tag)
        section = section_tags[0] if len(section_tags) == 1 else (
            f"{section_tags[0]} — also referenced in: {', '.join(section_tags[1:])}"
        )

        base["deadline"] = deadline
        base["section"] = section
        merged.append(base)
    return merged


def build_deliverable_category_prompt(records):
    rows = "\n".join(
        f"{r['id']} :: {r['name']} | {r['description']} | Source heading: {r['section']}"
        for r in records
    )
    allowed = "\n".join(f"- {category}" for category in DELIVERABLE_CATEGORIES)
    return f"""
You are organizing an already-extracted RFP deliverables register for a polished business UI.
Assign EVERY record ID below to exactly ONE category from the approved list.

Use reader-friendly requirement themes. Do NOT use raw section numbers, source headings,
attachment letters, document names, or generic labels as categories. Source headings remain
visible on each child row as evidence; they are not parent names. Do not omit, rename or
combine record IDs. Return only lines in this exact format: ID :: Category

APPROVED CATEGORIES:
{allowed}

RECORDS:
{rows}
"""


def _fallback_deliverable_category(record):
    text = " ".join(record[k] for k in ("name", "description", "section")).casefold()
    if any(k in text for k in ("price", "pricing", "cost", "fee", "financial proposal", "rate schedule")):
        return "Pricing & Commercial Response"
    if any(k in text for k in ("affidavit", "certif", "disclosure", "form", "w-9", "e-verify", "notar")):
        return "Required Forms, Certifications & Disclosures"
    if any(k in text for k in ("reference", "experience", "qualification", "resume", "past performance")):
        return "Bidder Qualifications, Experience & References"
    if any(k in text for k in ("technical", "solution", "scope", "system", "security", "service")):
        return "Technical Solution & Service Requirements"
    if any(k in text for k in ("meeting", "question", "conference", "clarification", "site visit")):
        return "Meetings, Questions & Pre-Submission Actions"
    if any(k in text for k in ("report", "ongoing", "renewal", "maintain", "post-award")):
        return "Post-Award Reporting & Ongoing Obligations"
    if any(k in text for k in ("implementation", "transition", "training", "project plan", "schedule")):
        return "Implementation, Transition & Project Delivery"
    if any(k in text for k in ("contract", "insurance", "legal", "compliance", "agreement", "term")):
        return "Contract, Legal & Compliance Commitments"
    if any(k in text for k in ("submit", "submission", "proposal", "bid", "upload", "envelope")):
        return "Proposal Submission Package"
    return "Other Required Proposal Commitments"


def _assign_deliverable_categories(records, max_retries):
    mapping = {}
    for offset in range(0, len(records), 70):
        batch = records[offset:offset + 70]
        response = call_gemini_with_retry(
            build_deliverable_category_prompt(batch),
            f"Deliverables category assignment {offset // 70 + 1}", max_retries,
            model_key="fast",
        )
        valid_ids = {r["id"] for r in batch}
        if response:
            for line in response.splitlines():
                if "::" not in line:
                    continue
                record_id, category = [x.strip() for x in line.split("::", 1)]
                if record_id in valid_ids and category in DELIVERABLE_CATEGORIES:
                    mapping[record_id] = category
    return {r["id"]: mapping.get(r["id"], _fallback_deliverable_category(r)) for r in records}


def _format_deliverable_register(records, category_by_id):
    grouped = {category: [] for category in DELIVERABLE_CATEGORIES}
    for record in records:
        grouped[category_by_id[record["id"]]].append(record)
    output = ["# DELIVERABLES"]
    for category, children in grouped.items():
        if not children:
            continue
        output.extend(["", f"## {category}"])
        for r in children:
            output.append(
                f"- {r['name']} :: {r['description']} :: {r['deadline']} :: {r['page']} :: "
                f"{r['evidence']} :: {r['document']} :: {r['section']} :: {r['requirement_type']}"
            )
    return "\n".join(output)


def extract_deliverables_exhaustively(document_text, max_retries=5):
    """Exhaustively extract child records (chunked page scan + lite model),
    then locally preserve, dedupe and group them — same algorithm as app.py,
    just without any Streamlit progress UI."""
    chunks = split_rfp_for_deliverables(document_text)
    if not chunks:
        return None
    candidates = []
    for index, chunk in enumerate(chunks, 1):
        result = call_gemini_with_retry(
            build_deliverables_page_prompt(chunk, index, len(chunks)),
            f"Deliverables source scan {index}/{len(chunks)}", max_retries,
            model_key="lite",
        )
        if result:
            candidates.append(result)
    records = _parse_deliverable_candidates(candidates)
    if not records:
        return "# DELIVERABLES\n\n## No bidder or contractor deliverables identified in the extracted source text."
    records = _merge_duplicate_deliverables(records)
    for index, record in enumerate(records, 1):
        record["id"] = f"D{index:04d}"
    category_by_id = _assign_deliverable_categories(records, max_retries)
    return _format_deliverable_register(records, category_by_id)


# =====================================================
# PROMPT 2: EVALUATION CRITERIA — detailed card format (matches app.py)
# =====================================================


def build_evaluation_prompt(document_text):
    return f"""
You are an SPS Proposal Capture Manager.

Analyze ALL uploaded RFP documents (each marked with [START OF DOCUMENT: filename.pdf] ... [END OF DOCUMENT: filename.pdf]).

STRICT RULES:
1. Use ONLY information present in the RFP text. Never guess or hallucinate.
2. If information is genuinely missing write: "Not specified in RFP" — do
   not invent a plausible-sounding criterion or weight.
3. Keep each individual bullet concise — but this does NOT apply to the
   overall extraction. Every distinct evaluation criterion, sub-criterion,
   weight, threshold, and disqualifying condition mentioned ANYWHERE in
   these documents must be captured.

Output EXACTLY in this format, and output NOTHING else — no preamble, no closing remarks.
Use the labels below exactly.

# EVALUATION CRITERIA

## Evaluation at a Glance
- **Award Method:** State the stated method (e.g. lowest evaluated price, best value, weighted scoring). If absent: Not specified in RFP.
- **Total Available Points / Weight:** State the total, if stated.
- **Technical Minimum Threshold:** State any technical pass mark, if stated.
- **Financial / Price Threshold:** State any price-related threshold or formula, if stated.
- **Evaluation Stages:** State the order of stages (e.g. mandatory screening, technical review, pricing, interview) if stated.

## 1. Technical Evaluation Criteria
For EVERY distinct technical criterion and sub-criterion, use this complete card format:

### [Exact Criterion Name]
- **What is assessed:** Concise description of what evaluators assess.
- **Weight / Points:** Exact weight, points, or percentage; otherwise Not specified in RFP.
- **Evidence expected:** Required proposal content, documents, demonstrations, references, or presentations; otherwise Not specified in RFP.
- **Scoring notes:** Any scoring method, qualitative standard, cap, or special rule; otherwise Not specified in RFP.
- **Source:** Document name • Page number • Section name.

Do not merge independently scored sub-criteria into one card. Repeat the card
format until every technical item is covered.

## 2. Financial Evaluation Criteria
For EVERY distinct pricing, cost, commercial, or value-for-money criterion, use:

### [Exact Financial Criterion Name]
- **What is assessed:** Concise description of the price/cost factor.
- **Weight / Points:** Exact weight, points, or percentage; otherwise Not specified in RFP.
- **Evaluation method:** State the formula, lowest-price method, best-value method, normalization approach, or stated method; otherwise Not specified in RFP.
- **Pricing evidence required:** Required pricing schedules, cost breakdowns, rate cards, or forms; otherwise Not specified in RFP.
- **Source:** Document name • Page number • Section name.

## 3. Mandatory Requirements (Pass / Fail)
For EVERY gating requirement, use:

### [Exact Requirement Name]
- **Requirement:** What must be submitted, confirmed, or complied with.
- **Consequence if unmet:** State the stated consequence; otherwise "May be treated as non-responsive / Not specified in RFP" only when that is all the RFP supports.
- **Source:** Document name • Page number • Section name.

## 4. Minimum Thresholds & Conditions
- List EVERY minimum score, qualification bar, required certification, evaluation-stage gate, or condition for advancing.
- For each item include: **Threshold / Condition**, **Applies to**, **Consequence**, and **Source** (Document name • Page number • Section name).
- If none are stated, write exactly: Not specified in RFP.

## 5. Disqualification Conditions
For EVERY stated rejection, ineligibility, or non-responsiveness condition, use:

### [Exact Disqualification Condition]
- **Trigger:** The action, omission, or circumstance that creates the risk.
- **Outcome:** Rejection, disqualification, non-responsiveness, loss of points, or other stated outcome.
- **Source:** Document name • Page number • Section name.

Never invent page numbers, section names, weights, formulas, or criteria.

RFP DOCUMENTS:
{document_text}
"""


# =====================================================
# PROMPT 3: COMPLIANCE CHECKLIST (8-column, matches app.py exactly)
# =====================================================


def build_checklist_prompt(document_text):
    return f"""
You are an SPS Proposal Capture Manager.

Analyze ALL uploaded RFP documents (each marked with [START OF DOCUMENT: filename.pdf] ... [END OF DOCUMENT: filename.pdf])
STRICTLY against the fixed checklist below. Do NOT use any generic knowledge — only what is written inside the RFP text.

STRICT RULES:
1. Use ONLY information present in RFP.
2. Never guess. Never hallucinate.
3. If information is missing write: "Not specified in RFP".
4. Keep each Explanation concise — but never skip or merge checklist items
   to save length. Every fixed item below must get its own row.
4b. Every Explanation must end with a short, natural cause-and-effect
    clause that names the resulting Decision, so the reader never has to
    guess WHY that Decision was reached. Keep this clause short (roughly
    8-15 words) and vary the phrasing naturally.
5. Remove duplicate information.
6. Check EACH item and decide its Status/Decision before outputting.
7. Every row must ALSO carry FOUR extra fields at the end — "Reference from RFP",
   "Page No", "Document Name", and "Section Name":
   - Reference from RFP: quote or closely paraphrase the EXACT short
     phrase/sentence from the RFP text (roughly 8-20 words) that proves the
     Status/Decision you gave for that item. If the item's Status is
     ❌ NOT FOUND (truly not mentioned anywhere), write "Not specified in RFP".
   - Page No: the page number where that reference appears, taken from the
     nearest "[PAGE n]" marker in the RFP text near that reference (write it
     as e.g. "Page 4"). If the Status is ❌ NOT FOUND, write "N/A".
   - Document Name: the exact filename of the document this reference came
     from. If the item's Status is ❌ NOT FOUND, write "N/A".
   - Section Name: the short section number/heading this reference falls
     under. If no clear section heading exists, write "General Requirements".
     If the item's Status is ❌ NOT FOUND, write "N/A".
8. Every row must also carry a per-item Decision of GO, NO-GO, or MAYBE:
   - Payment Terms: NET30 → ✅ FOUND / GO. More than NET30 → ⚠️ ACTION REQUIRED / MAYBE. Not mentioned → ❌ NOT FOUND / NO-GO.
   - Financial Stability Requirements: clear requirement stated → ✅ FOUND / GO (note unaudited statements acceptable unless audited explicitly required, and that SPS finance must confirm internally it can produce the documentation). General "may investigate + shall furnish info as requested" clause → ⚠️ ACTION REQUIRED / MAYBE (flag as contingent obligation, note SPS finance should be ready to produce info later). Truly silent (no mention at all) → ❌ NOT FOUND / GO (not a risk).
   - Insurance Requirements: exactly $5M → ✅ FOUND / GO. More than $5M → ⚠️ ACTION REQUIRED / NO-GO (hard limit). Not mentioned → ❌ NOT FOUND / MAYBE (confirm with client). Always end the Explanation noting SPS's finance/insurance team must separately confirm SPS's own coverage meets or can be upgraded to the stated amount.
   - Profitability Analysis: this is always the bidder's own internal exercise. RFP gives enough figures to readily perform it → ✅ FOUND / GO. Partial figures → ⚠️ ACTION REQUIRED / MAYBE. No relevant figures at all (normal case) → ❌ NOT FOUND / MAYBE (a to-do flag, never NO-GO).
   - Capability (Qualified Personnel/Technical Knowhow): based only on whether the RFP asks for personnel/skills disclosure, never on SPS's actual staffing. Clearly requires disclosure → ✅ FOUND / GO (Explanation ends noting SPS must confirm internally it has matching staff). Vague/ambiguous → ⚠️ ACTION REQUIRED / MAYBE. Not mentioned at all → ❌ NOT FOUND / GO (not a risk).
   - Quantum of Input Required (Period of Implementation, Insurance Coverage, Compliance of Law — Expected Revenue Generation is always SPS's own internal estimate and must never pull this down): all three RFP-derivable sub-parts clearly stated → ✅ FOUND / GO. Some missing/ambiguous → ⚠️ ACTION REQUIRED / MAYBE. None addressed → ❌ NOT FOUND / NO-GO. Explanation always ends noting Expected Revenue Generation is SPS's own internal projection, not something the RFP is expected to provide.
   - Scope Alignment: Status is about whether the RFP describes its scope at all (almost always ✅ FOUND; ❌ NOT FOUND only if genuinely no scope description exists). Decision is about whether that scope matches SPS's portfolio (Identity and Access Management, cybersecurity, identity governance, access control): GO if genuinely IAM/cybersecurity/identity/access-control; NO-GO if unrelated (even though Status stays FOUND); MAYBE only if partially related/ambiguous.
   - Bid Bond: required → ✅ FOUND / GO (normal, satisfiable). Vague/ambiguous → ⚠️ ACTION REQUIRED / MAYBE. Not mentioned at all → ❌ NOT FOUND / GO (no bond required, not a risk).
   - E-Verify: required → ✅ FOUND / GO. Vague/ambiguous → ⚠️ ACTION REQUIRED / MAYBE. Not mentioned at all → ❌ NOT FOUND / GO (not a risk).
   - All other items: ✅ FOUND → GO. ⚠️ ACTION REQUIRED (partial/ambiguous) → MAYBE. ❌ NOT FOUND (absent) → NO-GO.
9. Do not invent or fabricate any Reference from RFP text — it must be real wording taken from (or tightly paraphrased from) the RFP documents provided.

Output EXACTLY in this format, and output NOTHING else — no preamble, no closing remarks:

# COMPLIANCE CHECKLIST

## FINANCE TEAM
| Item | Status | Decision | Explanation | Reference from RFP | Page No | Document Name | Section Name |
|------|--------|----------|-------------|--------------------|---------|---------------|--------------|
| Payment Terms (NET30 rule) | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Financial Stability | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Insurance Requirements ($5M rule) | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Profitability Analysis | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Bid Bond | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |

## LEGAL TEAM
| Item | Status | Decision | Explanation | Reference from RFP | Page No | Document Name | Section Name |
|------|--------|----------|-------------|--------------------|---------|---------------|--------------|
| Eligibility Criteria | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Capability | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Quantum of Input | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Data Protection | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| State Registration | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| E-Verify | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Contractual Obligations | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |

## OPERATIONS TEAM
| Item | Status | Decision | Explanation | Reference from RFP | Page No | Document Name | Section Name |
|------|--------|----------|-------------|--------------------|---------|---------------|--------------|
| Required Forms | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Submission Deadlines | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Document Compliance | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Signatory Authority | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Required Documents | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Responsible Person | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Meeting with Ops | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Vendor Registration | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |

## TECHNICAL TEAM
| Item | Status | Decision | Explanation | Reference from RFP | Page No | Document Name | Section Name |
|------|--------|----------|-------------|--------------------|---------|---------------|--------------|
| Scope Alignment | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Technical Requirements | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Industry Standards | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Security Requirements | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |
| Integration Needs | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase, or "Not specified in RFP"] | [Page No, or "N/A"] | [Document filename] | [Section heading, or "General Requirements"] |

RFP DOCUMENTS:
{document_text}
"""


# =====================================================
# PROMPT 4: QUALIFICATION DECISION (deadline-override aware)
# =====================================================


def build_decision_prompt(checklist_text, overall_pct, correct_decision, deadline_overdue=False):
    deadline_note = (
        "\nIMPORTANT: The RFP's primary bid submission deadline has ALREADY "
        "PASSED as of today. This is why the Final Decision is NO-GO "
        "regardless of the compliance score — the bid window is closed and "
        "this opportunity can no longer be submitted. Your Justification "
        "MUST lead with this fact before mentioning any other checklist "
        "findings.\n" if deadline_overdue else ""
    )
    return f"""
You are an SPS Proposal Capture Manager writing the final qualification
verdict for an RFP, based on the compliance checklist below (already
finalized — do not recompute or contradict its findings).

The Overall Score has ALREADY been calculated as {overall_pct:.1f}%.
The Final Decision has ALREADY been determined as: {correct_decision}.
Do NOT recalculate these — simply write the narrative that explains and
supports them, referencing the SPECIFIC checklist item(s) responsible for
any MAYBE or NO-GO (especially Finance team rows: Payment Terms, Insurance
Requirements).
{deadline_note}
COMPLIANCE CHECKLIST (for your reference only):
{checklist_text}

Output EXACTLY in this format, and output NOTHING else — no preamble, no closing remarks:

# QUALIFICATION DECISION

Strategic Fit: [Strong / Moderate / Poor]
Capability Alignment: [Strong / Moderate / Poor]
Financial Viability: [Viable / Needs Review / Not Viable]
Risk Assessment: [Low / Medium / High]

## FINAL RECOMMENDATION

Final Decision: {correct_decision}

## JUSTIFICATION

[Clear 3-4 sentence explanation. If the decision is MAYBE or NO-GO,
explicitly name WHICH item(s) caused it so the reason is obvious, not
generic. Cover: why this decision was made, key strengths identified, key
risks or gaps (name the specific flagged item(s)), and what needs to
happen next.]
"""


# =====================================================
# PROMPT 5: VERIFICATION — independent QA pass (appended to raw report)
# =====================================================


def build_verification_prompt(document_text, combined_report):
    today_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    return f"""
You are an independent QA / Verification Agent for an RFP Proposal Capture
System. You did NOT write the report below — a separate agent did. Your
ONLY job is to audit it against the source RFP text for accuracy.

Today's actual real-world date is {today_str}. Use this when judging any
claim in the report about a deadline having "already passed" or being
"overdue".

Check the report against the source text for: hallucinations (anything not
actually present in the RFP), omissions (clearly-stated requirements missing
from the report), scoring/logic issues, and internal contradictions.

IMPORTANT — a known, INTENTIONAL rule (do NOT flag this as an error): if the
RFP's primary bid submission deadline falls before today's actual date
above, the Final Decision is deliberately forced to NO-GO regardless of the
Overall Score, and the Justification will contain an "⚠️ OVERRIDE" note.
This is correct, expected behavior — only flag it if the cited deadline date
is factually wrong.

STRICT RULES:
1. Do NOT rewrite or regenerate the report. You are auditing it, not redoing it.
2. Only flag something if you can point to a concrete mismatch.
3. Be concise — this is a QA summary, not a new report.

Output EXACTLY in this format, nothing else:

# VERIFICATION SUMMARY

Confidence: [High / Medium / Low]

## Issues Found
If there are no issues, write exactly:
- No material issues found — report is well-grounded in the source RFP.

Otherwise, output ONE block per issue, back to back, in exactly this form:
### ISSUE
Type: [Hallucination / Omission / Internal Contradiction / Scoring or Logic Issue]
Where: [Short section/row reference]
Problem: [One concise sentence describing what's wrong]
### END ISSUE

## Notes
[Optional 1-2 sentence caveat. Omit this line entirely if not needed.]

================================================
ORIGINAL RFP DOCUMENT TEXT:
================================================
{document_text}

================================================
REPORT TO VERIFY:
================================================
{combined_report}
"""


# =====================================================
# ORCHESTRATOR (headless version of app.py's analyze_rfp)
# =====================================================


def analyze_rfp_headless(document_text, max_retries=5):
    """
    Runs the exact same 5-agent pipeline as app.py's analyze_rfp():
      1-3. Deliverables / Evaluation / Checklist  — run in PARALLEL
      4.   Decision narrative (Python-computed score/decision, agent just
           explains it)
      5.   Independent verification pass (appended as its own top-level
           "# VERIFICATION SUMMARY" section at the end of the report)

    Returns a single raw markdown report string (same shape api.py/
    rfp_json_formatter.report_to_json already expect). The verification
    section is additive text at the end and does not interfere with
    report_to_json's section parsing.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {
            executor.submit(extract_deliverables_exhaustively, document_text, max_retries): "deliverables",
            executor.submit(call_gemini_with_retry, build_evaluation_prompt(document_text),
                             "Evaluation Criteria", max_retries, "fast"): "evaluation",
            executor.submit(call_gemini_with_retry, build_checklist_prompt(document_text),
                             "Compliance Checklist", max_retries, "fast"): "checklist",
        }
        parallel_results = {}
        for future in concurrent.futures.as_completed(future_map):
            key = future_map[future]
            parallel_results[key] = future.result()

    deliverables_text = parallel_results["deliverables"]
    evaluation_text = parallel_results["evaluation"]
    checklist_text = parallel_results["checklist"]

    if not deliverables_text:
        raise Exception("Deliverables extraction failed")
    if not evaluation_text:
        raise Exception("Evaluation criteria extraction failed")
    if not checklist_text:
        raise Exception("Compliance checklist failed")

    scores = recompute_scores(checklist_text)
    deadline_overdue = _primary_deadline_overdue(deliverables_text)
    if scores:
        overall_pct = sum(v["pct"] for v in scores.values()) / len(scores)
        finance = scores.get("Finance Score")
        finance_maybe = finance["maybe"] if finance else 0
        finance_nogo = finance["nogo"] if finance else 0
        correct_decision = determine_final_decision(overall_pct, finance_maybe, finance_nogo, deadline_overdue)
    else:
        overall_pct = 0
        correct_decision = "NO-GO" if deadline_overdue else "MAYBE"

    decision_text = call_gemini_with_retry(
        build_decision_prompt(checklist_text, overall_pct, correct_decision, deadline_overdue),
        "Qualification Decision", max_retries, model_key="pro",
    )
    if not decision_text:
        raise Exception("Decision generation failed")

    combined = f"""{deliverables_text.strip()}

{evaluation_text.strip()}

{checklist_text.strip()}

# SCORING SUMMARY

Finance Score: 0%
Legal Score: 0%
Operations Score: 0%
Technical Score: 0%

Overall Score: 0%

{decision_text.strip()}
"""
    fixed_text = apply_score_fix(combined)

    verification_notes = call_gemini_with_retry(
        build_verification_prompt(document_text, fixed_text),
        "Verification", max_retries, model_key="pro",
    )
    if not verification_notes:
        verification_notes = (
            "# VERIFICATION SUMMARY\n\nConfidence: Unknown\n\n"
            "## Issues Found\n- Verification agent could not be reached; "
            "report was not independently checked.\n"
        )

    return f"{fixed_text}\n\n{verification_notes.strip()}\n"