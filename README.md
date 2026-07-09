# 📄 AI Proposal Capture System

A smart RFP (Request for Proposal) analysis tool powered by **Google Gemini AI**. Upload an RFP PDF and get back a full compliance breakdown, department-wise scoring, and a clear **GO / NO-GO / MAYBE** recommendation — in seconds.

---

## ✨ Features

- ✅ Upload RFP PDF document
- ✅ AI-powered analysis with Google Gemini
- ✅ **Finance team** checklist (Payment terms, Insurance, Financial stability, Profitability, Bid bond)
- ✅ **Legal team** checklist (Eligibility, Capability, Data protection, Contractual obligations, State registration, E-Verify)
- ✅ **Operations team** checklist (Forms, Deadlines, Document compliance, Signatory authority)
- ✅ **Technical team** checklist (Scope alignment, Requirements, Standards, Security, Integration)
- ✅ Department-wise scoring system
- ✅ Automatic GO / NO-GO / MAYBE recommendation
- ✅ Session history — review any previously analyzed RFP
- ✅ Export full reports in Markdown format

---

## 🛠️ Tech Stack

| Component | Purpose |
|---|---|
| [Streamlit](https://streamlit.io/) | Web app framework / UI |
| [PyPDF](https://pypi.org/project/pypdf/) | PDF text extraction |
| [Google Gemini AI](https://ai.google.dev/) | Document analysis engine |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Loads the API key from `.env` |

---

## 📁 Project Structure

```
proposal-capture-system/
├── app.py          # Main application (Streamlit + Gemini logic)
├── style.css       # Custom UI styling
├── .env            # Your API key (create this yourself, not committed)
```

---

## 📦 Installation

Install the required Python packages:

```bash
pip install streamlit pypdf google-generativeai python-dotenv
```

---

## 🔑 Setup: API Key

1. Get a free Gemini API key from **[Google AI Studio](https://aistudio.google.com/app/apikey)**.
2. In the project's root folder, create a file named **`.env`**.
3. Add your key like this:

```dotenv
GOOGLE_API_KEY=your_google_gemini_api_key_here
```

> The app reads this key automatically at startup via `python-dotenv`. If the key is missing, the app will show an error and stop.

---

## 🚀 Run the App

From the project folder, run:

```bash
streamlit run app.py
```

Then open the local URL Streamlit gives you (usually `http://localhost:8501`) in your browser.

---

## 🎯 How It Works

1. **Upload** your RFP PDF in the "New Analysis" tab.
2. The app **reads and extracts text** from every page of the document.
3. **Gemini AI analyzes** the RFP against a fixed, detailed checklist — covering Finance, Legal, Operations, and Technical criteria.
4. You get a **detailed compliance report** with a Status (Found / Not Found / Action Required) and a Decision (GO / NO-GO / MAYBE) for every checklist item.
5. Scores are calculated **directly from the Decision columns** (not trusted from the AI's own math), guaranteeing the numbers are always internally consistent.
6. You receive a **final recommendation** with a clear, specific justification — and can download the full report or revisit it later in **History**.

---

## 📊 Scoring System

Each checklist item is scored as:

| Decision | Points |
|---|---|
| ✅ GO | 1.0 |
| ⚠️ MAYBE | 0.5 |
| ❌ NO-GO | 0.0 |

Each team's score = `(sum of points) / (total items) × 100`
**Overall Score** = average of all four team scores (Finance, Legal, Operations, Technical).

### Final Decision Rules

| Condition | Decision |
|---|---|
| Overall score **≥ 80%** AND every Finance-team item = GO | ✅ **GO** |
| Any single flag exists (e.g. insurance over the cap, non-standard payment terms) — even with a high overall score | ⚠️ **MAYBE** |
| Overall score **< 60%** | ❌ **NO-GO** |

---

## 📄 License

All Rights Reserved.

---

**Made by Amna Pervez**
