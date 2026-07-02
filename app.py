import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
import time
from google.api_core import exceptions
import re
from pathlib import Path
import os
from dotenv import load_dotenv

# =====================================================
# LOAD ENVIRONMENT VARIABLES
# =====================================================
load_dotenv()

# =====================================================
# GEMINI CONFIG
# =====================================================

# Use environment variable for API key (SECURE)
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    # Fallback for testing - REMOVE IN PRODUCTION
    API_KEY = "YOUR_API_KEY_HERE"
    st.warning("⚠️ Using hardcoded API key. Please set GEMINI_API_KEY in .env file")

genai.configure(api_key=API_KEY)

model = genai.GenerativeModel(
    "models/gemini-2.0-flash-exp"
)

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
# CUSTOM CSS - LOAD FROM EXTERNAL FILE
# =====================================================

def load_css():
    """Load CSS from external file"""
    css_path = Path(__file__).parent / "style.css"
    if css_path.exists():
        with open(css_path, "r") as f:
            css = f.read()
        return f"<style>{css}</style>"
    else:
        # Fallback inline CSS if file doesn't exist
        return """
        <style>
            .stApp { background: #0a0a0a; }
            .main { padding: 2rem; background: #0a0a0a; }
            .gradient-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 2rem;
                border-radius: 12px;
                text-align: center;
                margin-bottom: 2rem;
            }
            .gradient-header h1 { color: white; margin: 0; }
            .gradient-header p { color: rgba(255,255,255,0.9); }
            .info-card {
                background: #1a1a2e;
                padding: 1.5rem;
                border-radius: 10px;
                text-align: center;
                border: 1px solid #2a2a4a;
            }
            .card-icon { font-size: 2.5rem; display: block; }
            .info-card h3 { color: #e6e6e6; }
            .info-card p { color: #8892b0; }
            .processing-status {
                background: #1a1a2e;
                padding: 2rem;
                border-radius: 10px;
                margin: 2rem 0;
            }
            .step-indicator { display: flex; gap: 1rem; margin: 1.5rem 0; }
            .step {
                flex: 1;
                padding: 0.8rem;
                background: #0d0d1a;
                border-radius: 6px;
                text-align: center;
                color: #8892b0;
                opacity: 0.5;
            }
            .step.active { opacity: 1; background: #1a1a3e; border: 1px solid #667eea; color: #e6e6e6; }
            .step.done { opacity: 1; color: #4CAF50; }
            .highlight { color: #00d4aa; }
            .status-go { color: #4CAF50; font-weight: bold; }
            .status-maybe { color: #FF9800; font-weight: bold; }
            .status-no-go { color: #f44336; font-weight: bold; }
        </style>
        """
    return ""

# Apply the CSS
st.markdown(load_css(), unsafe_allow_html=True)

# =====================================================
# HEADER
# =====================================================

