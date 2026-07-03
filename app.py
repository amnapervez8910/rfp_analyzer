import streamlit as st
from pypdf import PdfReader
import google.generativeai as genai
import time
from google.api_core import exceptions
import re
from pathlib import Path

# =====================================================
# GEMINI CONFIG
# =====================================================

genai.configure("GEMINI_KEY")

model = genai.GenerativeModel(
    "models/gemini-2.5-flash"
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
        </style>
        """

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
   - Insurance Requirements: if RFP states exactly $5M coverage → Status ✅ FOUND, Decision GO. If RFP requires MORE than $5M → Status ⚠️ ACTION REQUIRED, Decision NO-GO (this is a hard limit, do not mark it GO or MAYBE). If not mentioned → Status ❌ NOT FOUND, Decision NO-GO.
   - All other items: Status ✅ FOUND → Decision GO. Status ⚠️ ACTION REQUIRED (partially/ambiguously mentioned) → Decision MAYBE. Status ❌ NOT FOUND (absent) → Decision NO-GO.

Internal sub-criteria reference (for your checking only, never print):
- Payment Terms: payment schedule, milestones, retainage, late-payment penalties.
- Financial Stability Requirements: financial statements / proof of financial stability required.
- Insurance Requirements: required coverage amount.
- Profitability Analysis: expected revenue vs projected cost / budget / contract value.
- Bid Bond: bid bond or bond percentage requirement.
- Taxes: tax ID / tax compliance / tax clearance requirement.
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
- Scope Alignment: SPS's actual service portfolio is Identity and Access Management (IAM), cybersecurity solutions, identity governance, access control, and related security services. Do NOT mark this as FOUND/aligned just because the RFP has a scope/description section defined. Read what the RFP's scope actually asks for and compare it word-for-word against SPS's portfolio above:
  - ✅ FOUND only if the RFP's scope is genuinely about IAM, cybersecurity, identity governance, access control, or a closely related security discipline.
  - ❌ NOT FOUND if the RFP's scope is about something else entirely (e.g. website search, personalization engines, general software development, marketing, construction, unrelated AI/ML products, etc.) — even if that scope is clearly and fully described in the RFP. A well-defined scope that has nothing to do with SPS's services is a NOT FOUND for alignment, not a FOUND.
  - ⚠️ ACTION REQUIRED only if the scope is partially related or ambiguous (e.g. touches on data security or access control as one component among unrelated work).
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
| Taxes | ✅ FOUND / ❌ NOT FOUND / ⚠️ ACTION REQUIRED | GO / NO-GO / MAYBE | [Brief] |

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

Calculate scores based on percentage of FOUND items (✅ FOUND = 1 point, ⚠️ ACTION REQUIRED = 0.5 point, ❌ NOT FOUND = 0 point) out of total items per team.

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
# FORMAT REPORT - FINAL WORKING VERSION
# =====================================================

def format_report(report):
    """Format the report with clean markdown - FINAL WORKING VERSION"""

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
    report = report.replace('# SCORING SUMMARY', '## 📊 SCORING SUMMARY')
    report = report.replace('# QUALIFICATION DECISION', '## 🎯 QUALIFICATION DECISION')

    report = report.replace('## FINANCE TEAM', '### 💰 FINANCE TEAM')
    report = report.replace('## LEGAL TEAM', '### ⚖️ LEGAL TEAM')
    report = report.replace('## OPERATIONS TEAM', '### 📋 OPERATIONS TEAM')
    report = report.replace('## TECHNICAL TEAM', '### 🔧 TECHNICAL TEAM')

     # ============================================
    # EXTRACT SCORES
    # ============================================

    finance = re.search(r'Finance Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)
    legal = re.search(r'Legal Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)
    ops = re.search(r'Operations Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)
    tech = re.search(r'Technical Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)
    overall = re.search(r'Overall Score:\s*(\d+\.?\d*%)', report, re.IGNORECASE)

    def get_color(score_str):
        try:
            num = float(score_str.replace('%', ''))
            if num >= 80:
                return '#00d4aa'
            elif num >= 60:
                return '#fbbf24'
            else:
                return '#ff6b6b'
        except:
            return '#8892b0'

    # Build score HTML cards (no leading whitespace, no blank lines mid-block)
    score_html = '<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1.5rem 0;">'

    if finance:
        score = finance.group(1)
        color = get_color(score)
        score_html += f'<div style="background: linear-gradient(145deg, #1a1a2e, #16213e); padding: 1.2rem; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); text-align: center;"><div style="color: #8892b0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.3rem;">💰 Finance</div><div style="font-size: 2rem; font-weight: 700; color: {color};">{score}</div></div>'

    if legal:
        score = legal.group(1)
        color = get_color(score)
        score_html += f'<div style="background: linear-gradient(145deg, #1a1a2e, #16213e); padding: 1.2rem; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); text-align: center;"><div style="color: #8892b0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.3rem;">⚖️ Legal</div><div style="font-size: 2rem; font-weight: 700; color: {color};">{score}</div></div>'

    if ops:
        score = ops.group(1)
        color = get_color(score)
        score_html += f'<div style="background: linear-gradient(145deg, #1a1a2e, #16213e); padding: 1.2rem; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); text-align: center;"><div style="color: #8892b0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.3rem;">📋 Operations</div><div style="font-size: 2rem; font-weight: 700; color: {color};">{score}</div></div>'

    if tech:
        score = tech.group(1)
        color = get_color(score)
        score_html += f'<div style="background: linear-gradient(145deg, #1a1a2e, #16213e); padding: 1.2rem; border-radius: 12px; border: 1px solid rgba(255,255,255,0.05); text-align: center;"><div style="color: #8892b0; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.3rem;">🔧 Technical</div><div style="font-size: 2rem; font-weight: 700; color: {color};">{score}</div></div>'

    score_html += '</div>'

    if overall:
        score = overall.group(1)
        color = get_color(score)
        score_html += f'<div style="background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 2rem; border-radius: 15px; border: 2px solid rgba(102,126,234,0.3); text-align: center; margin: 1.5rem 0;"><div style="color: #8892b0; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 2px;">📊 Overall Score</div><div style="font-size: 4rem; font-weight: 700; color: {color};">{score}</div></div>'

    # Replace SCORING SUMMARY section entirely with the score cards
    report = re.sub(
        r'## 📊 SCORING SUMMARY.*?(?=##|\Z)',
        f'## 📊 SCORING SUMMARY\n\n{score_html}\n\n',
        report,
        flags=re.DOTALL | re.IGNORECASE
    )

    # ============================================
    # DECISION ITEMS (Strategic Fit / Capability / etc)
    # ============================================

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

# ============================================
    # FINAL DECISION
    # FIX: capture hyphenated values like "NO-GO" correctly
    # ============================================

    decision_match = re.search(r'Final Decision:\s*[^\w]*([\w-]+(?:\s+\w+)?)', report, re.IGNORECASE)
    if decision_match:
        decision = decision_match.group(1).strip().upper()

        if 'NO-GO' in decision or 'NO GO' in decision or 'NOGO' in decision:
            decision_text = (
                '\n## 🎯 FINAL RECOMMENDATION\n\n'
                '### ❌ NO-GO\n\n'
                '🚫 Do not pursue this proposal\n\n'
                '📋 Next Step: Allocate resources to other opportunities\n'
            )
        elif 'MAYBE' in decision:
            decision_text = (
                '\n## 🎯 FINAL RECOMMENDATION\n\n'
                '### ⚠️ MAYBE\n\n'
                '🤔 Proceed with caution - need risk mitigation\n\n'
                '📋 Next Step: Conduct further assessment and get clarifications\n'
            )
        elif 'GO' in decision:
            decision_text = (
                '\n## 🎯 FINAL RECOMMENDATION\n\n'
                '### ✅ GO\n\n'
                '🎯 Strongly recommend pursuing this proposal\n\n'
                '📋 Next Step: Proceed with proposal development immediately\n'
            )
        else:
            decision_text = (
                f'\n## 🎯 FINAL RECOMMENDATION\n\n'
                f'### ⚠️ {decision}\n\n'
                f'🤔 Need further review\n'
            )

        # Remove the entire original FINAL RECOMMENDATION section (header through Final Decision line)
        report = re.sub(
            r'## FINAL RECOMMENDATION.*?Final Decision:.*?(?=\n\n|\Z)',
            '',
            report,
            flags=re.DOTALL | re.IGNORECASE
        )

        report += f'\n\n{decision_text}'

    # Clean up any leftover "Final Decision:" line that wasn't caught above
    report = re.sub(r'Final Decision:.*?(?=\n|$)', '', report)

    # ============================================
    # JUSTIFICATION
    # FIX: also remove the leading "##" so no empty heading remains
    # ============================================

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
            report += f'\n\n---\n\n## 📝 JUSTIFICATION\n\n{just_text}\n'

    # ============================================
    # FIX STATUS BADGES
    # ============================================

    report = report.replace('✅ FOUND', '<span class="status-found">✅ FOUND</span>')
    report = report.replace('❌ NOT FOUND', '<span class="status-not-found">❌ NOT FOUND</span>')
    report = report.replace('⚠️ ACTION REQUIRED', '<span class="status-action">⚠️ ACTION REQUIRED</span>')

    # ============================================
    # FIX DECISION COLUMN BADGES (GO / NO-GO / MAYBE)
    # Only match inside table cells i.e. surrounded by | ... |
    # NOTE: order matters — match NO-GO before GO so "GO" inside "NO-GO" isn't
    # partially replaced first.
    # ============================================

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

    # ============================================
    # STRIP LEADING WHITESPACE FROM EVERY LINE
    # (prevents markdown from treating indented HTML as a code block)
    # ============================================

    lines = report.split('\n')
    report = '\n'.join(line.lstrip() for line in lines)

    return report

# =====================================================
# MAIN APP
# =====================================================

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
            st.markdown("""
            <div class="success-box">
                ✅ Analysis Completed Successfully!
            </div>
            """, unsafe_allow_html=True)

            formatted_report = format_report(report)

            st.markdown("---")

            st.markdown("""
            <div class="card">
            """, unsafe_allow_html=True)

            st.markdown(formatted_report, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            # Only ONE Download Report button - at the bottom
            st.download_button(
                label="📥 Download Report",
                data=report,
                file_name="rfp_analysis_report.md",
                mime="text/markdown",
                use_container_width=True
            )
        else:
            st.error("❌ Analysis failed. Please try again.")

# =====================================================
# FOOTER
# =====================================================

st.markdown("---")

st.markdown(
    """
    <div style="background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 2rem; border-radius: 12px; margin-top: 1.5rem; border: 1px solid rgba(255, 255, 255, 0.05); text-align: center;">
        <div style="font-size: 1.2rem; font-weight: 600; color: #ffffff; letter-spacing: 1px; margin-bottom: 0.8rem;">◆ AI Proposal Capture System</div>
        <div style="width: 60px; height: 2px; background: linear-gradient(90deg, #667eea, #764ba2); margin: 0.8rem auto; border-radius: 10px;"></div>
        <div style="color: #8892b0; font-size: 0.9rem; margin: 0.5rem 0; padding: 0.2rem 0;">🔒 Powered by Google Gemini AI • Secure & Confidential</div>
        <div style="color: #8892b0; font-size: 0.9rem; margin: 0.5rem 0; padding: 0.2rem 0;">Developed by <span style="color: #00d4aa; font-weight: 600; font-size: 1rem;">Amna Pervez</span></div>
        <div style="width: 40px; height: 1px; background: rgba(255,255,255,0.05); margin: 0.3rem auto;"></div>
        <div style="color: #a8b2d1; font-size: 0.85rem; margin-top: 0.05rem; padding: 0.1rem 0; letter-spacing: 0.5px; font-weight: 500;">© 2026 AI Proposal Capture System • All Rights Reserved</div>
    </div>
    """,
    unsafe_allow_html=True
)