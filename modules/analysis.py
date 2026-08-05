import concurrent.futures
import os
import queue
import random
import re
import threading
import time

import streamlit as st
from google.api_core import exceptions

from .config import configure_gemini
from .scoring import apply_score_fix, determine_final_decision

MODELS = configure_gemini()
if MODELS is None:
    # The UI gives the user the friendly error before analysis can begin.
    MODELS = {}

GEMINI_MIN_INTERVAL_SECONDS = max(0.5, float(os.getenv("GEMINI_MIN_INTERVAL_SECONDS", "6.0")))
_gemini_pacing_lock = threading.Lock()
_gemini_next_request_at = {}  # model_name -> monotonic timestamp


def _acquire_gemini_slot(model_name):
    """Reserve one paced request slot for this specific underlying model."""
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
    """Make every worker on this model respect a cooldown returned by Gemini."""
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


def call_gemini_with_retry(prompt, status_label="Analyzing...", max_retries=5, model_key="fast", silent=False, status_queue=None):
    """Gemini caller with coordinated quota pacing and retry cooldowns.

    Pacing/cooldowns are scoped to the underlying model name, so "fast" and
    "pro" (same model) keep sharing one gate, while "lite" (a different
    model/quota) paces independently instead of queueing behind them.
    """
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
            msg = f"⏳ Rate limit reached ({status_label}). Coordinating retry in {wait_time:.0f}s... (Attempt {attempt + 1}/{max_retries})"
            # Background workers cannot safely update Streamlit directly.
            # Send their retry status to the main UI instead of printing it
            # in the terminal.
            if status_queue is not None:
                status_queue.put(msg)
            elif not silent:
                st.warning(msg)
            time.sleep(wait_time)
        except Exception as e:
            error_msg = f"❌ Error during {status_label}: {e}"
            if status_queue is not None:
                status_queue.put(error_msg)
            elif not silent:
                st.error(error_msg)
            raise
    return None

# =====================================================
# PROMPT 1: DELIVERABLES ONLY
# =====================================================

def build_deliverables_prompt(document_text):
    return f"""
You are an SPS Proposal Capture Manager.

Analyze ALL uploaded RFP documents. Each document is clearly marked with:
- [START OF DOCUMENT: filename.pdf]
- [END OF DOCUMENT: filename.pdf]

For EVERY deliverable you extract, you MUST identify which document it came from AND which section/heading it belongs to.

STRICT RULES:
1. Use ONLY information present in RFP.
2. Never guess. Never hallucinate.
3. If information is missing write: "Not specified in RFP".
4. Keep each individual DESCRIPTION concise — but this does NOT apply to
   the overall extraction. The number of deliverables and parent
   categories you list must be EXHAUSTIVE, never trimmed for brevity.
5. Remove duplicate information (the exact same deliverable listed twice).
6. Do not add references from your own.

⚠️ COMPLETENESS OVERRIDE — READ CAREFULLY:
Your default instinct may be to summarize, consolidate, or return a
"representative" subset of deliverables to keep the answer short and
token-efficient. For THIS task, that instinct is WRONG and must be
overridden. There is no length limit and no reward for brevity here —
an incomplete extraction is a FAILED extraction, even if every item you
did list is accurate. A real government/enterprise RFP of this size
typically contains many dozens of individual deliverables spread across
5-15+ distinct parent categories (submission forms, technical narrative,
pricing/cost forms, licensing/certifications, insurance, staffing,
security/compliance, references, timelines, post-award documents,
pre-bid/conference items, etc. — the EXACT categories depend on what
THESE documents actually contain). If your first pass produces fewer
than ~5 parent categories or seems short relative to the length of the
source documents, that is a signal you stopped too early — go back
through EVERY section, attachment, form, and appendix of EVERY document
again before finalizing.

================================================

# DELIVERABLES

Extract EVERY SINGLE deliverable, submission requirement, form, document, or
action item required from the bidder ANYWHERE in these RFP documents — this must be a
COMPLETE, EXHAUSTIVE extraction across ALL uploaded documents, not a partial or representative sample.

MANDATORY COMPLETENESS PROCESS:
1. Scan ALL RFP documents from beginning to end — submission instructions,
   statement of needs/scope, evaluation criteria, forms, attachments,
   appendices, terms and conditions, and any other section — for anything
   the bidder/Contractor is required to prepare, sign, submit, include,
   acknowledge, or provide.
2. For EVERY deliverable, you MUST identify WHICH DOCUMENT it came from
   (the filename) AND WHICH SECTION/HEADING it appears under.
   The document name appears in the markers:
   [START OF DOCUMENT: filename.pdf] ... [END OF DOCUMENT: filename.pdf]
3. For Section Name, provide the exact short section heading or identifier
   nearest to the requirement (for example "3.2 Technical Proposal
   Requirements" or "Attachment A — Required Forms"). If there is genuinely
   no heading, write "General Requirements" or "N/A".
4. Do NOT skip a deliverable just because it seems minor, is only mentioned
   once, or appears inside an attachment/appendix rather than the main body.
   A one-line requirement (e.g. "submit a signed W-9") is just as much a
   deliverable as a multi-page technical narrative.
5. Before finalizing your output, mentally re-check all documents one more
   time and confirm nothing required of the bidder has been left out.
   Completeness is more important than brevity here.

Organize everything you find into a TWO-LEVEL PARENT-CHILD structure:

- Group the deliverables under as MANY logical PARENT categories as are
  genuinely needed based on THESE RFPs' actual content and structure —
  do NOT artificially cap the number of categories, and do NOT force unrelated
  deliverables together just to keep the count low. If these RFPs genuinely
  have 6, 7, 8+ distinct deliverable themes, create that many parent categories.
  Equally, do not invent extra categories that aren't really needed — the
  number of categories should be whatever the RFPs themselves naturally produce.
  Do NOT reuse a fixed, generic set of category names for every RFP. Look at
  what these particular RFPs actually ask for and name the parent categories
  accordingly.
- ACCURACY IS CRITICAL: every deliverable, category name, and deadline must
  come strictly from what is actually written in the RFP text. Never invent,
  assume, or guess a deliverable that isn't there. If the RFP itself explicitly
  names a section/heading that groups certain requirements, REUSE THAT EXACT
  WORDING as the parent category name. If a deadline is not stated for a
  specific deliverable, write "Not specified in RFP" rather than guessing one.
- Every individual deliverable is a CHILD that belongs to exactly one parent
  category. Do not create an empty parent category.
- EVERY child row must always carry all EIGHT pieces of information — Name,
  Description, Deadline, Page Number, Reference/Evidence snippet, Document Name,
  Section Name, and Requirement Type. Never leave any field blank.
- REFERENCE FROM RFP (5th field): for every deliverable, quote or closely
  paraphrase the EXACT short phrase/sentence from the RFP text that proves
  this deliverable exists. Keep it SHORT (roughly 8-20 words), taken directly
  from (or tightly paraphrased from) the RFP text near the matching "[PAGE n]"
  marker.
- The document name (6th field) should be the exact filename as shown in the
  markers, e.g. "RFP_Solicitation_123.pdf" or "Attachment_A_Forms.pdf".
- The section name (7th field) should be the exact heading/title of the section
  where this deliverable appears, e.g. "3.2 Technical Proposal Requirements",
  "Section 4 - Submission Instructions", "Attachment A", "Required Forms", etc.
  If no clear section heading exists, write "General Requirements".
- The Requirement Type (8th field) must be exactly "Mandatory" when the RFP
  explicitly requires it (must, shall, required), or exactly "Optional" only when
  the RFP explicitly says it is optional, discretionary, or may be submitted.
- The RFP document text below contains page markers in the exact form
  "[PAGE n]" showing where each page begins. For every deliverable you list,
  look at which "[PAGE n]" marker the requirement appeared under/near in the
  text and report that page number as the 4th field.
- Do not use a markdown table for this section.

Output EXACTLY in this format (repeat the "## Parent" block for each category), and output NOTHING else — no preamble, no closing remarks:

# DELIVERABLES

## [Parent Category Name]
- [Deliverable Name] :: [Short Description] :: [Deadline, or "Not specified in RFP"] :: [Page Number, e.g. "Page 4", or "N/A"] :: [Reference/Evidence snippet from RFP] :: [Document Name] :: [Section Name] :: [Mandatory or Optional]

## [Parent Category Name 2]
- [Deliverable Name] :: [Short Description] :: [Deadline, or "Not specified in RFP"] :: [Page Number, e.g. "Page 4", or "N/A"] :: [Reference/Evidence snippet from RFP] :: [Document Name] :: [Section Name] :: [Mandatory or Optional]

Rules for this section:
- Use "::" EXACTLY as the separator between Deliverable Name, Description,
  Deadline, Page Number, Reference, Document Name, Section Name, and Requirement Type.
- Do NOT use "|" or any markdown table syntax anywhere in this section.
- Keep each Description to one concise but complete sentence.
- Every deliverable actually present in the RFPs must appear under some parent —
  do not drop any deliverable. When in doubt about whether something counts as
  a deliverable, include it rather than omit it.
- Do NOT truncate your answer early to save length/tokens. If you have not
  yet covered every page and every attachment/appendix of every document,
  you are not done — keep going until the full document set has been
  scanned, even if that means a very long output.

RFP DOCUMENTS:
{document_text}
"""