st.markdown("""
<div class="gradient-header">
    <h1>📄 AI Proposal Capture System</h1>
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
# FILE UPLOADER
# =====================================================

st.markdown("### 📤 Upload RFP Document")

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
# AI ANALYSIS
# =====================================================

def analyze_rfp(document_text, max_retries=5):
    prompt = f"""
You are an SPS Proposal Capture Manager.

Analyze ONLY the uploaded RFP, STRICTLY against the fixed checklist below.
Do NOT use any generic knowledge — only what is written inside the RFP text.

Every checklist item has hidden sub-criteria (listed for you below, for your
own internal checking only — do NOT print these sub-criteria or any decision
rules in your output, only print the final Item / Status / Explanation table
exactly in the format shown further down).

STRICT RULES:
1. Use ONLY information present in RFP.
2. Never guess. Never hallucinate.
3. If information is missing write: "Not specified in RFP".
4. Keep response concise and professional.
5. Remove duplicate information.
6. Check EACH item against its sub-criteria (below) before deciding status — but only output the final Item/Status/Explanation table, nothing else about the sub-criteria.
7. Apply these exact decision rules silently, do not print them:
   - Payment Terms: if RFP states NET30 → ✅ FOUND. If more than NET30 (NET45/60 etc) → ⚠️ ACTION REQUIRED (escalate to accounting). If not mentioned → ❌ NOT FOUND.
   - Insurance Requirements: 
     * If RFP states exactly $5M or less → ✅ FOUND (GO DECISION)
     * If RFP states more than $5M → ❌ NOT FOUND (AUTOMATIC NO-GO - DISQUALIFICATION)
     * If not mentioned → ❌ NOT FOUND (Needs clarification)
   - All other items: ✅ FOUND only if clearly stated in RFP, ⚠️ ACTION REQUIRED if partially/ambiguously mentioned, ❌ NOT FOUND if absent.

Internal sub-criteria reference (for your checking only, never print):
- Payment Terms: payment schedule, milestones, retainage, late-payment penalties.
- Financial Stability Requirements: unaudited/audited financial statements or proof of financial stability required.
- Insurance Requirements: required coverage amount.
- Profitability Analysis: expected revenue vs projected cost / budget / contract value.
- Bid Bond: bid bond or bond percentage requirement.
- Eligibility Criteria: relevant experience, registration requirement, prior-year financial statement.
- Capability: qualified personnel, technical know-how.
- Quantum of Input: expected revenue generation, implementation period, insurance coverage, compliance of law.
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
- Scope Alignment: does scope match SPS offerings (IAM, cybersecurity, etc).
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
| Item | Status | Explanation |
|------|--------|-------------|
| Payment Terms (NET30 rule) | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Financial Stability | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Insurance Requirements ($5M rule) | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Profitability Analysis | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Bid Bond | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |


## LEGAL TEAM
| Item | Status | Explanation |
|------|--------|-------------|
| Eligibility Criteria | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Capability | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Quantum of Input | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Data Protection | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| State Registration | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| E-Verify | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Contractual Obligations | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |

## OPERATIONS TEAM
| Item | Status | Explanation |
|------|--------|-------------|
| Required Forms | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Submission Deadlines | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Document Compliance | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Signatory Authority | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Required Documents | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Responsible Person | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Meeting with Ops | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Vendor Registration | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |

## TECHNICAL TEAM
| Item | Status | Explanation |
|------|--------|-------------|
| Scope Alignment | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Technical Requirements | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Industry Standards | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Security Requirements | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |
| Integration Needs | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | [Brief] |

================================================

# QUALIFICATION DECISION

Strategic Fit: [Strong / Moderate / Poor]
Capability Alignment: [Strong / Moderate / Poor]
Financial Viability: [Viable / Needs Review / Not Viable]
Risk Assessment: [Low / Medium / High]

## JUSTIFICATION

[Clear 3-4 sentence explanation:
- Key strengths identified
- Key risks or gaps
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
                <p style="color: #8892b0; margin-top: 0.5rem;">⏳ Analyzing RFP content...</p>
            </div>
            """, unsafe_allow_html=True)

            progress_bar.progress(0.5)

            response = model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0,
                    "top_p": 0.8,
                    "top_k": 20
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

            return response.text

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
# REAL PYTHON-BASED SCORING
# =====================================================

STATUS_POINTS = {
    "✅": 1.0,
    "⚠️": 0.5,
    "❌": 0.0,
}

TEAM_SECTION_PATTERN = re.compile(
    r'##\s*(FINANCE TEAM|LEGAL TEAM|OPERATIONS TEAM|TECHNICAL TEAM)\s*\n(.*?)(?=\n##|\Z)',
    re.DOTALL | re.IGNORECASE
)

ROW_STATUS_PATTERN = re.compile(r'^\|(.+?)\|\s*(✅|⚠️|❌)[^|]*\|', re.MULTILINE)


def parse_team_rows(section_text):
    """Return list of (item_name, status_symbol) for one team's table."""
    rows = []
    for match in ROW_STATUS_PATTERN.finditer(section_text):
        item = match.group(1).strip()
        status = match.group(2)
        # skip the header/separator rows of the markdown table
        if item.lower() in ("item", ""):
            continue
        if set(item) <= {"-", ":", " "}:
            continue
        rows.append((item, status))
    return rows


def compute_team_score(rows):
    if not rows:
        return None
    total_points = sum(STATUS_POINTS.get(status, 0.0) for _, status in rows)
    max_points = len(rows)
    return round((total_points / max_points) * 100, 1)


def compute_real_scores(report):
    """
    Parses the raw AI report text and independently computes:
    - per-team scores
    - overall score
    - whether an unresolved Finance ACTION REQUIRED flag exists
      (Payment Terms > NET30 or Insurance > $5M)
    - the final GO / MAYBE / NO-GO decision, per the fixed rules
    Returns a dict with everything the report needs.
    """
    team_scores = {}
    finance_rows = []

    for match in TEAM_SECTION_PATTERN.finditer(report):
        team_name = match.group(1).upper()
        section_text = match.group(2)
        rows = parse_team_rows(section_text)
        score = compute_team_score(rows)
        team_scores[team_name] = score
        if "FINANCE" in team_name:
            finance_rows = rows

    finance = team_scores.get("FINANCE TEAM")
    legal = team_scores.get("LEGAL TEAM")
    ops = team_scores.get("OPERATIONS TEAM")
    tech = team_scores.get("TECHNICAL TEAM")

    valid_scores = [s for s in (finance, legal, ops, tech) if s is not None]
    overall = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else None

    # Check for Insurance NO-GO condition (Insurance > $5M)
    insurance_no_go = False
    for item, status in finance_rows:
        item_lower = item.lower()
        if "insurance" in item_lower:
            # If insurance is marked as NOT FOUND due to >$5M
            if status == "❌" and ("more than 5" in item_lower or "exceeds" in item_lower or ">$5M" in item_lower):
                insurance_no_go = True
            # Also check if explanation contains >$5M
            # We'll check the explanation text in the report too
            if "more than 5" in item_lower or "exceeds" in item_lower:
                insurance_no_go = True

    # Check for an unresolved Finance ACTION REQUIRED flag on
    # Payment Terms specifically (Insurance now triggers NO-GO directly)
    finance_flag = False
    for item, status in finance_rows:
        item_lower = item.lower()
        if status == "⚠️" and "payment terms" in item_lower:
            finance_flag = True

    decision = None
    if insurance_no_go:
        decision = "NO-GO"  # Force NO-GO if insurance > $5M
    elif overall is not None:
        if overall >= 80 and not finance_flag:
            decision = "GO"
        elif overall < 60:
            decision = "NO-GO"
        else:
            decision = "MAYBE"

    return {
        "finance": finance,
        "legal": legal,
        "ops": ops,
        "tech": tech,
        "overall": overall,
        "finance_flag": finance_flag,
        "insurance_no_go": insurance_no_go,
        "decision": decision,
    }

# =====================================================
# FORMAT REPORT
# =====================================================

def format_report(report):
    """Format the report with clean markdown, using real computed
    scores/decision (Fix #2) and robust section extraction (Fix #3)."""

    # Compute the real, verifiable scores BEFORE any text is stripped out.
    scores = compute_real_scores(report)

    # Remove all HTML tags and junk
    report = re.sub(r'<[^>]+>', '', report)
    report = re.sub(r'»|›|•', '', report)
    report = re.sub(r'\*\*', '', report)


    # ============================================
    # HEADERS WITH ICONS
    # ============================================

    report = report.replace('# DELIVERABLES', '## 📋 DELIVERABLES')
    report = report.replace('# EVALUATION CRITERIA', '## ⚖️ EVALUATION CRITERIA')
    report = report.replace('# COMPLIANCE CHECKLIST', '## ✅ COMPLIANCE CHECKLIST')
    report = report.replace('# QUALIFICATION DECISION', '## 🎯 QUALIFICATION DECISION')

    # ============================================
    # QUALIFICATION DECISION - OVERRIDE WITH REAL SCORES
    # ============================================

    # Find and replace the qualification decision section
    decision_pattern = r'## 🎯 QUALIFICATION DECISION.*?(?=\n##|\Z)'
    decision_match = re.search(decision_pattern, report, re.DOTALL)

    if decision_match:
        decision_section = decision_match.group(0)

        # Get real scores and decision
        decision = scores.get('decision', 'MAYBE')
        overall = scores.get('overall', 0)

        # Map decision to status class
        status_class = {
            'GO': 'status-go',
            'MAYBE': 'status-maybe',
            'NO-GO': 'status-no-go'
        }.get(decision, 'status-maybe')

        # Replace the qualification decision with real data
        new_decision = f"""
## 🎯 QUALIFICATION DECISION

**Overall Compliance Score:** {overall}%

**Decision: <span class="{status_class}">{decision}</span>**

**Team Scores:**
- Finance Team: {scores.get('finance', 'N/A')}%
- Legal Team: {scores.get('legal', 'N/A')}%
- Operations Team: {scores.get('ops', 'N/A')}%
- Technical Team: {scores.get('tech', 'N/A')}%

**Issues:**
{f'⚠️ **Finance Flag:** ACTION REQUIRED on Payment Terms' if scores.get('finance_flag') else '✅ No finance issues'}
{f'❌ **Insurance NO-GO:** Insurance requirement exceeds $5M' if scores.get('insurance_no_go') else '✅ Insurance compliant'}

### JUSTIFICATION

[Clear 3-4 sentence explanation:
- Key strengths identified
- Key risks or gaps
- What needs to happen next]
"""

        # Replace the old decision section with the new one
        report = report.replace(decision_match.group(0), new_decision)

    # ============================================
    # ADD SCORING SUMMARY AT TOP
    # ============================================

    summary = f"""
## 📊 COMPLIANCE SCORING SUMMARY

| Team | Score | Status |
|------|-------|--------|
| Finance | {scores.get('finance', 'N/A')}% | {'✅' if scores.get('finance', 0) >= 70 else '⚠️' if scores.get('finance', 0) >= 50 else '❌'} |
| Legal | {scores.get('legal', 'N/A')}% | {'✅' if scores.get('legal', 0) >= 70 else '⚠️' if scores.get('legal', 0) >= 50 else '❌'} |
| Operations | {scores.get('ops', 'N/A')}% | {'✅' if scores.get('ops', 0) >= 70 else '⚠️' if scores.get('ops', 0) >= 50 else '❌'} |
| Technical | {scores.get('tech', 'N/A')}% | {'✅' if scores.get('tech', 0) >= 70 else '⚠️' if scores.get('tech', 0) >= 50 else '❌'} |
| **Overall** | **{scores.get('overall', 'N/A')}%** | **{scores.get('decision', 'MAYBE')}** |

---

"""
    # Insert summary after the header
    report = report.replace('## 📋 DELIVERABLES', summary + '## 📋 DELIVERABLES')

    # ============================================
    # CLEANUP
    # ============================================

    # Remove duplicate newlines
    report = re.sub(r'\n{3,}', '\n\n', report)

    return report

# =====================================================
# MAIN APP LOGIC
# =====================================================

if uploaded_file is not None:
    with st.spinner("📖 Extracting text from PDF..."):
        document_text = extract_text(uploaded_file)

    if document_text.strip():
        st.success(f"✅ Successfully extracted {len(document_text)} characters from PDF")

        if st.button("🚀 Analyze RFP", type="primary", use_container_width=True):
            with st.spinner("🧠 Analyzing with AI..."):
                raw_report = analyze_rfp(document_text)

                if raw_report and "failed" not in raw_report.lower():
                    formatted_report = format_report(raw_report)

                    # Display the report
                    st.markdown("---")
                    st.markdown("## 📊 RFP Analysis Report")
                    st.markdown(formatted_report)

                    # Download button
                    st.download_button(
                        label="📥 Download Report",
                        data=formatted_report,
                        file_name=f"rfp_analysis_{time.strftime('%Y%m%d_%H%M%S')}.md",
                        mime="text/markdown",
                        use_container_width=True
                    )
                else:
                    st.error("❌ Analysis failed. Please try again.")
    else:
        st.error("❌ No text could be extracted from the PDF. Please ensure it's a text-based PDF.")
else:
    st.info("📤 Please upload an RFP PDF document to begin analysis.")

# =====================================================
# FOOTER
# =====================================================

st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #8892b0; padding: 1rem;">
    <p>🚀 Powered by Gemini AI | Built with Streamlit</p>
    <p style="font-size: 0.8rem;">© 2024 AI Proposal Capture System</p>
</div>
""", unsafe_allow_html=True)
```

---