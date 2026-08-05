import streamlit as st

def load_css():
    """Return embedded CSS"""
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --bg-0: #06060f;
        --bg-1: #0b0b1a;
        --surface-1: #12132a;
        --surface-2: #181a35;
        --border-soft: rgba(255,255,255,0.07);
        --border-hover: rgba(124, 108, 255, 0.45);
        --text-primary: #f6f7fd;
        --text-secondary: #cdd2ef;
        --text-muted: #9aa0c4;
        --accent-1: #7c6cff;
        --accent-2: #b06cff;
        --accent-3: #35e6c8;
        --accent-warn: #ffc857;
        --accent-danger: #ff6b81;
        --accent-go: #2fe6b8;
        --grad-primary: linear-gradient(135deg, #7c6cff 0%, #b06cff 55%, #ff6cd6 100%);
        --grad-surface: linear-gradient(160deg, var(--surface-1) 0%, var(--surface-2) 100%);
        --shadow-soft: 0 10px 30px rgba(5, 5, 20, 0.55);
        --shadow-glow: 0 0 0 1px rgba(124,108,255,0.18), 0 12px 40px rgba(124,108,255,0.18);
    }

    * { font-family: 'Inter', -apple-system, sans-serif; }
    h1, h2, h3, h4, h5, h6, .gradient-header h1 { font-family: 'Sora', sans-serif; }

    .stApp {
        background:
            radial-gradient(circle at 12% 8%, rgba(124,108,255,0.14) 0%, transparent 42%),
            radial-gradient(circle at 88% 18%, rgba(53,230,200,0.10) 0%, transparent 40%),
            radial-gradient(circle at 50% 100%, rgba(176,108,255,0.08) 0%, transparent 45%),
            var(--bg-0);
    }
    .main { padding: 2rem; }

    .gradient-header {
        position: relative;
        background: linear-gradient(120deg, #10112b 0%, #171a3d 45%, #1c1442 100%);
        padding: 2.6rem 2.4rem;
        border-radius: 24px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: var(--shadow-soft);
        border: 1px solid var(--border-soft);
        overflow: hidden;
    }
    .gradient-header::before {
        content: '';
        position: absolute;
        inset: 0;
        background: var(--grad-primary);
        opacity: 0.08;
        pointer-events: none;
    }
    .gradient-header::after {
        content: '';
        position: absolute;
        top: -60%;
        right: -10%;
        width: 320px;
        height: 320px;
        background: radial-gradient(circle, rgba(124,108,255,0.35), transparent 70%);
        filter: blur(10px);
    }
    .gradient-header .eyebrow {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: var(--accent-3);
        background: rgba(53, 230, 200, 0.1);
        border: 1px solid rgba(53, 230, 200, 0.3);
        padding: 4px 12px;
        border-radius: 20px;
        margin-bottom: 0.9rem;
        position: relative;
        z-index: 1;
    }
    .gradient-header h1 {
        font-size: 2.6rem;
        font-weight: 800;
        margin: 0;
        color: #ffffff;
        letter-spacing: -0.5px;
        position: relative;
        z-index: 1;
    }
    .gradient-header p {
        font-size: 1.05rem;
        margin-top: 0.6rem;
        color: var(--text-secondary);
        position: relative;
        z-index: 1;
    }

    .stButton button {
        background: var(--grad-primary) !important;
        background-size: 200% 200% !important;
        color: white !important;
        border: none !important;
        padding: 0.85rem 2.5rem;
        border-radius: 14px;
        font-weight: 700;
        font-size: 1.05rem;
        letter-spacing: 0.3px;
        transition: all 0.25s ease;
        box-shadow: 0 8px 24px rgba(124, 108, 255, 0.35);
        width: 100%;
    }
    .stButton button:hover,
    .stButton button:focus,
    .stButton button:focus:not(:active) {
        background: var(--grad-primary) !important;
        background-size: 200% 200% !important;
        color: white !important;
        border: none !important;
        transform: translateY(-2px);
        box-shadow: 0 12px 32px rgba(124, 108, 255, 0.5);
        background-position: 100% 0;
    }
    .stButton button:hover p,
    .stButton button:focus p { color: white !important; }
    .stButton button:active { transform: translateY(0px); }

    .card {
        background: var(--grad-surface);
        padding: 2.2rem;
        border-radius: 20px;
        box-shadow: var(--shadow-soft);
        margin: 1rem 0;
        border: 1px solid var(--border-soft);
        border-top: 3px solid transparent;
        border-image: var(--grad-primary) 1;
    }

    .success-box {
        background: linear-gradient(120deg, rgba(47, 230, 184, 0.16), rgba(53, 230, 200, 0.08));
        padding: 1rem 1.6rem;
        border-radius: 14px;
        color: #d3fff2;
        font-weight: 600;
        margin: 1rem 0;
        box-shadow: 0 4px 18px rgba(47, 230, 184, 0.12);
        border: 1px solid rgba(47, 230, 184, 0.35);
    }

    .info-card {
        background: var(--grad-surface);
        padding: 1.7rem 1.4rem;
        border-radius: 16px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.35);
        margin: 0.5rem 0;
        border: 1px solid var(--border-soft);
        transition: all 0.28s cubic-bezier(.2,.8,.2,1);
        text-align: center;
        position: relative;
        overflow: hidden;
    }
    .info-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--accent-1), var(--accent-2));
    }
    .info-card:hover {
        transform: translateY(-6px);
        box-shadow: var(--shadow-glow);
        border-color: var(--border-hover);
    }
    .card-icon {
        font-size: 2.1rem;
        margin-bottom: 0.6rem;
        display: block;
        line-height: 1.2;
        filter: drop-shadow(0 4px 10px rgba(124,108,255,0.35));
    }
    .info-card h3 {
        color: #ffffff;
        font-size: 1.05rem;
        margin: 0.4rem 0;
        font-weight: 700;
        letter-spacing: 0.3px;
    }
    .info-card p {
        color: var(--text-muted) !important;
        font-size: 0.85rem;
        margin: 0;
    }

    .card-deliverables::before { background: linear-gradient(90deg, #7c6cff, #b06cff); }
    .card-evaluation::before { background: linear-gradient(90deg, #ff6cd6, #ff8f70); }
    .card-compliance::before { background: linear-gradient(90deg, #35e6c8, #4fa8ff); }
    .card-decision::before { background: linear-gradient(90deg, #2fe6b8, #35e6c8); }

    .status-found, .status-not-found, .status-action,
    .decision-go, .decision-no-go, .decision-maybe {
        display: inline-block;
        font-weight: 700;
        padding: 5px 16px;
        border-radius: 999px;
        font-size: 0.78rem;
        letter-spacing: 0.3px;
        min-width: 108px;
        text-align: center;
        box-shadow: 0 3px 10px rgba(0,0,0,0.25);
    }
    .status-found { background: linear-gradient(135deg, #2fe6b8, #1fb894); color: #06231c !important; }
    .status-not-found { background: linear-gradient(135deg, #ff8393, #ff6b81); color: #2b0810 !important; }
    .status-action { background: linear-gradient(135deg, #ffd166, #ffb84d); color: #2b1a00 !important; }
    .decision-go { background: linear-gradient(135deg, #2fe6b8, #1fb894); color: #06231c !important; min-width: 88px; }
    .decision-no-go { background: linear-gradient(135deg, #ff8393, #ff6b81); color: #2b0810 !important; min-width: 88px; }
    .decision-maybe { background: linear-gradient(135deg, #ffd166, #ffb84d); color: #2b1a00 !important; min-width: 88px; }

    /* Verification — clear, calm QA outcome card */
    .verification-card {
        position: relative; overflow: hidden; border-radius: 18px; padding: 1.35rem 1.45rem;
        margin: 0.45rem 0 1.1rem; display: flex; align-items: center; gap: 1rem;
        border: 1px solid rgba(47,230,184,.5); background: linear-gradient(135deg, rgba(27,174,134,.20), rgba(18,27,52,.78));
        box-shadow: 0 10px 30px rgba(0,0,0,.22);
    }
    .verification-card.review { border-color: rgba(255,200,87,.55); background: linear-gradient(135deg, rgba(168,119,18,.18), rgba(18,27,52,.78)); }
    .verification-card::after { content: ''; position:absolute; inset:0; pointer-events:none; background: radial-gradient(circle at 92% 15%, rgba(255,255,255,.14), transparent 25%); }
    .verification-check {
        position:relative; z-index:1; width:46px; height:46px; border-radius:50%; flex:0 0 46px;
        display:flex; align-items:center; justify-content:center; font-size:1.45rem; font-weight:800;
        color:#06231c; background:linear-gradient(135deg,#55f3ca,#1fb894); box-shadow:0 0 0 6px rgba(47,230,184,.10), 0 6px 18px rgba(47,230,184,.24);
    }
    .verification-card.review .verification-check { color:#332500; background:linear-gradient(135deg,#ffe28a,#e9ad35); box-shadow:0 0 0 6px rgba(255,200,87,.10),0 6px 18px rgba(255,200,87,.18); }
    .verification-copy { position:relative; z-index:1; min-width:0; }
    .verification-eyebrow { color:#9ff5dd; font-size:.70rem; line-height:1; letter-spacing:1.25px; text-transform:uppercase; font-weight:800; }
    .verification-card.review .verification-eyebrow { color:#ffdc82; }
    .verification-title { color:#fff; font-size:1.08rem; font-weight:800; margin:.34rem 0 .18rem; }
    .verification-subtitle { color:var(--text-muted); font-size:.84rem; line-height:1.45; margin:0; }
    .verification-confidence { position:relative; z-index:1; margin-left:auto; align-self:flex-start; color:#9ff5dd; border:1px solid rgba(47,230,184,.42); background:rgba(47,230,184,.10); padding:.32rem .58rem; border-radius:999px; font-size:.70rem; font-weight:800; white-space:nowrap; }
    .verification-card.review .verification-confidence { color:#ffdc82; border-color:rgba(255,200,87,.42); background:rgba(255,200,87,.10); }
    .verification-detail { border:1px solid var(--border-soft); background:rgba(15,16,39,.66); border-radius:12px; padding:.7rem 1rem; color:var(--text-muted); font-size:.86rem; margin-top:.6rem; }

    table {
        width: 100%;
        border-collapse: separate;
        border-spacing: 0;
        margin: 1.2rem 0;
        background: var(--surface-1);
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid var(--border-soft);
    }
    th {
        background: linear-gradient(135deg, #171935, #1d2044);
        color: var(--text-secondary);
        padding: 14px 18px;
        text-align: left;
        font-weight: 700;
        font-size: 0.78rem;
        border-bottom: 1px solid var(--border-soft);
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }
    td {
        padding: 14px 18px;
        border-bottom: 1px solid var(--border-soft);
        color: var(--text-secondary);
        font-size: 0.9rem;
        vertical-align: middle;
    }
    td:first-child { font-weight: 600; color: var(--text-primary); }
    tr:nth-child(even) { background: rgba(255, 255, 255, 0.015); }
    tr:hover { background: rgba(124, 108, 255, 0.08); }
    tr:last-child td { border-bottom: none; }

    .processing-status {
        background: var(--grad-surface);
        padding: 2.2rem;
        border-radius: 18px;
        text-align: center;
        border: 1px solid var(--border-soft);
        margin: 1rem 0;
        box-shadow: var(--shadow-soft);
    }
    .processing-status h3 { color: var(--text-secondary); font-weight: 500; margin: 0; }
    .processing-status .highlight {
        color: var(--accent-1);
        font-weight: 700;
        background: linear-gradient(90deg, var(--accent-1), var(--accent-2));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .processing-status .live-analysis {
        display: inline-block;
        margin-left: 0.35rem;
        font-weight: 700;
        letter-spacing: 0.15px;
        background: linear-gradient(90deg, #a78bfa 0%, #e879f9 52%, #fb7185 100%);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .step-indicator {
        display: flex;
        justify-content: center;
        gap: 1.2rem;
        margin: 1.3rem 0 0.4rem;
        flex-wrap: wrap;
    }
    .step {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: var(--text-muted);
        font-size: 0.88rem;
        font-weight: 500;
        padding: 0.55rem 1.3rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid var(--border-soft);
        transition: all 0.25s ease;
    }
    .step.active {
        color: #fff;
        border-color: var(--accent-1);
        background: linear-gradient(135deg, rgba(124,108,255,0.25), rgba(176,108,255,0.15));
        box-shadow: 0 0 18px rgba(124,108,255,0.25);
    }
    .step.done {
        color: #06231c;
        border-color: var(--accent-3);
        background: linear-gradient(135deg, #2fe6b8, #35e6c8);
        font-weight: 700;
    }
    .step-icon { font-size: 1.15rem; }

    /* ---- LIVE AGENT PIPELINE ---- */
    .agent-pipeline {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
        gap: 0.9rem;
        margin-top: 1.3rem;
    }
    .agent-card {
        background: rgba(255,255,255,0.025);
        border: 1px solid var(--border-soft);
        border-radius: 16px;
        padding: 1.1rem 1.1rem 1rem;
        text-align: left;
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    .agent-card.pending { opacity: 0.48; }
    .agent-card.active {
        border-color: var(--accent-1);
        background: linear-gradient(160deg, rgba(124,108,255,0.16), rgba(176,108,255,0.06));
        animation: agent-pulse 1.7s ease-in-out infinite;
    }
    .agent-card.done {
        border-color: rgba(47,230,184,0.5);
        background: linear-gradient(160deg, rgba(47,230,184,0.10), rgba(53,230,200,0.04));
        opacity: 1;
    }
    @keyframes agent-pulse {
        0%, 100% { box-shadow: 0 0 16px rgba(124,108,255,0.22); }
        50% { box-shadow: 0 0 30px rgba(124,108,255,0.45); }
    }
    .agent-card-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.65rem;
    }
    .agent-icon { font-size: 1.4rem; }
    .agent-status-pill {
        font-size: 0.62rem;
        font-weight: 700;
        letter-spacing: 0.6px;
        text-transform: uppercase;
        padding: 0.22rem 0.6rem;
        border-radius: 999px;
        color: var(--text-muted);
        background: rgba(255,255,255,0.05);
        white-space: nowrap;
    }
    .agent-status-pill.active {
        color: #fff;
        background: var(--grad-primary);
        box-shadow: 0 0 10px rgba(124,108,255,0.5);
    }
    .agent-status-pill.done {
        color: #06231c;
        background: linear-gradient(135deg, #2fe6b8, #35e6c8);
    }
    .agent-name {
        font-family: 'Sora', sans-serif;
        font-weight: 700;
        font-size: 0.92rem;
        color: var(--text-primary);
        margin-bottom: 0.25rem;
        line-height: 1.25;
    }
    .agent-desc {
        font-size: 0.76rem;
        color: var(--text-muted);
        margin-bottom: 0.75rem;
        min-height: 1.9rem;
        line-height: 1.35;
    }
    .agent-model-badge {
        display: inline-block;
        font-size: 0.66rem;
        font-weight: 700;
        padding: 0.22rem 0.6rem;
        border-radius: 8px;
        letter-spacing: 0.3px;
    }
    .agent-model-badge.badge-fast {
        color: #35e6c8;
        background: rgba(53,230,200,0.12);
        border: 1px solid rgba(53,230,200,0.3);
    }
    .agent-model-badge.badge-pro {
        color: #b06cff;
        background: rgba(176,108,255,0.14);
        border: 1px solid rgba(176,108,255,0.35);
    }
    @media (max-width: 640px) {
        .agent-pipeline { grid-template-columns: repeat(2, 1fr); gap: 0.6rem; }
        .agent-card { padding: 0.85rem; }
    }

    .stProgress > div > div > div > div { background: var(--grad-primary) !important; }
    .stSpinner > div { border-color: var(--accent-1) transparent var(--accent-2) transparent !important; }
    .stMarkdown { color: var(--text-secondary); }
    .stAlert { background: rgba(18, 19, 42, 0.85) !important; border-color: var(--border-soft) !important; color: var(--text-secondary) !important; border-radius: 12px !important; }
    .stAlert > div { color: var(--text-secondary) !important; }
    .stAlert svg { fill: var(--accent-1) !important; }

    .stFileUploader > div > div {
        background: rgba(18, 19, 42, 0.6) !important;
        border: 2px dashed rgba(124, 108, 255, 0.45) !important;
        border-radius: 18px !important;
        padding: 2.2rem !important;
        transition: all 0.25s ease;
    }
    .stFileUploader > div > div:hover {
        border-color: var(--accent-1) !important;
        background: rgba(124, 108, 255, 0.08) !important;
    }
    .stFileUploader label { color: var(--text-secondary) !important; }

    h1, h2, h3, h4, h5, h6 { color: var(--text-primary) !important; }
    p, li, span { color: var(--text-secondary); }
    hr { border-color: var(--border-soft) !important; margin: 1.8rem 0 !important; }

    ::-webkit-scrollbar { width: 10px; }
    ::-webkit-scrollbar-track { background: var(--bg-0); }
    ::-webkit-scrollbar-thumb { background: var(--grad-primary); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: linear-gradient(135deg, var(--accent-2), var(--accent-1)); }
    ::selection { background: var(--accent-1); color: white; }

    .stDownloadButton > button {
        background: var(--grad-surface) !important;
        color: var(--text-secondary) !important;
        border: 1px solid var(--border-soft) !important;
        border-radius: 14px !important;
        font-weight: 600 !important;
        transition: all 0.25s ease !important;
    }
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, rgba(124,108,255,0.18), rgba(176,108,255,0.12)) !important;
        border-color: var(--accent-1) !important;
        color: #fff !important;
        transform: translateY(-2px);
    }

    .section-banner {
        display: flex;
        align-items: center;
        gap: 0.7rem;
        padding: 1rem 1.4rem;
        border-radius: 14px;
        margin: 2.2rem 0 1.1rem 0;
        font-family: 'Sora', sans-serif;
        font-weight: 700;
        font-size: 1.15rem;
        color: #fff;
        box-shadow: 0 6px 18px rgba(0,0,0,0.28);
        border: 1px solid rgba(255,255,255,0.08);
    }
    .section-banner:first-child { margin-top: 0.4rem; }
    .section-banner .section-icon,
    .section-banner .section-title { color: #ffffff !important; }
    .section-icon { font-size: 1.4rem; }
    .section-title { letter-spacing: 0.2px; }

    /* Amendment experience — a distinct, calm amber treatment for versioned work. */
    .amendment-banner {
        position: relative;
        overflow: hidden;
        background: linear-gradient(118deg, rgba(255, 190, 82, 0.18), rgba(255, 139, 76, 0.08));
        border: 1px solid rgba(255, 201, 102, 0.38);
        border-left: 4px solid var(--accent-warn);
        border-radius: 16px;
        padding: 1.05rem 1.3rem;
        margin: 0.55rem 0 1rem;
        box-shadow: 0 10px 26px rgba(255, 184, 77, 0.10);
    }
    .amendment-banner::after {
        content: '';
        position: absolute;
        inset: 0 0 0 auto;
        width: 32%;
        background: radial-gradient(circle at right center, rgba(255, 209, 102, 0.17), transparent 68%);
        pointer-events: none;
    }
    .amendment-banner__eyebrow {
        position: relative;
        z-index: 1;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        color: #ffe0a1 !important;
        font-size: 0.74rem;
        font-weight: 800;
        letter-spacing: 1.25px;
        line-height: 1.45;
        text-transform: uppercase;
    }
    .amendment-tools {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        padding: 0.85rem 1rem;
        margin: 1.1rem 0 0.65rem;
        background: linear-gradient(120deg, rgba(255, 190, 82, 0.10), rgba(255, 139, 76, 0.035));
        border: 1px solid rgba(255, 201, 102, 0.24);
        border-radius: 12px;
        color: #ffe0a1 !important;
        font-family: 'Sora', sans-serif;
        font-size: 0.9rem;
        font-weight: 700;
    }

    .addendum-summary {
    margin-top: 0.5rem;
    padding: 1.1rem 1.35rem 1.3rem;
    background: linear-gradient(145deg, rgba(255,190,82,0.10), rgba(15,17,35,0.5));
    border: 1px solid rgba(255,201,102,0.22);
    border-radius: 16px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 26px rgba(0,0,0,0.15);
}
.addendum-summary h1, .addendum-summary h2, .addendum-summary h3 {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    margin: 1rem 0 0.6rem !important;
    padding: 0.65rem 0.85rem;
    color: #ffe8c2 !important;
    font-family: 'Sora', sans-serif !important;
    font-size: 0.95rem !important;
    font-weight: 750 !important;
    background: linear-gradient(90deg, rgba(255,190,82,0.16), rgba(255,139,76,0.05));
    border: 1px solid rgba(255,201,102,0.22);
    border-left: 3px solid var(--accent-warn);
    border-radius: 10px;
}
.addendum-summary h1:first-child,
.addendum-summary h2:first-child,
.addendum-summary h3:first-child { margin-top: 0.15rem !important; }
.addendum-summary h1::before,
.addendum-summary h2::before,
.addendum-summary h3::before { content: '✦'; color: #ffd58a; font-size: 0.75rem; }
.addendum-summary p { color: #f3e6d0 !important; margin: 0.5rem 0 0.85rem; }
.addendum-summary ul,
.addendum-summary ol {
    padding: 0.75rem 1rem 0.75rem 1.9rem;
    background: rgba(8, 11, 27, 0.25);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 10px;
    margin: 0.5rem 0 0.9rem;
}
.addendum-summary ul ul, .addendum-summary ol ul { margin: 0.3rem 0; background: transparent; border: none; padding-left: 1.3rem; }
.addendum-summary li { margin: 0.32rem 0; color: #f3e6d0 !important; line-height: 1.6; }
.addendum-summary li::marker { color: #ffbf5e; }
.addendum-summary li strong, .addendum-summary strong { color: #ffe0a1 !important; }
    .amendment-tools span { color: #ffe0a1 !important; }

    .sec-deliverables { background: linear-gradient(120deg, rgba(124,108,255,0.28), rgba(124,108,255,0.08)); border-left: 4px solid #7c6cff; }
    .sec-evaluation {
        background: linear-gradient(120deg, rgba(255,108,214,0.30), rgba(255,108,214,0.07));
        border-left: 4px solid #ff6cd6;
        box-shadow: 0 8px 24px rgba(255, 108, 214, 0.16);
    }

    /* Evaluation Criteria — clearer scanning, better dense-table handling. */
    .evaluation-content {
        margin-top: 0.4rem;
        padding: 0.15rem 0.15rem 0.4rem;
    }
    .evaluation-content p,
    .evaluation-content li { line-height: 1.7; }
    .evaluation-content ul,
    .evaluation-content ol { padding-left: 1.35rem; margin: 0.55rem 0 1rem; }
    .evaluation-content table {
        display: block;
        max-width: 100%;
        overflow-x: auto;
        white-space: normal;
        box-shadow: 0 10px 24px rgba(255, 108, 214, 0.08);
        border-color: rgba(255, 108, 214, 0.22);
    }
    .evaluation-content th {
        background: linear-gradient(135deg, #30203c, #231b37);
        color: #ffe7f7;
    }
    .evaluation-content td { vertical-align: top; line-height: 1.55; }
    .evaluation-content tr:hover { background: rgba(255, 108, 214, 0.075); }

    /* The evaluation body is intentionally a full visual panel, not plain text. */
    div.evaluation-content {
        background: linear-gradient(145deg, rgba(42, 24, 57, 0.42), rgba(15, 17, 35, 0.48));
        border: 1px solid rgba(255, 108, 214, 0.20);
        border-top: 0;
        border-radius: 0 0 18px 18px;
        padding: 1.15rem 1.35rem 1.35rem;
        margin-top: -1.1rem;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.035), 0 14px 30px rgba(0,0,0,0.16);
    }
    div.evaluation-content h1,
    div.evaluation-content h2,
    div.evaluation-content h3,
    div.evaluation-content h4 {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        margin: 1.2rem 0 0.65rem !important;
        padding: 0.72rem 0.9rem;
        color: #ffe8f8 !important;
        font-family: 'Sora', sans-serif !important;
        font-size: 1rem !important;
        font-weight: 750 !important;
        line-height: 1.35 !important;
        background: linear-gradient(90deg, rgba(255, 108, 214, 0.16), rgba(176, 108, 255, 0.055));
        border: 1px solid rgba(255, 108, 214, 0.20);
        border-left: 3px solid #ff6cd6;
        border-radius: 10px;
        letter-spacing: 0.05px;
    }
    div.evaluation-content h1:first-child,
    div.evaluation-content h2:first-child,
    div.evaluation-content h3:first-child,
    div.evaluation-content h4:first-child { margin-top: 0.25rem !important; }
    div.evaluation-content h1::before,
    div.evaluation-content h2::before,
    div.evaluation-content h3::before,
    div.evaluation-content h4::before { content: '✦'; color: #ff8de0; font-size: 0.8rem; }
    div.evaluation-content p {
        margin: 0.55rem 0 0.95rem;
        color: #e5e7ff !important;
        font-size: 0.93rem;
    }
    div.evaluation-content ul,
    div.evaluation-content ol {
        padding: 0.85rem 1rem 0.85rem 2.1rem;
        background: rgba(8, 11, 27, 0.28);
        border: 1px solid rgba(255,255,255,0.055);
        border-radius: 10px;
    }
    div.evaluation-content li {
        padding-left: 0.28rem;
        margin: 0.38rem 0;
        color: #e5e7ff !important;
    }
    div.evaluation-content li::marker { color: #ff83db; }

    /* Evaluation detail hierarchy: quick scan at the top, evidence-led cards below. */
    div.evaluation-content h2 {
        margin: 1.5rem 0 0.7rem !important;
        padding: 0.8rem 1rem;
        color: #fff0fb !important;
        font-size: 1.05rem !important;
        background: linear-gradient(90deg, rgba(255,108,214,0.22), rgba(124,108,255,0.08));
        border: 1px solid rgba(255,108,214,0.30);
        border-left: 4px solid #ff6cd6;
        border-radius: 12px;
        box-shadow: 0 8px 18px rgba(255,108,214,0.08);
    }
    div.evaluation-content h3 {
        margin: 1rem 0 0 !important;
        padding: 0.72rem 0.95rem;
        color: #ffe9f8 !important;
        font-size: 0.95rem !important;
        background: rgba(255,255,255,0.035);
        border: 1px solid rgba(255,108,214,0.18);
        border-bottom: 0;
        border-left: 3px solid #b06cff;
        border-radius: 11px 11px 0 0;
    }
    div.evaluation-content h3 + ul {
        margin: 0 !important;
        padding: 0.75rem 1rem 0.85rem 2.1rem;
        background: linear-gradient(135deg, rgba(10,12,30,0.58), rgba(42,24,57,0.30));
        border: 1px solid rgba(255,108,214,0.18);
        border-top: 0;
        border-radius: 0 0 11px 11px;
        box-shadow: 0 7px 18px rgba(0,0,0,0.16);
    }
    div.evaluation-content strong {
        color: #ffb4e9 !important;
        font-weight: 700;
    }
    div.evaluation-content h2 + ul {
        background: linear-gradient(135deg, rgba(124,108,255,0.10), rgba(255,108,214,0.06));
        border-color: rgba(176,108,255,0.20);
    }
    .sec-checklist    { background: linear-gradient(120deg, rgba(53,230,200,0.22), rgba(53,230,200,0.06)); border-left: 4px solid #35e6c8; }
    .sec-scoring      { background: linear-gradient(120deg, rgba(176,108,255,0.24), rgba(176,108,255,0.06)); border-left: 4px solid #b06cff; }
    .sec-decision     { background: linear-gradient(120deg, rgba(47,230,184,0.22), rgba(255,209,102,0.06)); border-left: 4px solid #2fe6b8; }

    .team-banner {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.65rem 1.1rem;
        border-radius: 10px;
        margin: 1.6rem 0 0.7rem 0;
        font-weight: 700;
        font-size: 0.95rem;
        letter-spacing: 0.4px;
        text-transform: uppercase;
        color: var(--text-primary);
        background: rgba(255,255,255,0.03);
        border: 1px solid var(--border-soft);
        width: fit-content;
    }
    .team-icon { font-size: 1.05rem; }
    .team-finance { border-color: rgba(124,108,255,0.4); }
    .team-legal   { border-color: rgba(255,108,214,0.4); }
    .team-ops     { border-color: rgba(53,230,200,0.4); }
    .team-tech    { border-color: rgba(176,108,255,0.4); }

    .verdict-card {
        border-radius: 22px;
        padding: 2.2rem 2rem;
        margin: 1.5rem 0;
        text-align: center;
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(255,255,255,0.08);
        box-shadow: 0 14px 40px rgba(0,0,0,0.35);
    }
    .verdict-icon { font-size: 3rem; display: block; margin-bottom: 0.5rem; }
    .verdict-label { font-family: 'Sora', sans-serif; font-size: 1.8rem; font-weight: 800; letter-spacing: 0.5px; margin-bottom: 0.4rem; }
    .verdict-msg { font-size: 1rem; color: var(--text-secondary); margin-bottom: 0.3rem; }
    .verdict-next { font-size: 0.9rem; color: var(--text-muted); margin-top: 0.8rem; padding-top: 0.8rem; border-top: 1px solid rgba(255,255,255,0.08); }

    .verdict-go   { background: linear-gradient(160deg, rgba(47,230,184,0.16), rgba(18,19,42,0.9)); }
    .verdict-go .verdict-label { color: #2fe6b8; }
    .verdict-maybe { background: linear-gradient(160deg, rgba(255,209,102,0.16), rgba(18,19,42,0.9)); }
    .verdict-maybe .verdict-label { color: #ffd166; }
    .verdict-nogo { background: linear-gradient(160deg, rgba(255,107,129,0.16), rgba(18,19,42,0.9)); }
    .verdict-nogo .verdict-label { color: #ff6b81; }

    .justification-card {
        background: var(--grad-surface);
        border-left: 4px solid var(--accent-1);
        border-radius: 14px;
        padding: 1.4rem 1.6rem;
        margin: 1rem 0;
        color: var(--text-secondary);
        font-size: 0.95rem;
        line-height: 1.65;
    }
    .justification-card .jc-title {
        font-weight: 700;
        color: var(--text-primary);
        display: block;
        margin-bottom: 0.5rem;
        font-family: 'Sora', sans-serif;
    }

    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
        background: rgba(255,255,255,0.02);
        padding: 0.4rem;
        border-radius: 16px;
        border: 1px solid var(--border-soft);
    }
    .stTabs [data-baseweb="tab"] {
        height: auto;
        padding: 0.7rem 1.4rem;
        border-radius: 12px;
        background: transparent;
        color: var(--text-muted);
        font-weight: 600;
        font-size: 0.95rem;
        transition: all 0.22s ease;
        border: none;
    }
    .stTabs [data-baseweb="tab"]:hover { color: var(--text-primary); background: rgba(124,108,255,0.1); }
    .stTabs [aria-selected="true"] {
        background: var(--grad-primary) !important;
        color: #fff !important;
        box-shadow: 0 6px 18px rgba(124,108,255,0.35);
    }
    .stTabs [data-baseweb="tab-highlight"] { display: none; }
    .stTabs [data-baseweb="tab-border"] { display: none; }
    .stTabs [data-testid="stMarkdownContainer"] p { margin-bottom: 0; }

    /* Only the History file expander and its "What Changed" expander. */
    div[data-testid="stExpander"] > details:has(.history-hover-marker) > summary,
    div[data-testid="stExpander"] > details:has(.addendum-hover-marker) > summary,
    div[data-testid="stExpander"] > details:has(.upload-addendum-hover-marker) > summary {
        background: var(--surface-1) !important;
        color: var(--text-secondary) !important;
        border: 1px solid var(--border-soft) !important;
    }
    div[data-testid="stExpander"] > details:has(.history-hover-marker) > summary:hover,
    div[data-testid="stExpander"] > details:has(.addendum-hover-marker) > summary:hover,
    div[data-testid="stExpander"] > details:has(.upload-addendum-hover-marker) > summary:hover {
        background: linear-gradient(135deg, rgba(124,108,255,0.22), rgba(176,108,255,0.14)) !important;
        color: #ffffff !important;
        border-color: var(--accent-1) !important;
    }
    div[data-testid="stExpander"] > details:has(.history-hover-marker) > summary:hover *,
    div[data-testid="stExpander"] > details:has(.addendum-hover-marker) > summary:hover *,
    div[data-testid="stExpander"] > details:has(.upload-addendum-hover-marker) > summary:hover * {
        color: #ffffff !important;
    }

    /* ---- Two-level Deliverables (Numbered Outline: 1, 1.1, 1.2 / 2, 2.1 ...) ---- */
    .deliverable-groups {
        margin: 1rem 0 1.8rem 0;
        background: var(--surface-1);
        border-radius: 14px;
        overflow: hidden;
        border: 1px solid var(--border-soft);
        box-shadow: var(--shadow-soft);
    }
    .deliv-group { border-bottom: 1px solid var(--border-soft); }
    .deliv-group:last-child { border-bottom: none; }
    .deliv-group > summary {
        list-style: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 12px 18px;
        font-family: 'Sora', sans-serif;
        font-weight: 800;
        font-size: 1.0rem;
        color: #ffffff !important;
        letter-spacing: 0.2px;
        user-select: none;
    }
    .deliv-group > summary::-webkit-details-marker { display: none; }
    .deliv-toggle-icon {
        font-size: 0.68rem;
        display: inline-block;
        width: 12px;
        transition: transform 0.2s ease;
        opacity: 0.85;
    }
    .deliv-group[open] > summary .deliv-toggle-icon { transform: rotate(90deg); }
    .deliv-group .dp-icon { margin-right: 0.2rem; }

    /* Cycling category color palette so each parent category is visually distinct */
    .deliv-group-c0 > summary { background: linear-gradient(120deg, rgba(124,108,255,0.28), rgba(124,108,255,0.10)); }
    .deliv-group-c1 > summary { background: linear-gradient(120deg, rgba(255,108,214,0.26), rgba(255,108,214,0.08)); }
    .deliv-group-c2 > summary { background: linear-gradient(120deg, rgba(53,230,200,0.24), rgba(53,230,200,0.08)); }
    .deliv-group-c3 > summary { background: linear-gradient(120deg, rgba(176,108,255,0.26), rgba(176,108,255,0.08)); }
    .deliv-group-c4 > summary { background: linear-gradient(120deg, rgba(255,200,87,0.22), rgba(255,200,87,0.07)); }

    .deliverable-table {
        width: 100%;
        table-layout: fixed;
        border-collapse: separate;
        border-spacing: 0;
        background: var(--surface-1);
    }
    .deliverable-table td {
        padding: 14px 16px;
        border-bottom: 1px solid var(--border-soft);
        color: var(--text-secondary);
        font-size: 0.88rem;
        line-height: 1.5;
        vertical-align: top;
        word-wrap: break-word;
        overflow-wrap: break-word;
        white-space: normal;
    }
    .deliverable-table tr:last-child td { border-bottom: none; }
    .deliverable-table th {
        padding: 12px 16px;
        text-align: left;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.3px;
        text-transform: uppercase;
        color: var(--text-muted);
        background: rgba(255,255,255,0.03);
        border-bottom: 1px solid var(--border-soft);
    }

    .deliv-child-c0:hover td { background: rgba(124, 108, 255, 0.07); }
    .deliv-child-c1:hover td { background: rgba(255, 108, 214, 0.06); }
    .deliv-child-c2:hover td { background: rgba(53, 230, 200, 0.06); }
    .deliv-child-c3:hover td { background: rgba(176, 108, 255, 0.06); }
    .deliv-child-c4:hover td { background: rgba(255, 200, 87, 0.06); }

    .deliv-num {
        width: 60px;
        font-weight: 700;
        color: var(--text-muted);
        white-space: nowrap;
        padding-left: 16px;
        padding-right: 6px;
    }
    .deliv-child-row .deliv-num { padding-left: 1.6rem; white-space: nowrap; }
    .deliv-child-c0 .deliv-num { color: var(--accent-1); }
    .deliv-child-c1 .deliv-num { color: #ff6cd6; }
    .deliv-child-c2 .deliv-num { color: var(--accent-3); }
    .deliv-child-c3 .deliv-num { color: var(--accent-2); }
    .deliv-child-c4 .deliv-num { color: var(--accent-warn); }

    .deliv-name {
        width: 16%;
        font-weight: 700;
        color: var(--text-primary);
    }
    .deliv-desc { width: auto; }
    .deliv-doc {
        width: 18%;
        font-weight: 600;
        color: var(--accent-3);
        font-size: 0.78rem;
        line-height: 1.4;
    }
    .deliv-doc .doc-name { color: var(--accent-1); }
    .deliv-doc .sec-name { color: var(--accent-warn); font-size: 0.7rem; }
    .deliv-doc .sec-arrow { color: var(--text-muted); margin: 0 3px; font-size: 0.65rem; }
    .deliv-deadline-cell {
        width: 170px;
        text-align: left;
    }
    .deliverable-deadline {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        color: #ffd8a8;
        background: rgba(255, 200, 87, 0.12);
        border: 1px solid rgba(255, 200, 87, 0.3);
        padding: 6px 12px;
        border-radius: 10px;
        line-height: 1.5;
        white-space: normal;
        word-break: break-word;
    }
    .deliverable-deadline.deadline-conditional {
        color: #ffb3c8;
        background: rgba(255, 107, 129, 0.14);
        border: 1px solid rgba(255, 107, 129, 0.35);
    }
    .deliverable-deadline.deadline-overdue {
        color: #ffd0d8;
        background: rgba(255, 82, 112, 0.20);
        border: 1px solid rgba(255, 82, 112, 0.55);
    }
    .requirement-label {
        display: inline-block;
        margin-top: 6px;
        padding: 3px 8px;
        border-radius: 999px;
        font-size: 0.64rem;
        line-height: 1.2;
        font-weight: 800;
        letter-spacing: 0.4px;
        text-transform: uppercase;
    }
    .requirement-mandatory { color: #ffcf80; background: rgba(255, 184, 76, 0.15); border: 1px solid rgba(255, 184, 76, 0.38); }
    .requirement-optional { color: #8ee8dc; background: rgba(53, 230, 200, 0.11); border: 1px solid rgba(53, 230, 200, 0.30); }
    .deliverable-page {
        display: inline-block;
        margin-top: 5px;
        font-size: 0.68rem;
        font-weight: 700;
        color: var(--text-muted);
        background: rgba(124, 108, 255, 0.10);
        border: 1px solid rgba(124, 108, 255, 0.25);
        padding: 3px 10px;
        border-radius: 10px;
        white-space: nowrap;
    }

    .deliv-evidence-row td {
        padding-top: 0 !important;
        padding-bottom: 12px !important;
        border-bottom: 1px solid var(--border-soft);
    }
    .deliverable-evidence {
        display: block;
        margin-top: 8px;
        background: rgba(53, 230, 200, 0.06);
        border-left: 3px solid var(--accent-3);
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 0.8rem;
        line-height: 1.5;
        color: #b8f0e4;
    }
    .deliverable-evidence .ev-label {
        font-weight: 700;
        color: var(--accent-3);
        text-transform: uppercase;
        font-size: 0.68rem;
        letter-spacing: 0.6px;
        margin-right: 6px;
    }
    .deliverable-evidence .ev-text {
        color: #cdd2ef;
        font-style: italic;
    }

    @media (max-width: 768px) {
        .gradient-header { padding: 1.8rem 1.4rem; }
        .gradient-header h1 { font-size: 1.7rem; }
        .upload-box { padding: 1.5rem; }
        .info-card { padding: 1rem; }
        .card-icon { font-size: 1.8rem; }
        .step-indicator { gap: 0.5rem; }
        .step { font-size: 0.72rem; padding: 0.3rem 0.8rem; }

        .deliv-group > summary { flex-wrap: wrap; }
        .deliverable-table, .deliverable-table tbody { display: block; width: 100%; }
        .deliverable-table tr { display: block; width: 100%; }
        .deliv-child-row { display: block; padding: 10px 0; border-bottom: 1px solid var(--border-soft); }
        .deliv-child-row td {
            display: block;
            width: 100% !important;
            border-bottom: none;
            padding: 3px 16px;
        }
        .deliv-num { padding-left: 16px !important; font-size: 0.8rem; }
        .deliv-name { padding-top: 6px !important; }
        .deliv-doc { padding-top: 6px !important; }
        .deliv-deadline-cell { padding-top: 6px !important; }
        .deliv-evidence-row td { padding: 3px 16px !important; }
    }
    </style>
    """


def apply_styles():
    st.markdown(load_css(), unsafe_allow_html=True)