# =====================================================
# DELIVERABLES COMPLETENESS REVIEW — SECOND PASS
# =====================================================
def build_deliverables_completion_prompt(document_text, draft_deliverables):
    return f"""
You are performing a FINAL COMPLETENESS AUDIT of an RFP deliverables register.

Below are (1) the full source RFP text and (2) a draft register. Return a
COMPLETE REPLACEMENT register, not comments about the draft.

Your mission is to find every bidder/contractor deliverable that the draft
missed, especially items hidden in forms, appendices, certifications,
submission instructions, pricing schedules, signatures, acknowledgements,
insurance, references, staffing, compliance requirements, and post-award
requirements. Review every source page and attachment before answering.

IMPORTANT:
- Preserve every valid existing row; ADD missing rows rather than shortening
  or summarizing the register.
- Remove only genuine exact duplicates.
- Count separate forms, certificates, acknowledgements, and required actions
  as separate deliverables when the RFP identifies them separately.
- Do not invent requirements. Every row must have a supporting source.
- Keep all eight fields for every row, including page, evidence, document,
  section, and requirement type (Mandatory or Optional).

Return EXACTLY this format and NOTHING else:
# DELIVERABLES

## [Parent Category]
- [Deliverable Name] :: [Short Description] :: [Deadline or Not specified in RFP] :: [Page Number or N/A] :: [Short evidence from RFP] :: [Document Name] :: [Section Name] :: [Mandatory or Optional]

SOURCE RFP DOCUMENTS:
{document_text}

DRAFT DELIVERABLES REGISTER:
{draft_deliverables}
"""


# =====================================================
# DELIVERABLES PIPELINE — COMPLETE, RATE-SAFE, HUMAN-CATEGORIZED
# =====================================================
# The source of truth is the locally preserved child record, not a model merge.
# This guarantees that a category cleanup can never erase a deliverable.
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
    doc_re = re.compile(r'(\[START OF DOCUMENT:.*?\].*?\[END OF DOCUMENT:.*?\])', re.DOTALL)
    documents = doc_re.findall(document_text) or [document_text]
    chunks = []
    for document in documents:
        marker = re.search(r'\[START OF DOCUMENT:.*?\]', document)
        header = marker.group(0) + '\n' if marker else ''
        pages = re.split(r'(?=\[PAGE\s+\d+\])', document)
        buffer = ''
        for page in pages:
            if buffer and len(buffer) + len(page) > target_chars:
                chunks.append(header + buffer + '\n[END OF CHUNK]')
                buffer = ''
            buffer += page
        if buffer.strip():
            chunks.append(header + buffer + '\n[END OF CHUNK]')
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
    return re.sub(r'\s+', ' ', value.replace('::', '—').strip())


def _parse_deliverable_candidates(candidates):
    """Parse every syntactically usable row into immutable source records."""
    records, seen = [], set()
    for candidate in candidates:
        if not candidate:
            continue
        for line in candidate.splitlines():
            raw = line.strip()
            if not raw.startswith('-') or raw.count('::') < 6:
                continue
            parts = [_clean_deliverable_field(part) for part in raw.lstrip('-').split('::')]
            if len(parts) < 7:
                continue
            # Keep the source-section field intact if an older response has extra
            # separators. New responses use field 8 for the requirement type.
            if len(parts) == 7:
                parts.append('')
            elif len(parts) > 8:
                parts = parts[:6] + [' — '.join(parts[6:-1]), parts[-1]]
            if not all(parts[:7]):
                continue
            requirement_type = _normalize_requirement_type(parts[7], *parts[:5])
            fingerprint = '|'.join(part.casefold() for part in parts[:7])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            records.append({
                'name': parts[0], 'description': parts[1], 'deadline': parts[2],
                'page': parts[3], 'evidence': parts[4], 'document': parts[5],
                'section': parts[6], 'requirement_type': requirement_type,
            })
    return records


_ATTACHMENT_LABEL_RE = re.compile(r'\battachment\s+([a-z](?:[-\s]?\d+)?)\b', re.IGNORECASE)


def _normalize_deliverable_name(name):
    """Return a grouping key for a deliverable name. If the name references a
    lettered/numbered Attachment (e.g. "Attachment C", "Attachment E-1"), the
    Attachment label itself is the key — the RFP routinely refers to the SAME
    physical attachment with slightly different wording in different sections
    ("Attachment C - State Contract Affidavit" vs "Attachment C - Contract
    Affidavit"), and those must be recognized as one deliverable. Otherwise,
    fall back to the cleaned full name.
    """
    text = re.sub(r'^\[|\]$', '', name.strip())
    text = re.sub(r'\s+', ' ', text)
    match = _ATTACHMENT_LABEL_RE.search(text)
    if match:
        return 'attachment ' + re.sub(r'[-\s]', '', match.group(1)).casefold()
    return text.casefold()


def _merge_duplicate_deliverables(records):
    """Collapse repeated mentions of the same underlying deliverable (same
    normalized name + same source document) into a single row instead of
    one row per section it happens to be mentioned in. When merging, also
    backfill a missing deadline from a sibling mention that does state one,
    so the same real requirement doesn't show "Not specified in RFP" in one
    row and a real date in another.
    """
    groups, order = {}, []
    for record in records:
        key = (_normalize_deliverable_name(record['name']), record['document'].casefold())
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

        # Prefer a real stated deadline over "Not specified in RFP" from any sibling mention.
        real_deadlines = [r['deadline'] for r in group
                           if r['deadline'] and 'not specified' not in r['deadline'].casefold()]
        deadline = real_deadlines[0] if real_deadlines else group[0]['deadline']

        # Use the most detailed description as the representative one.
        base = dict(max(group, key=lambda r: len(r['description'])))

        # Preserve every section this deliverable was actually referenced in,
        # so nothing is silently dropped — just consolidated into one row.
        section_tags, seen_tags = [], set()
        for r in group:
            tag = r['section'] if r['page'] in ('', 'N/A') else f"{r['section']} ({r['page']})"
            if tag.casefold() not in seen_tags:
                seen_tags.add(tag.casefold())
                section_tags.append(tag)
        section = section_tags[0] if len(section_tags) == 1 else (
            f"{section_tags[0]} — also referenced in: {', '.join(section_tags[1:])}"
        )

        base['deadline'] = deadline
        base['section'] = section
        merged.append(base)
    return merged


