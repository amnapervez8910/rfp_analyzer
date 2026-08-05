# 📄 AI Proposal Capture System

An AI-powered RFP analysis application built with **Streamlit** and **Google Gemini AI**. It helps teams analyze one or multiple Request for Proposal (RFP) documents, extract important requirements, evaluate departmental compliance, and make informed **GO / NO-GO / MAYBE** decisions.

---

## ✨ Features

- 📤 Upload one or multiple RFP documents in PDF format
- 🤖 Analyze RFP content using Google Gemini AI
- 📋 Extract key deliverables and submission requirements
- ⚖️ Identify evaluation criteria and scoring details
- 💰 Generate a Finance team compliance checklist
- ⚖️ Generate a Legal team compliance checklist
- ⚙️ Generate an Operations team compliance checklist
- 💻 Generate a Technical team compliance checklist
- 📊 Provide department-wise compliance scores
- 🚦 Generate a GO / NO-GO / MAYBE recommendation
- 🕒 Save and review previous analyses through the History tab
- 📝 Export complete analysis reports in Markdown format
- 🎨 Provide a clean, responsive, and user-friendly interface

---

## 🛠️ Tech Stack

| Technology | Purpose |
|---|---|
| [Python](https://www.python.org/) | Core programming language |
| [Streamlit](https://streamlit.io/) | Web application framework and user interface |
| [Google Gemini AI](https://ai.google.dev/) | AI-powered RFP analysis and recommendations |
| [PyPDF](https://pypi.org/project/pypdf/) | PDF text extraction |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Secure environment variable management |
| HTML & CSS | Custom styling and visual components |

---

## 📦 Installation

Clone the repository and install the required packages:

```bash
git clone https://github.com/amnapervez8910/rfp_analyzer.git
cd rfp_analyzer
pip install streamlit pypdf google-generativeai python-dotenv
```

---

## 🔑 Gemini API Key Setup

1. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Create a `.env` file in the main project folder.
3. Add your API key:

```env
GOOGLE_API_KEY=your_google_gemini_api_key_here
```

If the API key is missing, the application will display an error message and stop automatically.

---

## 🚀 Run the Application

Run the following command from the project folder:

```bash
streamlit run app.py
```

The application will usually open automatically in your browser. If it does not, visit:

```text
http://localhost:8501
```

---

## 📖 How to Use

1. Open the application in your browser.
2. Go to the **New Analysis** tab.
3. Upload one or multiple RFP documents in PDF format.
4. Start the AI analysis and wait for the documents to be processed.
5. Review the extracted deliverables, evaluation criteria, departmental checklists, scores, and final recommendation.
6. Open the **History** tab to review previously saved analyses.

---

## 🚦 Decision Intelligence

The system reviews the extracted requirements, compliance status, departmental scores, risks, and missing information to provide one of the following recommendations:

- **GO** — The opportunity is suitable and the major requirements can be fulfilled.
- **NO-GO** — Critical requirements, risks, or compliance issues make the opportunity unsuitable.
- **MAYBE** — The opportunity requires further review because some information or approvals are still needed.

---

## 🔒 Security and Privacy

- The Gemini API key is loaded securely from environment variables.
- RFP documents may contain confidential business information, so they should be handled carefully.
- Do not expose API credentials or upload the `.env` file to a public repository.
- Review AI-generated results before making a final business or bidding decision.

---


