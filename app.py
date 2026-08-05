import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from modules.config import configure_gemini
from modules.history import load_history_from_disk
from modules.history_ui import render_history_tab
from modules.new_analysis_ui import render_new_tab
from modules.styles import apply_styles

st.set_page_config(
    page_title="AI Proposal Capture System",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)
apply_styles()

if configure_gemini() is None:
    st.error("❌ API Key not found! Please check your .env file.")
    st.stop()

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


if "history" not in st.session_state:
    st.session_state.history = load_history_from_disk()
if "current_result" not in st.session_state:
    st.session_state.current_result = None

top_tab_new, top_tab_history = st.tabs([
    "📤 New Analysis",
    f"🕒 History ({len(st.session_state.history)})",
])

with top_tab_new:
    st.markdown("""
    <h3 style="margin-bottom: 0.3rem;">📤 Upload RFP Documents</h3>
    <p style="color: #a6acd4; margin-top: 0; margin-bottom: 1rem; font-size: 0.92rem;">
        PDF only • Upload one or multiple RFPs • Your documents are analyzed securely
    </p>
    """, unsafe_allow_html=True)
    uploaded_files = st.file_uploader(
        "Drop your RFP PDFs here or click to browse",
        type=["pdf"], label_visibility="collapsed", accept_multiple_files=True,
    )

render_history_tab(top_tab_history)
render_new_tab(top_tab_new, uploaded_files)

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