def _apply_amendment_precedence(records, amendment_filenames=None):
    """When an addendum is analyzed together with the original RFP, the same
    deliverable (e.g. "Primary Bid Document") ends up as TWO separate rows —
    one extracted from the original RFP's document block and one extracted
    from the addendum's document block — because _merge_duplicate_deliverables
    only collapses rows that share the exact same source `document` filename.
    Since the original and the addendum are different files, that dedup never
    fires, and BOTH the old (superseded) value and the new (addendum) value
    survive into the final register side by side — which is exactly the kind
    of internal contradiction (stale July 16 date next to corrected Aug 13
    date) the verification agent flags. This second pass runs ONLY for
    addendum re-analyses and re-collapses by name alone, letting the
    addendum's version win whenever the same deliverable also has an entry
    from a pre-addendum document.
    """
    if not amendment_filenames:
        return records

    amendment_names = {f.strip().casefold() for f in amendment_filenames if f}

    def _is_amendment_doc(document_field):
        doc = (document_field or '').casefold()
        if doc in amendment_names:
            return True
        # Fallback fuzzy match in case the extraction agent paraphrased the
        # filename slightly (e.g. dropped punctuation/extension).
        return any(name and (name in doc or doc in name) for name in amendment_names)

    groups, order = {}, []
    for record in records:
        key = _normalize_deliverable_name(record['name'])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(record)

    reconciled = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            reconciled.append(group[0])
            continue

        amendment_rows = [r for r in group if _is_amendment_doc(r['document'])]
        prior_rows = [r for r in group if not _is_amendment_doc(r['document'])]

        if not amendment_rows or not prior_rows:
            # Either no addendum touched this deliverable, or every mention
            # of it came from addendum documents only — nothing to reconcile.
            reconciled.extend(group)
            continue

        # The addendum version is authoritative. Use its deadline/description,
        # but make the override explicit and keep the prior value visible so
        # nothing is silently lost — this is what previously showed up as an
        # unexplained contradiction between two separate rows.
        winner = dict(max(amendment_rows, key=lambda r: len(r['description'])))
        prior_deadline = next(
            (r['deadline'] for r in prior_rows
             if r['deadline'] and 'not specified' not in r['deadline'].casefold()),
            None,
        )
        if prior_deadline and prior_deadline.casefold() != winner['deadline'].casefold():
            winner['deadline'] = f"{winner['deadline']} (updated by addendum — supersedes prior date of {prior_deadline})"

        all_sections = [winner['section']] + [
            r['section'] for r in prior_rows if r['section'].casefold() != winner['section'].casefold()
        ]
        seen_sections, section_tags = set(), []
        for tag in all_sections:
            if tag.casefold() not in seen_sections:
                seen_sections.add(tag.casefold())
                section_tags.append(tag)
        winner['section'] = section_tags[0] if len(section_tags) == 1 else (
            f"{section_tags[0]} — supersedes: {', '.join(section_tags[1:])}"
        )
        reconciled.append(winner)

    return reconciled


def _sync_amendment_deadlines(records, amendment_filenames=None):
    """Correct the deadline on deliverables the addendum never mentioned by
    name at all.

    Addenda typically state ONE blanket deadline change (e.g. "the
    submission deadline is extended to August 13, 2026") without individually
    re-listing every affected item (Bid Document, PIA Copy, Transmittal
    Letter, Attachment B, ...). _apply_amendment_precedence only fixes items
    that appear on BOTH sides under a matching name — everything else silently
    keeps the stale date from the original RFP extraction, which is exactly
    the "internal contradiction" the verification agent keeps catching.

    This pass is name-agnostic: it finds the deadline the addendum itself
    states, finds the dominant (2+) Mandatory deadline still held by non-
    addendum records, and if they differ, rewrites EVERY record still
    carrying the stale date — whatever its name is. This is meant to hold
    for any future addendum, not just this specific RFP's wording.
    """
    if not amendment_filenames:
        return records

    from collections import Counter
    amendment_names = {f.strip().casefold() for f in amendment_filenames if f}

    def _is_amendment_doc(document_field):
        doc = (document_field or '').casefold()
        if doc in amendment_names:
            return True
        return any(name and (name in doc or doc in name) for name in amendment_names)

    amendment_deadlines = [
        r['deadline'] for r in records
        if _is_amendment_doc(r['document'])
        and r['deadline'] and 'not specified' not in r['deadline'].casefold()
        and 'updated by addendum' not in r['deadline'].casefold()
    ]
    if not amendment_deadlines:
        return records
    new_deadline, _ = Counter(amendment_deadlines).most_common(1)[0]

    prior_mandatory_deadlines = [
        r['deadline'] for r in records
        if not _is_amendment_doc(r['document'])
        and r.get('requirement_type') == 'Mandatory'
        and r['deadline'] and 'not specified' not in r['deadline'].casefold()
        and 'updated by addendum' not in r['deadline'].casefold()
    ]
    if not prior_mandatory_deadlines:
        return records
    old_deadline, old_count = Counter(prior_mandatory_deadlines).most_common(1)[0]

    if old_count < 2 or old_deadline.casefold() == new_deadline.casefold():
        return records

    note = f"{new_deadline} (updated by addendum — supersedes prior date of {old_deadline})"
    for record in records:
        if (
            not _is_amendment_doc(record['document'])
            and record['deadline'].casefold() == old_deadline.casefold()
        ):
            record['deadline'] = note
    return records


def build_deliverable_category_prompt(records):
    rows = '\n'.join(
        f"{r['id']} :: {r['name']} | {r['description']} | Source heading: {r['section']}"
        for r in records
    )
    allowed = '\n'.join(f'- {category}' for category in DELIVERABLE_CATEGORIES)
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
    text = ' '.join(record[k] for k in ('name', 'description', 'section')).casefold()
    if any(k in text for k in ('price', 'pricing', 'cost', 'fee', 'financial proposal', 'rate schedule')):
        return 'Pricing & Commercial Response'
    if any(k in text for k in ('affidavit', 'certif', 'disclosure', 'form', 'w-9', 'e-verify', 'notar')):
        return 'Required Forms, Certifications & Disclosures'
    if any(k in text for k in ('reference', 'experience', 'qualification', 'resume', 'past performance')):
        return 'Bidder Qualifications, Experience & References'
    if any(k in text for k in ('technical', 'solution', 'scope', 'system', 'security', 'service')):
        return 'Technical Solution & Service Requirements'
    if any(k in text for k in ('meeting', 'question', 'conference', 'clarification', 'site visit')):
        return 'Meetings, Questions & Pre-Submission Actions'
    if any(k in text for k in ('report', 'ongoing', 'renewal', 'maintain', 'post-award')):
        return 'Post-Award Reporting & Ongoing Obligations'
    if any(k in text for k in ('implementation', 'transition', 'training', 'project plan', 'schedule')):
        return 'Implementation, Transition & Project Delivery'
    if any(k in text for k in ('contract', 'insurance', 'legal', 'compliance', 'agreement', 'term')):
        return 'Contract, Legal & Compliance Commitments'
    if any(k in text for k in ('submit', 'submission', 'proposal', 'bid', 'upload', 'envelope')):
        return 'Proposal Submission Package'
    return 'Other Required Proposal Commitments'


def _assign_deliverable_categories(records, max_retries, status_queue=None):
    """Classify IDs only; the local source records remain untouched and complete."""
    mapping = {}
    # Small batches prevent a huge category response from becoming its own quota/output issue.
    for offset in range(0, len(records), 70):
        batch = records[offset:offset + 70]
        response = call_gemini_with_retry(
            build_deliverable_category_prompt(batch),
            f"Deliverables category assignment {offset // 70 + 1}", max_retries,
            model_key='fast', silent=True, status_queue=status_queue,
        )
        valid_ids = {r['id'] for r in batch}
        if response:
            for line in response.splitlines():
                if '::' not in line:
                    continue
                record_id, category = [x.strip() for x in line.split('::', 1)]
                if record_id in valid_ids and category in DELIVERABLE_CATEGORIES:
                    mapping[record_id] = category
    return {r['id']: mapping.get(r['id'], _fallback_deliverable_category(r)) for r in records}


