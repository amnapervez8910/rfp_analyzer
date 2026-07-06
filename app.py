import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
import time
from google.api_core import exceptions
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv  
import os  
# =====================================================
# LOAD ENVIRONMENT VARIABLES
# =====================================================

load_dotenv()  # .env file load 

# =====================================================
# PAGE CONFIG
# =====================================================

st.set_page_config(
    page_title="AI Proposal Capture System",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =====================================================
# CUSTOM CSS - EMBEDDED DIRECTLY
# =====================================================

def load_css():
    """Load CSS from the external style.css file (same styling as before,
    just moved out of app.py into its own file) and wrap it in a <style> tag."""
    css_path = Path(__file__).parent / "style.css"
    with open(css_path, "r", encoding="utf-8") as f:
        css_content = f.read()
    return f"<style>\n{css_content}\n</style>"

st.markdown(load_css(), unsafe_allow_html=True)

# =====================================================
# GEMINI CONFIG
# =====================================================

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    st.error("❌ API Key not found! Please check your .env file.")
    st.stop()

genai.configure(
    api_key=api_key
)

model = genai.GenerativeModel(
    "models/gemini-2.5-flash"
)

# =====================================================
# HEADER
# =====================================================

st.markdown("""
<div class="gradient-header">
    <span class="eyebrow">AI-Powered Capture Engine</span>
    <h1>AI Proposal Capture System</h1>
    <p>Intelligent RFP Analysis • Extract • Evaluate • Decide</p>
</div>
""", unsafe_allow_html=True)

# =====================================================
# FEATURES GRID
# =====================================================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("""
    <div class="info-card card-deliverables">
        <span class="card-icon">📋</span>
        <h3>Deliverables</h3>
        <p>Extract all requirements</p>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div class="info-card card-evaluation">
        <span class="card-icon">⚖️</span>
        <h3>Evaluation</h3>
        <p>Criteria & scoring</p>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown("""
    <div class="info-card card-compliance">
        <span class="card-icon">✓</span>
        <h3>Compliance</h3>
        <p>Department-wise checklist</p>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown("""
    <div class="info-card card-decision">
        <span class="card-icon">◆</span>
        <h3>Decision</h3>
        <p>GO / NO-GO intelligence</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# =====================================================
# SUMMARY HELPER (for History tab labels — read-only)
# =====================================================

def extract_quick_summary(raw_report):
    """Pulls Overall Score and Final Decision out of a raw AI report
    just to label a History entry. Does not affect analysis logic."""
    overall = re.search(r'Overall Score:\s*(\d+\.?\d*%)', raw_report, re.IGNORECASE)
    decision = re.search(r'Final Decision:\s*[^\w]*([\w-]+(?:\s+\w+)?)', raw_report, re.IGNORECASE)
    score_text = overall.group(1) if overall else "N/A"
    decision_text = decision.group(1).strip().upper() if decision else "N/A"
    if 'NO-GO' in decision_text or 'NO GO' in decision_text:
        decision_label, decision_icon = "NO-GO", "❌"
    elif 'MAYBE' in decision_text:
        decision_label, decision_icon = "MAYBE", "⚠️"
    elif 'GO' in decision_text:
        decision_label, decision_icon = "GO", "✅"
    else:
        decision_label, decision_icon = decision_text, "❔"
    return score_text, decision_label, decision_icon

# =====================================================
# SESSION STATE
# =====================================================

if "history" not in st.session_state:
    st.session_state.history = []
if "current_result" not in st.session_state:
    st.session_state.current_result = None

# =====================================================
# TOP-LEVEL NAVIGATION
# =====================================================

top_tab_new, top_tab_history = st.tabs([
    "📤 New Analysis",
    f"🕒 History ({len(st.session_state.history)})",
])

# =====================================================
# HISTORY TAB
# =====================================================

with top_tab_history:
    if not st.session_state.history:
        st.info("📭 No previous RFPs analyzed yet in this session. Once you run an analysis, it'll show up here.")
    else:
        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.markdown("Every RFP you've analyzed in this session, most recent first.")
        with col_b:
            if st.button("🗑️ Clear History", use_container_width=True, key="clear_history_btn"):
                st.session_state.history = []
                st.session_state.current_result = None
                st.rerun()

        for idx, entry in enumerate(st.session_state.history):
            score_text, decision_label, decision_icon = extract_quick_summary(entry["raw_report"])
            label = (
                f"📄 {entry['filename']} • "
                f"{entry['timestamp'].strftime('%b %d, %Y %I:%M %p')} • "
                f"Score: {score_text} • {decision_icon} {decision_label}"
            )
            with st.expander(label, expanded=False):
                st.markdown(entry["formatted_report"], unsafe_allow_html=True)
                st.download_button(
                    label="📥 Download This Report",
                    data=entry["raw_report"],
                    file_name=f"rfp_analysis_{entry['timestamp'].strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key=f"history_download_{idx}"
                )

# =====================================================
# FILE UPLOADER
# =====================================================

with top_tab_new:
    st.markdown("""
    <h3 style="margin-bottom: 0.3rem;">📤 Upload RFP Document</h3>
    <p style="color: #a6acd4; margin-top: 0; margin-bottom: 1rem; font-size: 0.92rem;">
        PDF only • Your document is analyzed securely
    </p>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Drop your RFP PDF here or click to browse",
        type=["pdf"],
        label_visibility="collapsed"
    )

# =====================================================
# PDF READER
# =====================================================

def extract_text(pdf):
    reader = PdfReader(pdf)
    text = ""
    total_pages = len(reader.pages)

    progress_text = st.empty()
    progress_bar = st.progress(0)

    for i, page in enumerate(reader.pages):
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

        progress = (i + 1) / total_pages
        progress_bar.progress(progress)
        progress_text.markdown(f"📖 **Reading PDF...** Page {i+1} of {total_pages}")

    progress_bar.empty()
    progress_text.empty()

    return text

# =====================================================
# SCORE RECOMPUTATION (SOURCE OF TRUTH — overrides Gemini's own arithmetic)
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
    """
    Returns a dict: { "Finance Score": {"pct": .., "go": .., "maybe": .., "nogo": .., "total": ..}, ... }
    This is calculated directly from the Decision column of every table row —
    it never trusts any percentage Gemini wrote itself.
    """
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


def determine_final_decision(overall_pct: float, finance_maybe: int, finance_nogo: int) -> str:
    """
    Same rule the prompt describes, but computed in Python so it can NEVER
    disagree with the recomputed Overall Score. Priority order matters:
      1. Anything under 60% is an automatic NO-GO, no matter what.
      2. 80%+ AND every Finance row is GO -> GO.
      3. Everything else (60-79%, or a Finance MAYBE/NO-GO exists) -> MAYBE.
    """
    if overall_pct < 60:
        return "NO-GO"
    if overall_pct >= 80 and finance_maybe == 0 and finance_nogo == 0:
        return "GO"
    return "MAYBE"


def sync_justification_score(report_text: str, overall_pct: float, correct_decision: str) -> str:
    """
    Gemini writes the Justification paragraph as free text and sometimes
    quotes a score number OR a decision word (GO/NO-GO/MAYBE) that doesn't
    match the recomputed Overall Score / Final Decision. This finds those
    phrases ONLY inside the Justification section and forces them to the
    correct values, without touching unrelated percentages elsewhere in the
    RFP facts (e.g. '40% SWAM target', '99.99% uptime').
    """
    correct = _format_pct(overall_pct)
    match = re.search(
        r'(##?\s*JUSTIFICATION\s*\n+)(.+?)(?=\n\n|\Z)',
        report_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return report_text

    just_text = match.group(2)

    # Fix any quoted score number
    fixed_just = re.sub(
        r"score\s*(?:of|is|:)?\s*\d+\.?\d*%",
        f"score of {correct}",
        just_text,
        flags=re.IGNORECASE,
    )

    # Fix any quoted decision word (GO / NO-GO / MAYBE) so it matches
    # the actual computed Final Decision, e.g. "the final recommendation
    # is MAYBE" when the real decision is NO-GO.
    fixed_just = re.sub(
        r"(recommendation|decision)\s+is\s+(?:a\s+)?(?:GO|NO-GO|NO GO|MAYBE)\b",
        rf"\1 is {correct_decision}",
        fixed_just,
        flags=re.IGNORECASE,
    )

    return report_text[:match.start(2)] + fixed_just + report_text[match.end(2):]

def apply_score_fix(report_text: str) -> str:
    """
    Single source of truth for everything numeric in the report:
    1. Recomputes each team's % strictly from Decision columns.
    2. Recomputes Overall Score as the average of the four team %s.
    3. Recomputes Final Decision using the exact same numbers (so it can
       never contradict the score shown).
    4. Forces the Justification paragraph's quoted score to match.
    This guarantees the Scoring Summary, Final Decision, and Justification
    are always internally consistent, regardless of any arithmetic mistake
    Gemini might have made in its own draft.
    """
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
    correct_decision = determine_final_decision(overall_pct, finance_maybe, finance_nogo)

    if re.search(r"Final Decision:\s*[^\n]*", fixed, re.IGNORECASE):
        fixed = re.sub(
            r"Final Decision:\s*[^\n]*",
            f"Final Decision: {correct_decision}",
            fixed,
            flags=re.IGNORECASE,
        )
    else:
        fixed += f"\n\nFinal Decision: {correct_decision}\n"

    fixed = sync_justification_score(fixed, overall_pct, correct_decision)

    return fixed
# =====================================================
# AI ANALYSIS
# =====================================================

def analyze_rfp(document_text, max_retries=5):
    prompt = f"""
You are an SPS Proposal Capture Manager.

Analyze ONLY the uploaded RFP, STRICTLY against the fixed checklist below.
Do NOT use any generic knowledge — only what is written inside the RFP text.

Every checklist item has hidden sub-criteria (listed for you below, for your
own internal checking only — do NOT print these sub-criteria or any decision
rules in your output, only print the final Item / Status / Decision / Explanation
table exactly in the format shown further down).

STRICT RULES:
1. Use ONLY information present in RFP.
2. Never guess. Never hallucinate.
3. If information is missing write: "Not specified in RFP".
4. Keep response concise and professional.
5. Remove duplicate information.
6. Check EACH item against its sub-criteria (below) before deciding status — but only output the final Item/Status/Decision/Explanation table, nothing else about the sub-criteria.
7. Every row must also carry a per-item Decision of GO, NO-GO, or MAYBE, decided using these exact rules (apply silently, do not print the rules themselves):
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
     - If the RFP does not mention personnel/capability requirements at all (rare) → Status ❌ NOT FOUND, Decision NO-GO.
     Whenever the Decision is GO for this item, the Explanation must end with a short note: SPS must separately confirm internally that it has personnel matching the described qualifications, since the AI cannot verify SPS's actual staffing.
   - Quantum of Input Required: this checklist item covers four sub-parts — Expected Revenue Generation, Period of Implementation, Insurance Coverage, and Compliance of Law. Expected Revenue Generation is ALWAYS the bidder's own internal estimate (same as in Profitability Analysis) — the RFP will essentially never state SPS's expected revenue, so its absence must never pull the Status to NOT FOUND or the Decision to NO-GO. Base the Status/Decision on ONLY the three RFP-derivable sub-parts (Period of Implementation, Insurance Coverage, Compliance of Law):
     - If all three RFP-derivable sub-parts are clearly stated → Status ✅ FOUND, Decision GO.
     - If some are missing or ambiguous → Status ⚠️ ACTION REQUIRED, Decision MAYBE.
     - If none of the three are addressed at all → Status ❌ NOT FOUND, Decision NO-GO.
     The Explanation must always end with a short note: Expected Revenue Generation is SPS's own internal projection for this project and is not something the RFP is expected to provide.
   - Scope Alignment: Status and Decision are SEPARATE for this item. Status is ONLY about whether the RFP describes its scope of work / statement of needs at all — mark Status ✅ FOUND whenever the RFP defines what it is seeking (this is true for almost every RFP). Mark Status ❌ NOT FOUND only if the RFP genuinely contains no scope/statement-of-needs description whatsoever. Decision is about whether that described scope matches SPS's own portfolio (Identity and Access Management, cybersecurity solutions, identity governance, access control): Decision GO if the scope is genuinely about IAM/cybersecurity/identity/access-control; Decision NO-GO if the scope is about something unrelated (e.g. website search, personalization, general software development, marketing, construction, unrelated AI/ML products) even though the scope itself is clearly described (Status must still stay FOUND, never NOT FOUND, in this case); Decision MAYBE only if the scope is partially related or ambiguous. Do not let a NO-GO decision pull the Status down to NOT FOUND — a clearly-out-of-scope RFP is Status FOUND + Decision NO-GO, not Status NOT FOUND.
   - All other items: Status ✅ FOUND → Decision GO. Status ⚠️ ACTION REQUIRED (partially/ambiguously mentioned) → Decision MAYBE. Status ❌ NOT FOUND (absent) → Decision NO-GO.
8. Do not add references from your own.


Internal sub-criteria reference (for your checking only, never print):
- Payment Terms: payment schedule, milestones, retainage, late-payment penalties.
- Financial Stability Requirements: financial statements / proof of financial stability required. This is a THREE-WAY conditional check, not a plain found/not-found risk item — see the special rule above (clear requirement = GO, general "may investigate + shall furnish info as requested" clause = MAYBE, truly no mention at all = GO). Unaudited financial statements should be treated as sufficient proof unless the RFP explicitly demands audited statements.
- Insurance Requirements: required coverage amount. See special rule above for the "not mentioned" case (MAYBE, not NO-GO).
- Profitability Analysis: expected revenue vs projected cost / budget / contract value. This is always the bidder's own internal exercise — see special rule above (NOT FOUND = MAYBE, never NO-GO).
- Bid Bond: bid bond or bond percentage requirement.
- Eligibility Criteria: relevant experience, registration requirement, prior-year financial statement.
- Capability: qualified personnel, technical know-how. Status/Decision reflect ONLY what the RFP asks for regarding personnel/skills disclosure, never whether SPS actually has that staff — see special rule above. GO decisions always carry an internal-confirmation note in the Explanation.
- Quantum of Input: expected revenue generation, implementation period, insurance coverage, compliance of law. Expected Revenue Generation is always the bidder's own internal estimate and must never drag Status/Decision down — see special rule above. Base Status/Decision only on implementation period, insurance coverage, and compliance of law.
- Data Protection: data protection laws / regulatory compliance.
- State Registration: requirement to register in the state of execution.
- E-Verify: requirement to use E-Verify system.
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

================================================

# DELIVERABLES

Extract ALL deliverables required from the bidder.

Provide table:

| Deliverable | Description | Deadline |

================================================

# EVALUATION CRITERIA

Summarize:

### Technical Evaluation Criteria
List with weights/points

### Financial Evaluation Criteria
List with method and weight %

### Mandatory Requirements
### Minimum Threshold
### Disqualification Conditions

================================================

# COMPLIANCE CHECKLIST

## FINANCE TEAM
| Item | Status | Decision | Explanation |
|------|--------|----------|-------------|
| Payment Terms (NET30 rule) | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Financial Stability | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Insurance Requirements ($5M rule) | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Profitability Analysis | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Bid Bond | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |


## LEGAL TEAM
| Item | Status | Decision | Explanation |
|------|--------|----------|-------------|
| Eligibility Criteria | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Capability | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Quantum of Input | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Data Protection | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| State Registration | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| E-Verify | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Contractual Obligations | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |

## OPERATIONS TEAM
| Item | Status | Decision | Explanation |
|------|--------|----------|-------------|
| Required Forms | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Submission Deadlines | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Document Compliance | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Signatory Authority | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Required Documents | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Responsible Person | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Meeting with Ops | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Vendor Registration | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |

## TECHNICAL TEAM
| Item | Status | Decision | Explanation |
|------|--------|----------|-------------|
| Scope Alignment | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Technical Requirements | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Industry Standards | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Security Requirements | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |
| Integration Needs | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |

================================================

# SCORING SUMMARY

Calculate scores based on the DECISION column for each team (✅ GO = 1 point, ⚠️ MAYBE = 0.5 point, ❌ NO-GO = 0 point) out of total items per team. Do NOT score based on the Status column — Status only shows whether info exists in the RFP, Decision shows whether it is actually favorable.

Finance Score: [XX%]
Legal Score: [XX%]
Operations Score: [XX%]
Technical Score: [XX%]

Overall Score: [average of the four scores, XX%]

================================================

# QUALIFICATION DECISION

Strategic Fit: [Strong / Moderate / Poor]
Capability Alignment: [Strong / Moderate / Poor]
Financial Viability: [Viable / Needs Review / Not Viable]
Risk Assessment: [Low / Medium / High]

## FINAL RECOMMENDATION

Based on the overall score AND on whether any checklist row above (especially Finance team rows: Payment Terms, Insurance Requirements) carries a NO-GO or MAYBE Decision:
- If Score >= 80% AND every Finance row Decision = GO (no NO-GO/MAYBE anywhere, including Insurance and Payment Terms) → ✅ GO - Strongly recommend pursuing this proposal
- If ANY issue/flag exists — a Finance row is MAYBE or NO-GO (e.g. payment terms > NET30, insurance coverage > $5M, insurance not mentioned, or Score is 60-79%) → ⚠️ MAYBE - Proceed with caution, need risk mitigation. Do NOT auto-fail the whole proposal just because one item has a problem; treat it as a flag to resolve.
- Only if Score < 60% (overall checklist mostly missing/failing) → ❌ NO-GO - Do not pursue this proposal

Final Decision: [GO / NO-GO / MAYBE]

## JUSTIFICATION

[Clear 3-4 sentence explanation. If the decision is MAYBE, explicitly name WHICH item(s) caused it (e.g. "Insurance requirement of $10M exceeds the $5M threshold" or "Payment terms are NET60, exceeding NET30") so the reason is obvious, not generic:
- Why this decision was made
- Key strengths identified
- Key risks or gaps (name the specific flagged item(s) here)
- What needs to happen next]

================================================

RFP DOCUMENT:
{document_text}
"""

    status_placeholder = st.empty()
    progress_placeholder = st.empty()

    status_placeholder.markdown("""
    <div class="processing-status">
        <h3>🧠 <span class="highlight">AI Analysis in Progress</span></h3>
        <div class="step-indicator">
            <div class="step active"><span class="step-icon">📄</span> Reading Document</div>
            <div class="step"><span class="step-icon">🔍</span> Extracting Data</div>
            <div class="step"><span class="step-icon">📊</span> Analyzing Compliance</div>
            <div class="step"><span class="step-icon">✅</span> Generating Report</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    progress_bar = progress_placeholder.progress(0)

    for attempt in range(max_retries):
        try:
            progress_bar.progress(0.3)
            status_placeholder.markdown("""
            <div class="processing-status">
                <h3>🧠 <span class="highlight">AI Analysis in Progress</span></h3>
                <div class="step-indicator">
                    <div class="step done"><span class="step-icon">📄</span> Reading Document</div>
                    <div class="step active"><span class="step-icon">🔍</span> Extracting Data</div>
                    <div class="step"><span class="step-icon">📊</span> Analyzing Compliance</div>
                    <div class="step"><span class="step-icon">✅</span> Generating Report</div>
                </div>
                <p style="color: #c3c8e6; margin-top: 0.5rem;">⏳ Analyzing RFP content...</p>
            </div>
            """, unsafe_allow_html=True)

            progress_bar.progress(0.5)

            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0,
                    "top_p": 1,
                    "top_k": 1,
                    "candidate_count": 1
                }
            )

            progress_bar.progress(0.9)
            status_placeholder.markdown("""
            <div class="processing-status">
                <h3>🧠 <span class="highlight">AI Analysis in Progress</span></h3>
                <div class="step-indicator">
                    <div class="step done"><span class="step-icon">📄</span> Reading Document</div>
                    <div class="step done"><span class="step-icon">🔍</span> Extracting Data</div>
                    <div class="step done"><span class="step-icon">📊</span> Analyzing Compliance</div>
                    <div class="step active"><span class="step-icon">✅</span> Generating Report</div>
                </div>
                <p style="color: #00d4aa; margin-top: 0.5rem;">✨ Finalizing report...</p>
            </div>
            """, unsafe_allow_html=True)

            progress_bar.progress(1.0)
            time.sleep(0.5)
            status_placeholder.empty()
            progress_placeholder.empty()

            fixed_text = apply_score_fix(response.text)
            return fixed_text

        except exceptions.ResourceExhausted as e:
            if hasattr(e, 'retry_delay'):
                wait_time = e.retry_delay.seconds + 2
            else:
                wait_time = (2 ** attempt) * 10

            status_placeholder.markdown(f"""
            <div class="processing-status">
                <h3>⏳ <span class="highlight">Rate Limit Reached</span></h3>
                <p style="color: #fbbf24;">Waiting {wait_time:.0f} seconds... (Attempt {attempt+1}/{max_retries})</p>
            </div>
            """, unsafe_allow_html=True)

            progress_bar.progress((attempt + 1) / max_retries)

            for i in range(int(wait_time)):
                time.sleep(1)

        except Exception as e:
            st.error(f"❌ Error: {e}")
            status_placeholder.empty()
            progress_placeholder.empty()
            raise

    status_placeholder.empty()
    progress_placeholder.empty()
    st.error("❌ All retries failed. Please try again later.")
    return "Analysis failed due to rate limits. Please try again after some time."

# =====================================================
# FORMAT REPORT
# =====================================================

def format_report(report):
    """Format the report with clean markdown"""

    report = re.sub(r'[»›•]', '', report)
    report = report.replace('**', '')

    report = report.replace(
        '# DELIVERABLES',
        '\n\n<div class="section-banner sec-deliverables"><span class="section-icon">📋</span><span class="section-title">Deliverables</span></div>\n\n'
    )
    report = report.replace(
        '# EVALUATION CRITERIA',
        '\n\n<div class="section-banner sec-evaluation"><span class="section-icon">⚖️</span><span class="section-title">Evaluation Criteria</span></div>\n\n'
    )
    report = report.replace(
        '# COMPLIANCE CHECKLIST',
        '\n\n<div class="section-banner sec-checklist"><span class="section-icon">✅</span><span class="section-title">Compliance Checklist</span></div>\n\n'
    )
    report = report.replace(
        '# SCORING SUMMARY',
        '\n\n<div class="section-banner sec-scoring"><span class="section-icon">📊</span><span class="section-title">Scoring Summary</span></div>\n\n'
    )
    report = report.replace(
        '# QUALIFICATION DECISION',
        '\n\n<div class="section-banner sec-decision"><span class="section-icon">🎯</span><span class="section-title">Qualification Decision</span></div>\n\n'
    )

    report = report.replace(
        '## FINANCE TEAM',
        '\n\n<div class="team-banner team-finance"><span class="team-icon">💰</span>Finance Team</div>\n\n'
    )
    report = report.replace(
        '## LEGAL TEAM',
        '\n\n<div class="team-banner team-legal"><span class="team-icon">⚖️</span>Legal Team</div>\n\n'
    )
    report = report.replace(
        '## OPERATIONS TEAM',
        '\n\n<div class="team-banner team-ops"><span class="team-icon">📋</span>Operations Team</div>\n\n'
    )
    report = report.replace(
        '## TECHNICAL TEAM',
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

# =====================================================
# MAIN APP
# =====================================================

with top_tab_new:
    if uploaded_file:
        st.markdown("""
        <div class="success-box">
            ✅ PDF Uploaded Successfully! Ready for analysis.
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            st.info(f"📄 **File Name:** {uploaded_file.name}")
        with col2:
            st.info(f"📊 **File Size:** {round(uploaded_file.size / 1024, 2)} KB")

        if st.button("🚀 Start Analysis", use_container_width=True):
            with st.spinner("📖 Reading PDF document..."):
                document_text = extract_text(uploaded_file)

            report = analyze_rfp(document_text)

            if report and "Analysis failed" not in report:
                formatted_report = format_report(report)
                record = {
                    "filename": uploaded_file.name,
                    "timestamp": datetime.now(),
                    "raw_report": report,
                    "formatted_report": formatted_report,
                }
                st.session_state.current_result = record
                st.session_state.history.insert(0, record)
                st.rerun()
            else:
                st.error("❌ Analysis failed. Please try again.")

    if st.session_state.current_result:
        result = st.session_state.current_result

        st.markdown("""
        <div class="success-box">
            ✅ Analysis Completed Successfully!
        </div>
        """, unsafe_allow_html=True)

        sections = split_report_sections(result["formatted_report"])

        st.markdown("---")

        tab_deliverables, tab_evaluation, tab_checklist, tab_decision = st.tabs([
            "📋 Deliverables",
            "⚖️ Evaluation Criteria",
            "✅ Compliance Checklist",
            "🎯 Scoring & Decision",
        ])

        with tab_deliverables:
            st.markdown(
                sections.get("sec-deliverables", "_No deliverables section found in the report._"),
                unsafe_allow_html=True
            )

        with tab_evaluation:
            st.markdown(
                sections.get("sec-evaluation", "_No evaluation criteria section found in the report._"),
                unsafe_allow_html=True
            )

        with tab_checklist:
            st.markdown(
                sections.get("sec-checklist", "_No compliance checklist section found in the report._"),
                unsafe_allow_html=True
            )

        with tab_decision:
            combined_decision = sections.get("sec-scoring", "") + sections.get("sec-decision", "")
            st.markdown(
                combined_decision or "_No scoring/decision section found in the report._",
                unsafe_allow_html=True
            )

        st.markdown("---")

        st.download_button(
            label="📥 Download Report",
            data=result["raw_report"],
            file_name="rfp_analysis_report.md",
            mime="text/markdown",
            use_container_width=True
        )

# =====================================================
# FOOTER
# =====================================================

st.markdown("---")

st.markdown(
    """
    <div style="background: linear-gradient(160deg, #12132a, #181a35); padding: 2.2rem; border-radius: 20px; margin-top: 1.5rem; border: 1px solid rgba(255, 255, 255, 0.07); text-align: center; box-shadow: 0 10px 30px rgba(5,5,20,0.4);">
        <div style="font-size: 1.25rem; font-weight: 700; font-family: 'Sora', sans-serif; letter-spacing: 0.5px; margin-bottom: 0.8rem; background: linear-gradient(90deg, #7c6cff, #b06cff, #ff6cd6); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">AI Proposal Capture System</div>
        <div style="width: 60px; height: 3px; background: linear-gradient(90deg, #7c6cff, #b06cff); margin: 0.9rem auto; border-radius: 10px;"></div>
        <div style="color: #cdd2ef; font-size: 0.9rem; margin: 0.5rem 0;">🔒 Powered by Google Gemini AI &nbsp;•&nbsp; Secure &amp; Confidential</div>
        <div style="color: #cdd2ef; font-size: 0.9rem; margin: 0.5rem 0;">Developed by <span style="color: #35e6c8; font-weight: 700; font-size: 1rem;">Amna Pervez</span></div>
        <div style="width: 40px; height: 1px; background: rgba(255,255,255,0.08); margin: 0.6rem auto;"></div>
        <div style="color: #a6acd4; font-size: 0.82rem; margin-top: 0.1rem; letter-spacing: 0.5px; font-weight: 500;">© 2026 AI Proposal Capture System • All Rights Reserved</div>
    </div>
    """,
    unsafe_allow_html=True
)
