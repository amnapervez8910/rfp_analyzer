<div align="center">

# 📄 AI Proposal Capture System

### Intelligent RFP Analysis & Capture Management Platform

**Extract • Analyze • Verify • Decide**

<p>
<img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"/>
<img src="https://img.shields.io/badge/Google-Gemini-4285F4?style=for-the-badge&logo=google&logoColor=white"/>
</p>

AI-powered platform that transforms lengthy Request for Proposal (RFP) documents into structured capture reports with deliverables, compliance analysis, evaluation criteria, verification, and a deterministic GO / MAYBE / NO-GO recommendation.

</div>

---

# ✨ Features

- 📄 Intelligent RFP PDF Analysis
- 🤖 Google Gemini AI Integration
- 📋 Deliverable Extraction with Page Citations
- 🎯 Evaluation Criteria Detection
- ✅ Automated Compliance Checklist
- 📊 Deterministic GO / MAYBE / NO-GO Decision
- 🔍 AI Verification Against Source Document
- 🔄 Addendum & Version Management
- 📅 Calendar (.ics) Generation
- 📑 Professional PDF Reports
- 📦 JSON Export
- 🗂 Analysis History

---

# 🤖 AI Architecture

| Model | Purpose |
|--------|---------|
| **`gemini-3.5-flash-lite`** | Deliverable Extraction (chunked scan) |
| **`gemini-3.6-flash`** | Evaluation Criteria |
| **`gemini-3.6-flash`** | Compliance Checklist |
| **`gemini-3.6-flash`** | Decision Narrative |
| **`gemini-3.6-flash`** | Report Verification |

All models run with **temperature = 0** to ensure deterministic and consistent outputs.

> The Evaluation, Compliance, Decision, and Verification steps all currently use the same `gemini-3.6-flash` model (kept as separate `fast` / `pro` slots internally for future flexibility) — only the Deliverables step uses the lighter `gemini-3.5-flash-lite` model.

---

# ⚙️ Processing Pipeline

```text
                              📥 Upload PDF(s)
                                    │
                                    ▼
                    🧾 Extract Text (page-tagged, per file)
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────┐
        │   Runs in PARALLEL — 3 AI agents                   │
        │                                                     │
        │   📋 Deliverables    ⚖️ Evaluation    ✅ Compliance  │
        │   (lite model,       Criteria         Checklist     │
        │    chunked scan)     (fast model)     (fast model)  │
        └───────────────────────────────────────────────────┘
                                    │
                                    ▼
              🧮 Python Decision Engine
              (team scores + GO/NO-GO — never decided by AI)
                                    │
                                    ▼
              ◆ Decision Narrative (AI explains the locked verdict)
                                    │
                                    ▼
              🔍 Verification Agent
              (independent AI pass — audits the finished report
               against the source PDF for errors/omissions)
                                    │
                                    ▼
              📤 Final Report → Export & Save to History
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────┐
        │   🔄 ADDENDUM UPLOADED LATER? (from History tab)    │
        │   → Full pipeline above re-runs on original +       │
        │     addendum text together (addendum takes          │
        │     precedence) → produces a new version (v2, v3…)  │
        │     + a "What Changed" summary                      │
        └───────────────────────────────────────────────────┘
```

---

# 📊 Decision Rules

**Team score formula** — each team's % is computed straight from its checklist Decision column, never from anything the AI writes as a number:

```
Team Score % = (GO × 1  +  MAYBE × 0.5  +  NO-GO × 0) / total items × 100
```

A MAYBE counts as half credit, not zero. The **Overall Score** is then the plain average of the four team scores (Finance, Legal, Operations, Technical).

**Final verdict**, applied in this exact priority order:

| Priority | Rule | Result |
|:--:|------------------------------|-----------|
| 1 | Mandatory deadline passed | ❌ NO-GO |
| 2 | Overall score below 60% | ❌ NO-GO |
| 3 | Score ≥ 80% & Finance = GO | ✅ GO |
| 4 | Otherwise | ⚠️ MAYBE |

> Deadline validation only trusts explicit calendar dates shared by 2+ mandatory deliverables — vague wording like "TBD" is ignored so it never guesses.

If the AI's own Justification text quotes a different score or decision word than what was actually computed, the app silently rewrites just that phrase to match — so the numbers shown can never contradict the written explanation.

---

# 🔄 Addendum Support

Upload amended RFPs to:

- Merge original and addendum
- Override outdated requirements
- Detect deadline changes
- Generate "What Changed" summary
- Create new document versions
- Recalculate final recommendation

---

# ♻️ Duplicate Upload Detection

Every uploaded set of PDFs is SHA-256 hashed. If you upload the **exact same files** again, the app recognizes the hash match and instantly shows the previously saved result instead of re-running the AI pipeline — no wasted API calls, no wait.

---

# 📂 Project Structure

```text
AI-Proposal-Capture-System/
│
├── app.py                    → Streamlit entry point — page setup, feature cards,
│                                 wires the New Analysis + History tabs together
├── api.py                    → FastAPI server — returns a saved (or freshly run)
│                                 analysis as JSON, by RFP ID
├── rfp_core.py                → Headless copy of the full analysis pipeline
│                                 (prompts + orchestration), used only by api.py
├── rfp_json_formatter.py      → Converts the raw markdown report into a clean,
│                                 structured JSON dict (deliverables/evaluation/
│                                 checklist/scoring/decision as separate keys)
├── requirements.txt           → Python dependencies
├── rfp_results.db             → SQLite DB shared between the app and the API
│
├── modules/
│   ├── analysis.py            → The REAL pipeline the app runs: deliverables,
│   │                              evaluation, checklist, scoring, decision,
│   │                              verification, addendum re-analysis, one-click fixes
│   ├── config.py               → Sets up Gemini + defines which model each step uses
│   ├── exports.py              → Builds the downloadable PDF, JSON, and .ics files;
│   │                              also reads/writes the shared SQLite DB
│   ├── history.py              → Hashes uploaded files (skips re-analysis on repeat
│   │                              uploads), generates RFP IDs, saves history to disk
│   ├── history_ui.py           → "History" tab UI — past analyses + addendum upload
│   ├── new_analysis_ui.py      → "New Analysis" tab UI — upload, run, results, downloads
│   ├── pdf_reader.py           → Extracts text from uploaded PDFs (with page markers)
│   ├── presentation.py         → Turns the raw markdown report into styled HTML
│   ├── scoring.py              → The actual scoring math + final GO/NO-GO/MAYBE logic
│   └── styles.py               → CSS only, no logic
│
└── README.md
```

---

# 🚀 Installation

```bash
git clone https://github.com/yourusername/AI-Proposal-Capture-System.git

cd AI-Proposal-Capture-System

python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file:

```env
GOOGLE_API_KEY=YOUR_API_KEY
```

> The model names (`gemini-3.6-flash`, `gemini-3.5-flash-lite`) are set directly in `modules/config.py` / `rfp_core.py`, not via environment variables — only the API key is read from `.env`.

Run the application:

```bash
streamlit run app.py
```

---

# 📤 Export Formats

- 📑 PDF Report
- 📦 JSON Report
- 📅 Calendar (.ics)
- 🗂 Analysis History

---

# 🛠 Tech Stack

- Python
- Streamlit
- FastAPI
- Google Gemini AI
- SQLite
- pypdf

---

<div align="center">

### Built by **Amna Pervez**

**AI Proposal Capture System • Google Gemini • Streamlit • FastAPI**

</div>