def _format_deliverable_register(records, category_by_id):
    grouped = {category: [] for category in DELIVERABLE_CATEGORIES}
    for record in records:
        grouped[category_by_id[record['id']]].append(record)
    output = ['# DELIVERABLES']
    for category, children in grouped.items():
        if not children:
            continue
        output.extend(['', f'## {category}'])
        for r in children:
            output.append(
                f"- {r['name']} :: {r['description']} :: {r['deadline']} :: {r['page']} :: "
                f"{r['evidence']} :: {r['document']} :: {r['section']} :: {r['requirement_type']}"
            )
    return '\n'.join(output)


def extract_deliverables_exhaustively(document_text, max_retries=5, status_queue=None, amendment_filenames=None):
    """Exhaustively extract child records, then locally preserve and group them.

    Calls run sequentially on purpose. The shared request gate also protects the
    other agents, so a large RFP completes reliably instead of repeatedly colliding
    with Gemini's quota.
    """
    chunks = split_rfp_for_deliverables(document_text)
    if not chunks:
        return None
    candidates = []
    for index, chunk in enumerate(chunks, 1):
        result = call_gemini_with_retry(
            build_deliverables_page_prompt(chunk, index, len(chunks)),
            f"Deliverables source scan {index}/{len(chunks)}", max_retries,
            model_key='lite', silent=True, status_queue=status_queue,
        )
        if result:
            candidates.append(result)
    records = _parse_deliverable_candidates(candidates)
    if not records:
        return '# DELIVERABLES\n\n## No bidder or contractor deliverables identified in the extracted source text.'
    records = _merge_duplicate_deliverables(records)
    records = _apply_amendment_precedence(records, amendment_filenames)
    records = _sync_amendment_deadlines(records, amendment_filenames)
    for index, record in enumerate(records, 1):
        record['id'] = f'D{index:04d}'
    category_by_id = _assign_deliverable_categories(records, max_retries, status_queue)
    return _format_deliverable_register(records, category_by_id)

# =====================================================
# PROMPT 2: EVALUATION CRITERIA ONLY
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

⚠️ COMPLETENESS OVERRIDE — READ CAREFULLY:
Your default instinct may be to summarize evaluation criteria into a
short, high-level list to keep the answer brief and token-efficient. For
THIS task, that instinct is WRONG and must be overridden. There is no
reward for brevity here — a shortened list is a FAILED extraction even
if every item on it is accurate. Real RFP evaluation sections typically
break scoring down into MANY specific sub-criteria (e.g. not just
"Technical Approach" but its individual scored components: methodology,
staffing plan, past performance, technical narrative quality, compliance
with specifications, etc., each often with its own point value). Scan
the ENTIRE document set — including any scoring matrices, point-value
tables, weighting schedules, "Basis of Award" sections, appendices, and
attachments — not just a section literally titled "Evaluation Criteria".
If your first pass looks short relative to how detailed the source RFP
is, that is a signal you stopped too early — re-scan before finalizing.

Output EXACTLY in this format, and output NOTHING else — no preamble, no closing remarks.
Use the labels below exactly. This structure is deliberately detailed so the
reader can see both the scoring logic and the evidence behind it.

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

Do NOT truncate your answer early to save length/tokens. If you have not
yet covered every page and every attachment/appendix of every document
for evaluation-related content, you are not done.

RFP DOCUMENTS:
{document_text}
"""


# =====================================================
# PROMPT 3: COMPLIANCE CHECKLIST ONLY
# =====================================================

def build_checklist_prompt(document_text):
    return f"""
You are an SPS Proposal Capture Manager.

Analyze ALL uploaded RFP documents (each marked with [START OF DOCUMENT: filename.pdf] ... [END OF DOCUMENT: filename.pdf])
STRICTLY against the fixed checklist below. Do NOT use any generic knowledge — only what is written inside the RFP text.

Every checklist item has hidden sub-criteria (listed below, for your own
internal checking only — do NOT print these sub-criteria or any decision
rules in your output, only print the final Item / Status / Decision / Explanation /
Reference from RFP / Page No / Document Name / Section Name table exactly in
the format shown further down).

STRICT RULES:
1. Use ONLY information present in RFP.
2. Never guess. Never hallucinate.
3. If information is missing write: "Not specified in RFP".
4. Keep each Explanation concise — but never skip or merge checklist items
   to save length. Every fixed item below must get its own row.
4b. Every Explanation must end with a short, natural cause-and-effect
    clause that names the resulting Decision, so the reader never has to
    guess WHY that Decision was reached. Do not just repeat "GO"/"NO-GO"/
    "MAYBE" as a bare word — tie it back to the specific fact just stated.
    Example: "Payments are made no later than 30 days after receipt of a
    proper invoice, which meets the NET30 standard and leads to a GO
    decision." Another example: "The RFP requires $10M in coverage,
    exceeding the $5M threshold, which drives a NO-GO decision." Keep this
    clause short (roughly 8-15 words) and vary the phrasing naturally
    instead of pasting an identical template sentence on every row.
5. Remove duplicate information.
6. Check EACH item against its sub-criteria (below) before deciding status — but only output the final Item/Status/Decision/Explanation table, nothing else about the sub-criteria.
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
     from, taken from the "[START OF DOCUMENT: filename.pdf]" marker
     surrounding that reference. If multiple documents were uploaded, this
     tells the reader WHICH one this specific item's evidence came from. If
     the item's Status is ❌ NOT FOUND, write "N/A".
   - Section Name: the short section number/heading this reference falls
     under (e.g. "Section 4.1", "Attachment A"), same style as used in the
     Deliverables section. If no clear section heading exists, write
     "General Requirements". If the item's Status is ❌ NOT FOUND, write
     "N/A".
