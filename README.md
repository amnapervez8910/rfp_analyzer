# 📄 AI Proposal Capture System

A smart RFP analysis tool that uses Google Gemini AI to evaluate proposals and give GO/NO-GO decisions.

---

## 📦 Installation

```bash
pip install streamlit
pip install pypdf
pip install google-generativeai
```

---

## 🔑 Setup API Key


```env
GEMINI_KEY=your_google_gemini_api_key_here
```

Get your free API key from:
https://aistudio.google.com/app/apikey

---

## 🚀 Run the App

```bash
streamlit run app.py
```

---

## 📁 Project Files

```
📂 proposal-capture-system/
├── 📄 app.py          # Main application
├── 🎨 style.css       # Custom styles  
```

---

## ✨ Features

```
✅ Upload RFP PDF documents
✅ AI-powered analysis with Google Gemini
✅ Finance team checklist (Payment terms, Insurance, Stability)
✅ Legal team checklist (Eligibility, Data protection, Contracts)
✅ Operations team checklist (Forms, Deadlines, Documents)
✅ Technical team checklist (Scope, Requirements, Standards)
✅ Department-wise scoring system
✅ GO/NO-GO/MAYBE recommendations
✅ Export reports in Markdown format
```

---

## 🛠️ Tech Stack

```
- Streamlit - Web framework
- PyPDF - PDF text extraction
- Google Gemini AI - Document analysis
```

---

## 🎯 How It Works

```
1. Upload your RFP PDF
2. App reads and extracts text from all pages
3. Gemini AI analyzes against comprehensive checklist
4. Get detailed compliance report with scores
5. Receive final GO/NO-GO decision with justification
```

---

## 📊 Scoring System


---

### Final Decision Rules

| Condition | Decision |
|-----------|----------|
| Overall score ≥ 80% AND every Finance-team item = GO | ✅ **GO** |
| Any single flag exists (e.g., insurance over cap, non-standard payment terms) even with a high overall score | ⚠️ **MAYBE** |
| Overall score < 60% | ❌ **NO-GO** |

---

## 📄 License

All Rights Reserved

---

**Made by Amna Pervez**