8. Every row must also carry a per-item Decision of GO, NO-GO, or MAYBE, decided using these exact rules (apply silently, do not print the rules themselves):
   - Payment Terms: if RFP states NET30 → Status ✅ FOUND, Decision GO. If more than NET30 (NET45/60 etc) → Status ⚠️ ACTION REQUIRED, Decision MAYBE (escalate to accounting). If not mentioned → Status ❌ NOT FOUND, Decision NO-GO.
   - Financial Stability Requirements: this checklist item is conditional — it only matters if the RFP actually imposes a requirement. Check for THREE distinct cases:
     (a) CLEAR REQUIREMENT: the RFP explicitly requires financial statements or proof of financial stability, with a clear submission requirement → Status ✅ FOUND, Decision GO (note in the Explanation that unaudited financial statements should be treated as acceptable proof, unless the RFP explicitly demands audited statements; also add a short note that SPS's finance team must separately confirm internally that SPS can actually produce the specific financial documentation requested, since the AI has no access to SPS's own financial records).
     (b) CONDITIONAL / CONTINGENT OBLIGATION: the RFP contains general "ability to perform" investigation language AND also places an obligation on the bidder to furnish information if/when requested — for example wording like "the buyer may investigate the bidder's ability to perform" COMBINED WITH "the Contractor shall furnish/provide all such information and data for this purpose as may be requested". This combination (a discretionary investigation right plus a standing obligation to comply with such a request) means financial information COULD be demanded later even though nothing is due with the initial proposal. Treat this as → Status ⚠️ ACTION REQUIRED, Decision MAYBE — flag it as a contingent obligation to note, not a hard requirement, but also not a non-issue; also add a short note that SPS's finance team should be ready to produce such information internally if requested later.
     (c) TRULY SILENT: the RFP does not mention financial stability, proof of ability to perform, or any related investigation/furnish-information clause at all → Status ❌ NOT FOUND, Decision GO (there is no obligation on the bidder of any kind, so this is not a risk — do NOT mark this NO-GO or MAYBE).
     Do NOT default to case (c) just because no specific document name (e.g. "financial statements") is mentioned — check carefully whether a general investigate-and-furnish-information clause exists anywhere in the RFP's instructions/terms sections, since that alone is enough to qualify as case (b), not case (c). Apply this same three-way distinction to every RFP analyzed, not just a specific one.
   - Insurance Requirements: if RFP states exactly $5M coverage → Status ✅ FOUND, Decision GO. If RFP requires MORE than $5M → Status ⚠️ ACTION REQUIRED, Decision NO-GO (this is a hard limit, do not mark it GO or MAYBE). If insurance is not mentioned anywhere in the RFP → Status ❌ NOT FOUND, Decision MAYBE (no specific coverage amount is defined, so this needs to be confirmed with the client rather than treated as an automatic NO-GO). IMPORTANT — in every case for this item, the Explanation must end with a short note flagging that this analysis only confirms what the RFP requires; SPS's finance/insurance team must separately confirm internally that SPS's own current coverage actually meets or can be upgraded to meet the stated amount, since the AI has no access to SPS's actual insurance policy details.
   - Profitability Analysis: this is always an internal exercise the bidder must perform themselves (comparing expected revenue vs projected costs) — the RFP itself will essentially never state a completed profitability analysis. If the RFP provides enough figures (contract value, budget, expected revenue) for a profitability analysis to be readily performed → Status ✅ FOUND, Decision GO. If the RFP provides only partial figures → Status ⚠️ ACTION REQUIRED, Decision MAYBE. If the RFP provides no relevant financial figures at all (the normal case for most RFPs) → Status ❌ NOT FOUND, Decision MAYBE (this is a to-do flag for the bidder to complete their own analysis — it is NOT a NO-GO, since the RFP was never responsible for providing this).
   - Capability: this checklist item covers Qualified Personnel and Technical Knowhow. Its Status/Decision must be based ONLY on what the RFP itself asks for (whether it requires personnel qualifications, resumes, staff bios, or technical-knowhow disclosures) — NOT on whether SPS actually has such staff, since the AI has no access to SPS's internal HR/staffing records.
     - If the RFP clearly requires personnel/skills disclosure (e.g. resumes, roles, qualifications, key staff bios) → Status ✅ FOUND, Decision GO.
     - If the RFP mentions this vaguely or ambiguously → Status ⚠️ ACTION REQUIRED, Decision MAYBE.
     - If the RFP does not mention personnel/capability requirements at all → Status ❌ NOT FOUND, Decision GO (there is no personnel/skills-disclosure obligation on the bidder at all, so this is not a risk — do NOT mark this NO-GO or MAYBE, same logic as the Financial Stability "truly silent" case above).
     Whenever the Decision is GO for this item, the Explanation must end with a short note: SPS must separately confirm internally that it has personnel matching the described qualifications, since the AI cannot verify SPS's actual staffing.
   - Quantum of Input Required: this checklist item covers four sub-parts — Expected Revenue Generation, Period of Implementation, Insurance Coverage, and Compliance of Law. Expected Revenue Generation is ALWAYS the bidder's own internal estimate (same as in Profitability Analysis) — the RFP will essentially never state SPS's expected revenue, so its absence must never pull the Status to NOT FOUND or the Decision to NO-GO. Base the Status/Decision on ONLY the three RFP-derivable sub-parts (Period of Implementation, Insurance Coverage, Compliance of Law):
     - If all three RFP-derivable sub-parts are clearly stated → Status ✅ FOUND, Decision GO.
     - If some are missing or ambiguous → Status ⚠️ ACTION REQUIRED, Decision MAYBE.
     - If none of the three are addressed at all → Status ❌ NOT FOUND, Decision NO-GO.
     The Explanation must always end with a short note: Expected Revenue Generation is SPS's own internal projection for this project and is not something the RFP is expected to provide.
   - Scope Alignment: Status and Decision are SEPARATE for this item. Status is ONLY about whether the RFP describes its scope of work / statement of needs at all — mark Status ✅ FOUND whenever the RFP defines what it is seeking (this is true for almost every RFP). Mark Status ❌ NOT FOUND only if the RFP genuinely contains no scope/statement-of-needs description whatsoever. Decision is about whether that described scope matches SPS's own portfolio (Identity and Access Management, cybersecurity solutions, identity governance, access control): Decision GO if the scope is genuinely about IAM/cybersecurity/identity/access-control; Decision NO-GO if the scope is about something unrelated (e.g. website search, personalization, general software development, marketing, construction, unrelated AI/ML products) even though the scope itself is clearly described (Status must still stay FOUND, never NOT FOUND, in this case); Decision MAYBE only if the scope is partially related or ambiguous. Do not let a NO-GO decision pull the Status down to NOT FOUND — a clearly-out-of-scope RFP is Status FOUND + Decision NO-GO, not Status NOT FOUND.
   - Bid Bond: if RFP requires a bid bond or bond percentage → Status ✅ FOUND, Decision GO (this is a normal, satisfiable requirement, not a blocker). If mentioned vaguely/ambiguously → Status ⚠️ ACTION REQUIRED, Decision MAYBE. If the RFP does not mention a bid bond at all → Status ❌ NOT FOUND, Decision GO (no bond is required of the bidder, so this is not a risk — do NOT mark this NO-GO).
   - E-Verify: if RFP requires use of the E-Verify system → Status ✅ FOUND, Decision GO. If mentioned vaguely/ambiguously → Status ⚠️ ACTION REQUIRED, Decision MAYBE. If the RFP does not mention E-Verify at all → Status ❌ NOT FOUND, Decision GO (there is no E-Verify obligation on the bidder, so this is not a risk — do NOT mark this NO-GO).
   - All other items: Status ✅ FOUND → Decision GO. Status ⚠️ ACTION REQUIRED (partially/ambiguously mentioned) → Decision MAYBE. Status ❌ NOT FOUND (absent) → Decision NO-GO.
9. Do not invent or fabricate any Reference from RFP text — it must be real wording taken from (or tightly paraphrased from) the RFP documents provided.

Internal sub-criteria reference (for your checking only, never print):
- Payment Terms: payment schedule, milestones, retainage, late-payment penalties.
- Financial Stability Requirements: financial statements / proof of financial stability required. This is a THREE-WAY conditional check, not a plain found/not-found risk item — see the special rule above (clear requirement = GO, general "may investigate + shall furnish info as requested" clause = MAYBE, truly no mention at all = GO). Unaudited financial statements should be treated as sufficient proof unless the RFP explicitly demands audited statements.
- Insurance Requirements: required coverage amount. See special rule above for the "not mentioned" case (MAYBE, not NO-GO).
- Profitability Analysis: expected revenue vs projected cost / budget / contract value. This is always the bidder's own internal exercise — see special rule above (NOT FOUND = MAYBE, never NO-GO).
- Bid Bond: bid bond or bond percentage requirement. See special rule above (NOT FOUND = GO, not NO-GO — no bond required is not a risk).
- Eligibility Criteria: relevant experience, registration requirement, prior-year financial statement.
- Capability: qualified personnel, technical know-how. Status/Decision reflect ONLY what the RFP asks for regarding personnel/skills disclosure, never whether SPS actually has that staff — see special rule above (NOT FOUND = GO, not NO-GO — no disclosure requirement is not a risk). GO decisions always carry an internal-confirmation note in the Explanation.
- Quantum of Input: expected revenue generation, implementation period, insurance coverage, compliance of law. Expected Revenue Generation is always the bidder's own internal estimate and must never drag Status/Decision down — see special rule above. Base Status/Decision only on implementation period, insurance coverage, and compliance of law.
- Data Protection: data protection laws / regulatory compliance.
- State Registration: requirement to register in the state of execution.
- E-Verify: requirement to use E-Verify system. See special rule above (NOT FOUND = GO, not NO-GO — no E-Verify obligation is not a risk).
- Contractual Obligations: termination clauses, liability limits, dispute resolution.
- Required Forms: certifications, compliance forms, declarations, insurance info form (Tax ID, Owner Name, % ownership), Small Business (MD), MBE, Workers Comp, Business with Iran declaration.
- Submission Deadlines: specific submission date/time for forms/documents.
- Document Compliance: formatting/submission requirements (page limits, font, file format, portal rules).
- Signatory Authority: who must sign (authorized representative/officer).
- Required Documents: cross-check all required documents/forms are listed.
- Responsible Person: RFP Owner/Lead or point of contact identified.
- Meeting with Ops: pre-bid meeting / site visit / conference call requirement.
- Vendor Registration: info needed to complete registration, who is responsible.
- Scope Alignment: SPS's actual service portfolio is Identity and Access Management (IAM), cybersecurity solutions, identity governance, access control, and related security services.
  - STATUS (✅ FOUND / ❌ NOT FOUND) reflects ONLY whether the RFP clearly defines/describes its scope of work or statement of needs — regardless of what that scope actually is. Mark ✅ FOUND whenever the RFP explains what it wants done. Only mark ❌ NOT FOUND if the RFP truly has no scope/statement-of-needs description at all.
  - DECISION (GO / NO-GO / MAYBE) reflects whether that described scope ALIGNS with SPS's portfolio above:
    - Decision GO only if the RFP's scope is genuinely about IAM, cybersecurity, identity governance, access control, or a closely related security discipline.
    - Decision NO-GO if the RFP's scope is about something else entirely (e.g. website search, personalization engines, general software development, marketing, construction, unrelated AI/ML products, etc.) — even though that scope is clearly and fully described in the RFP. Status still stays FOUND in this case; only the Decision becomes NO-GO.
    - Decision MAYBE only if the scope is partially related or ambiguous (e.g. touches on data security or access control as one component among otherwise unrelated work).
  In the Explanation column, never claim "aligns with SPS offerings" unless the scope actually involves IAM/cybersecurity/identity/access-control work — state plainly what the RFP's scope is and whether it overlaps with SPS's services.
- Technical Requirements: do specs match SPS capabilities.
- Industry Standards: reference to standards/best practices (NIST, ISO, SOC2 etc).
- Security Requirements: data protection, encryption, access control.
- Integration Needs: requirement to integrate with other systems.

Output EXACTLY in this format, and output NOTHING else — no preamble, no closing remarks:

# COMPLIANCE CHECKLIST

## FINANCE TEAM
| Item | Status | Decision | Explanation | Reference from RFP | Page No | Document Name | Section Name |
|------|--------|----------|-------------|--------------------|---------|---------------|--------------|
| Payment Terms (NET30 rule) | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Financial Stability | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Insurance Requirements ($5M rule) | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Profitability Analysis | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Bid Bond | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |

## LEGAL TEAM
| Item | Status | Decision | Explanation | Reference from RFP | Page No | Document Name | Section Name |
|------|--------|----------|-------------|--------------------|---------|---------------|--------------|
| Eligibility Criteria | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Capability | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Quantum of Input | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Data Protection | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| State Registration | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| E-Verify | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Contractual Obligations | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |

## OPERATIONS TEAM
| Item | Status | Decision | Explanation | Reference from RFP | Page No | Document Name | Section Name |
|------|--------|----------|-------------|--------------------|---------|---------------|--------------|
| Required Forms | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Submission Deadlines | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Document Compliance | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Signatory Authority | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Required Documents | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Responsible Person | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Meeting with Ops | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Vendor Registration | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |

## TECHNICAL TEAM
| Item | Status | Decision | Explanation | Reference from RFP | Page No | Document Name | Section Name |
|------|--------|----------|-------------|--------------------|---------|---------------|--------------|
| Scope Alignment | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Technical Requirements | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Industry Standards | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Security Requirements | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |
| Integration Needs | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] | [Short quote/paraphrase from RFP, or "Not specified in RFP"] | [Page number, e.g. "Page 4", or "N/A"] | [Document filename, e.g. "RFP_Solicitation_123.pdf"] | [Section heading/number, e.g. "Section 4.1", or "General Requirements"] |

RFP DOCUMENTS:
{document_text}
"""


# =====================================================
# PROMPT 4: QUALIFICATION DECISION NARRATIVE ONLY
# (scores/decision are already computed in Python — this call just
#  explains them; sync_justification_score() will still correct any
#  mismatched numbers the model happens to quote)
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
explicitly name WHICH item(s) caused it (e.g. "Insurance requirement of
$10M exceeds the $5M threshold" or "Payment terms are NET60, exceeding
NET30") so the reason is obvious, not generic. Cover: why this decision
was made, key strengths identified, key risks or gaps (name the specific
flagged item(s)), and what needs to happen next.]
"""


# =====================================================
# PROMPT: AMENDMENT CHANGE SUMMARY
# =====================================================
# Used only when re-analyzing an RFP after amendment documents are
# uploaded. The new report is always regenerated from the FULL document
# set (original + amendments) so the analysis itself never drifts or
# compounds errors from an old summary — but we still show the previous
# report to Gemini here, purely so it can point out what moved.

def build_change_summary_prompt(previous_report, new_report, amendment_filenames):
    filenames_list = ", ".join(amendment_filenames) if amendment_filenames else "the newly uploaded amendment document(s)"
    return f"""
You are an SPS Proposal Capture Manager. An RFP was already analyzed once.
New amendment document(s) have now been uploaded: {filenames_list}.
The FULL analysis (Deliverables, Evaluation Criteria, Compliance Checklist,
Scoring, Decision) has already been fully redone from scratch using the
original RFP documents PLUS these amendment documents. That redone result
is the new source of truth — do not change it, only describe how it differs
from the previous version.

PREVIOUS REPORT (before amendment):
{previous_report}

NEW REPORT (after amendment):
{new_report}

STRICT RULES:
1. Compare the two reports and identify concrete differences only —
   added/removed/changed deliverables, evaluation criteria, checklist items,
   scores, or the final decision. Ignore purely cosmetic/formatting differences.
2. Do NOT guess a reason for a change unless it's evident from the text.
3. If a section is effectively unchanged, say so briefly — do not invent changes.
4. Be specific: name the deliverable/item/score that changed and its old vs new value.

Output EXACTLY in this format, and output NOTHING else — no preamble:

# ADDENDUM CHANGE SUMMARY

## WHAT CHANGED
- [Bullet list of concrete changes, one per line, each naming the specific
  item and old → new value. If nothing changed in a category, omit it.]

## OVERALL IMPACT
[1-2 sentence plain-language summary of how significant this amendment is
overall, e.g. "This amendment adds two new deliverables and shifts the
Finance score from MAYBE to GO due to relaxed payment terms."]
"""


# =====================================================
# VERIFICATION AGENT — final QA pass on the assembled report
# =====================================================
# Runs AFTER the other 4 agents have produced the full report. Its only
# job is to re-read the ORIGINAL RFP text side-by-side with the report
# those agents produced, and flag anything that looks hallucinated,
# missing, or mis-scored — a second, independent pair of "eyes" using
# the stronger reasoning model, dedicated purely to accuracy checking
# rather than content generation.

def build_verification_prompt(document_text, combined_report):
    today_str = datetime.now(timezone.utc).strftime('%B %d, %Y')
    return f"""
You are an independent QA / Verification Agent for an RFP Proposal Capture
System. You did NOT write the report below — a separate agent did. Your
ONLY job is to audit it against the source RFP text for accuracy.

Today's actual real-world date is {today_str}. Use this when judging any
claim in the report about a deadline having "already passed" or being
"overdue" — check the deadline date the report cites against this actual
date yourself; do not assume such a claim is ungrounded just because the
RFP text itself doesn't state today's date (RFP source documents never do).

You will be given:
1. The ORIGINAL RFP DOCUMENT TEXT (ground truth).
2. The REPORT that another AI agent produced from it.

Check the report against the source text for:
- Hallucinations: any deliverable, requirement, date, or figure in the
  report that is NOT actually present in the RFP text.
- Omissions: any clearly-stated, important requirement or deadline in the
  RFP that is missing from the report.
- Scoring/logic issues: does the Final Decision (GO / MAYBE / NO-GO)
  reasonably follow from the Overall Score and the checklist entries shown?
- Internal contradictions between sections of the report itself.

IMPORTANT — a known, INTENTIONAL rule of this system (do NOT flag this as
an error): if the RFP's primary bid submission deadline (the shared closing
date/time on the core Mandatory submission items — bid PDF, transmittal
letter, affidavits, bid price form, etc.) falls before today's actual date
above, the Final Decision is deliberately forced to NO-GO regardless of how
high the Overall Score is, because the bid window is closed and the
opportunity can no longer be submitted. The Justification will contain an
"⚠️ OVERRIDE" note explaining this. This is correct, expected behavior, NOT
a scoring/logic contradiction — only flag it as an issue if you can show the
cited deadline date is factually wrong (i.e. it does NOT actually appear in
the source RFP text, or it is NOT actually before today's date above).

STRICT RULES:
1. Do NOT rewrite or regenerate the report. You are auditing it, not
   redoing it.
2. Only flag something if you can point to a concrete mismatch. Do not
   invent issues to seem thorough.
3. Be concise — this is a QA summary, not a new report.
4. For every issue you flag, you MUST also provide the exact surgical fix:
   the precise snippet of text as it appears VERBATIM in the report right
   now (Original Text), and exactly what it should say instead (Corrected
   Text), grounded strictly in the source RFP text. Keep both snippets as
   SHORT as possible while still being unique enough in the report to find
   and replace unambiguously (ideally under ~25 words) — do not include
   surrounding text that doesn't need to change. If an issue is an omission
   (something missing entirely, nothing wrong to replace), leave Original
   Text and Corrected Text both as "N/A" — omissions can't be one-click
   fixed, they need a re-run.

Output EXACTLY in this format, nothing else:

# VERIFICATION SUMMARY

Confidence: [High / Medium / Low]

## Issues Found
If there are no issues, write exactly:
- No material issues found — report is well-grounded in the source RFP.

Otherwise, output ONE block per issue, back to back, in exactly this form:
### ISSUE
Type: [Hallucination / Omission / Internal Contradiction / Scoring or Logic Issue]
Where: [Short section/row reference, e.g. "Deliverables — Attachment C row"]
Problem: [One concise sentence describing what's wrong]
Original Text: [Exact verbatim snippet from the report, or N/A if omission]
Corrected Text: [Exact replacement snippet, or N/A if omission]
### END ISSUE

## Notes
[Optional 1-2 sentence caveat, e.g. sections that were hard to verify due
to unclear/scanned source text. Omit this line entirely if not needed.]

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
# ORCHESTRATOR — replaces the old single mega-call
# =====================================================

def _parse_verification_issues(verification_notes: str):
    """Parse the Verification Agent's output into structured issues.

    Supports the new structured "### ISSUE ... ### END ISSUE" block format
    (which carries an exact Original/Corrected text pair for one-click
    fixing) and falls back to the older plain "- issue text" bullet format
    for any verification_notes saved before this format existed — those
    are still displayed, just without a Fix button.
    """
    confidence_match = re.search(r"Confidence:\s*(High|Medium|Low)", verification_notes, re.IGNORECASE)
    confidence = confidence_match.group(1).title() if confidence_match else "Verified"

    issues_match = re.search(r"##\s*Issues Found\s*\n(.*?)(?=\n##\s|\Z)", verification_notes, re.IGNORECASE | re.DOTALL)
    issues_text = issues_match.group(1).strip() if issues_match else ""

    blocks = re.findall(r"###\s*ISSUE\s*\n(.*?)(?:###\s*END ISSUE|\Z)", issues_text, re.IGNORECASE | re.DOTALL)
    issues = []
    if blocks:
        for block in blocks:
            def _field(label):
                m = re.search(rf"{label}:\s*(.*?)(?=\n[A-Z][a-zA-Z ]*:|\Z)", block, re.IGNORECASE | re.DOTALL)
                return m.group(1).strip() if m else ""
            problem = _field("Problem")
            where = _field("Where")
            issue_type = _field("Type")
            original = _field("Original Text")
            corrected = _field("Corrected Text")
            display = f"{where + ': ' if where else ''}{problem}" if problem else block.strip()
            fixable = bool(
                original and corrected
                and original.strip().upper() != "N/A"
                and corrected.strip().upper() != "N/A"
                and original.strip() != corrected.strip()
            )
            issues.append({
                "display": display, "type": issue_type, "where": where,
                "problem": problem, "original": original, "corrected": corrected,
                "fixable": fixable,
            })
    else:
        for line in issues_text.splitlines():
            stripped = line.lstrip("-• ").strip()
            if stripped:
                issues.append({
                    "display": stripped, "type": "", "where": "", "problem": stripped,
                    "original": "", "corrected": "", "fixable": False,
                })

    no_issues = (not issues or any("no material issues found" in i["display"].lower() for i in issues))
    return confidence, issues, no_issues


def _apply_verification_fix(raw_report: str, verification_notes: str, issue: dict):
    """Apply exactly one verified fix with a plain-text find/replace — no AI
    call, no re-running the pipeline. Also re-runs the local (non-AI) score
    consistency pass and strips the fixed issue's block out of the stored
    verification notes so it stops showing as outstanding.

    Returns (new_raw_report, new_verification_notes, ok, message).
    """
    original, corrected = issue["original"].strip(), issue["corrected"].strip()
    count = raw_report.count(original)
    if count == 0:
        return raw_report, verification_notes, False, (
            "Couldn't find that exact text in the report to patch automatically "
            "— it may have shifted. Please re-run a full analysis instead."
        )
    if count > 1:
        return raw_report, verification_notes, False, (
            "That text appears more than once in the report, so an automatic "
            "patch isn't safe here — please fix this one manually."
        )

    new_raw_report = raw_report.replace(original, corrected, 1)
    new_raw_report = apply_score_fix(new_raw_report)

    # Remove this specific issue's block from the stored verification notes.
    block_pattern = re.compile(
        r"###\s*ISSUE\s*\n(?:(?!###\s*ISSUE).)*?"
        + re.escape(issue["display"][:60])
        + r"(?:(?!###\s*ISSUE).)*?###\s*END ISSUE\s*\n?",
        re.IGNORECASE | re.DOTALL,
    )
    new_verification_notes = block_pattern.sub("", verification_notes, count=1)
    if new_verification_notes == verification_notes:
        # Fallback: match purely on the exact original snippet if the
        # short-display heuristic above didn't line up.
        block_pattern = re.compile(
            r"###\s*ISSUE\s*\n(?:(?!###\s*ISSUE).)*?"
            + re.escape(original[:60])
            + r"(?:(?!###\s*ISSUE).)*?###\s*END ISSUE\s*\n?",
            re.IGNORECASE | re.DOTALL,
        )
        new_verification_notes = block_pattern.sub("", verification_notes, count=1)

    remaining_confidence, remaining_issues, remaining_none = _parse_verification_issues(new_verification_notes)
    if remaining_none:
        new_verification_notes = (
            f"# VERIFICATION SUMMARY\n\nConfidence: {remaining_confidence}\n\n"
            "## Issues Found\n- No material issues found — report is well-grounded in the source RFP.\n"
        )

    return new_raw_report, new_verification_notes, True, "✅ Fixed — report updated."


def analyze_rfp(document_text, max_retries=5, amendment_filenames=None):
    status_placeholder = st.empty()
    progress_placeholder = st.empty()
    progress_bar = progress_placeholder.progress(0)

    # (icon, agent name, model tier, short description of what it's doing)
    AGENTS_META = [
        ("📄", "Deliverables Agent", "fast", "Extracts every requirement & submission item"),
        ("⚖️", "Evaluation Agent", "fast", "Summarizes scoring & evaluation criteria"),
        ("✅", "Checklist Agent", "fast", "Builds department-wise compliance checklist"),
        ("🎯", "Decision Agent", "pro", "Weighs scores into a GO / NO-GO call"),
        ("🔍", "Verification Agent", "pro", "Independently audits the report for accuracy"),
    ]

    def update_status(statuses, label):
        """statuses: list of 5 strings ('pending' | 'active' | 'done'),
        one per agent in AGENTS_META order — lets several agents show as
        'active' at once when they're running in parallel."""
        # A clear, product-facing capability label is shown instead of a
        # technical model name, keeping the progress view focused on the work.
        model_badges = {
            "fast": ("✦ AI-Powered Analysis", "badge-fast"),
            "pro": ("✦ AI-Powered Analysis", "badge-fast"),
        }
        status_pills = {
            "pending": "Pending",
            "active": "● Running",
            "done": "✓ Done",
        }
        cards_html = ""
        for (icon, name, mkey, desc), status_cls in zip(AGENTS_META, statuses):
            badge_text, badge_cls = model_badges[mkey]
            cards_html += (
                f'<div class="agent-card {status_cls}">'
                f'<div class="agent-card-top">'
                f'<span class="agent-icon">{icon}</span>'
                f'<span class="agent-status-pill {status_cls}">{status_pills[status_cls]}</span>'
                f'</div>'
                f'<div class="agent-name">{name}</div>'
                f'<div class="agent-desc">{desc}</div>'
                f'<span class="agent-model-badge {badge_cls}">{badge_text}</span>'
                f'</div>'
            )
        status_placeholder.markdown(
            '<div class="processing-status">'
            '<h3>🧠 <span class="highlight">AI Agent Pipeline</span> — <span class="live-analysis">● Live Analysis in Progress</span></h3>'
            f'<p style="color:#c3c8e6; margin: 0.4rem 0 0.2rem;">{label}</p>'
            f'<div class="agent-pipeline">{cards_html}</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    P, A, D = "pending", "active", "done"

    try:
        # ---- Steps 1-3: Deliverables, Evaluation, Checklist — run in PARALLEL ----
        # None of these three depend on each other, only on the raw document
        # text, so there's no reason to make them wait in line.
        update_status([A, A, A, P, P], "⏳ Running Deliverables, Evaluation & Checklist agents in parallel...")
        progress_bar.progress(0.15)

        # Worker threads place retry notices here. The main Streamlit thread
        # reads them and shows them in the live pipeline card.
        retry_messages = queue.Queue()
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_map = {
                executor.submit(
                    extract_deliverables_exhaustively, document_text, max_retries, retry_messages, amendment_filenames,
                ): "deliverables",
                executor.submit(
                    call_gemini_with_retry, build_evaluation_prompt(document_text),
                    "Evaluation Criteria", max_retries, "fast", True, retry_messages,
                ): "evaluation",
                executor.submit(
                    call_gemini_with_retry, build_checklist_prompt(document_text),
                    "Compliance Checklist", max_retries, "fast", True, retry_messages,
                ): "checklist",
            }
            parallel_results = {}
            pending = set(future_map)
            while pending:
                # Refresh the UI while requests wait for the API cooldown.
                while not retry_messages.empty():
                    update_status([A, A, A, P, P], retry_messages.get_nowait())
                done, pending = concurrent.futures.wait(
                    pending, timeout=0.25,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                for future in done:
                    key = future_map[future]
                    parallel_results[key] = future.result()
            while not retry_messages.empty():
                update_status([A, A, A, P, P], retry_messages.get_nowait())

        deliverables_text = parallel_results["deliverables"]
        evaluation_text = parallel_results["evaluation"]
        checklist_text = parallel_results["checklist"]

        if not deliverables_text:
            raise Exception("Deliverables extraction failed")

        # Deliverables now come from page-bounded extraction plus a guarded
        # parent-child merge, so individual appendix/form rows cannot vanish.

        if not evaluation_text:
            raise Exception("Evaluation criteria extraction failed")
        if not checklist_text:
            raise Exception("Compliance checklist failed")

        update_status([D, D, D, P, P], "⏳ Deliverables, Evaluation & Checklist complete...")
        progress_bar.progress(0.55)

        # ---- Compute scores in Python BEFORE asking for the decision narrative ----
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

        # ---- Step 4: Decision narrative (needs the checklist result, so this stays sequential) ----
        update_status([D, D, D, A, P], "⏳ Generating qualification decision...")
        progress_bar.progress(0.75)
        decision_text = call_gemini_with_retry(
            build_decision_prompt(checklist_text, overall_pct, correct_decision, deadline_overdue),
            "Qualification Decision",
            max_retries,
            model_key="pro",
        )
        if not decision_text:
            raise Exception("Decision generation failed")

        # ---- Assemble combined report (same structure format_report expects) ----
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

        # ---- Step 5: Verification agent — needs the final report, so it runs last ----
        update_status([D, D, D, D, A], "⏳ Running independent verification check...")
        progress_bar.progress(0.95)
        verification_notes = call_gemini_with_retry(
            build_verification_prompt(document_text, fixed_text),
            "Verification",
            max_retries,
            model_key="pro",
        )
        if not verification_notes:
            # Verification failing shouldn't block the whole analysis —
            # the report itself is still valid, just unverified.
            verification_notes = (
                "# VERIFICATION SUMMARY\n\nConfidence: Unknown\n\n"
                "## Issues Found\n- Verification agent could not be reached; "
                "report was not independently checked.\n"
            )

        update_status([D, D, D, D, D], "✅ All agents complete.")
        progress_bar.progress(1.0)
        time.sleep(0.3)
        status_placeholder.empty()
        progress_placeholder.empty()

        return fixed_text, verification_notes

    except Exception as e:
        status_placeholder.empty()
        progress_placeholder.empty()
        st.error(f"❌ Error: {e}")
        return "Analysis failed due to an error. Please try again.", None


# =====================================================
# AMENDMENT ORCHESTRATOR
# =====================================================
# Design decision (see chat): when amendment documents arrive for an RFP
# that was already analyzed, we do NOT ask Gemini to patch the old report.
# Old AI output is a summary, not a source document — feeding it back in as
# the basis for a new analysis lets errors and omissions compound with every
# amendment. Instead:
#   1. The ORIGINAL document text is combined with the NEW amendment text
#      and run through the exact same 4-step pipeline as a fresh analysis
#      (deliverables/evaluation/checklist/decision) — so the new report is
#      always grounded directly in the actual RFP + amendment PDFs.
#   2. The previous report is then shown to Gemini ONLY as a reference point
#      to produce an explicit, human-readable "what changed" summary, so the
#      team always has traceability into how much the amendment moved things.

def build_amendment_document_text(original_document_text, amendment_document_text, amendment_filenames):
    names = ", ".join(amendment_filenames) if amendment_filenames else "amendment document(s)"
    return f"""{original_document_text}

{"=" * 60}
[AMENDMENT UPDATE — the following document(s) were uploaded AFTER the
original RFP and take precedence over the original wherever they conflict
with it: {names}]
{"=" * 60}

{amendment_document_text}
"""


def analyze_rfp_amendment(original_document_text, amendment_document_text, amendment_filenames, previous_report, max_retries=5):
    """Re-analyzes an RFP after amendment documents are uploaded.

    Returns (new_report, change_summary, verification_notes) — new_report has
    the exact same structure as analyze_rfp()'s output (so all existing
    rendering/PDF/JSON code works unchanged), change_summary is a short
    standalone report describing what moved versus the previous version, and
    verification_notes is the QA agent's audit of the new report.
    """
    combined_document_text = build_amendment_document_text(
        original_document_text, amendment_document_text, amendment_filenames
    )

    # Steps 1-5: identical pipeline to a fresh analysis (including the
    # verification agent), just with the amendment text folded into the
    # document set. amendment_filenames is threaded through so the
    # deliverables extraction step knows which document(s) are the addendum
    # and can make its updated values win over stale ones from the original
    # RFP instead of leaving both as contradictory rows (see
    # _apply_amendment_precedence).
    new_report, verification_notes = analyze_rfp(
        combined_document_text, max_retries=max_retries, amendment_filenames=amendment_filenames,
    )

    if not new_report or "Analysis failed" in new_report:
        return new_report, None, verification_notes

    # Step 6: explicit diff against the previous version.
    with st.spinner("📝 Summarizing what changed vs. the previous version..."):
        change_summary = call_gemini_with_retry(
            build_change_summary_prompt(previous_report, new_report, amendment_filenames),
            "Amendment Change Summary",
            max_retries,
            model_key="fast",
        )

    return new_report, change_summary, verification_notes

