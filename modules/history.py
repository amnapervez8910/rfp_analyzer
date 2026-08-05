import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).resolve().parent.parent / "rfp_history_store.json"

def compute_files_hash(uploaded_files):
    hashes = []
    for f in uploaded_files:
        f.seek(0)
        content = f.read()
        hashes.append(hashlib.sha256(content).hexdigest())
        f.seek(0)
    hashes.sort()
    combined = "".join(hashes)
    return hashlib.sha256(combined.encode()).hexdigest()


def generate_auto_rfp_id(uploaded_files, files_hash: str) -> str:
    """Builds a readable RFP ID from the first uploaded file's name,
    e.g. '364_rfp_PingOne_Advanced.pdf' -> '364_rfp_PingOne_Advanced-a1b2c3'.
    A short hash suffix (from the files' content hash) is appended so two
    different uploads that happen to share a filename don't collide."""
    if not uploaded_files:
        return files_hash[:10]

    base_name = Path(uploaded_files[0].name).stem  # filename without extension
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", base_name).strip("_")
    safe_name = safe_name[:40] if safe_name else "RFP"
    suffix = files_hash[:6]
    return f"{safe_name}-{suffix}"



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

def load_history_from_disk():
    """Load saved history entries from disk. Returns [] if file missing/corrupt."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            raw_list = json.load(f)
        history = []
        for item in raw_list:
            history.append({
                "filename": item.get("filename", "Unknown.pdf"),
                "timestamp": datetime.fromisoformat(item["timestamp"]),
                "raw_report": item.get("raw_report", ""),
                "formatted_report": item.get("formatted_report", ""),
                "files_hash": item.get("files_hash", ""),
                "rfp_id": item.get("rfp_id", "N/A"),
                "family_rfp_id": item.get("family_rfp_id", item.get("rfp_id", "N/A")),
                "document_text": item.get("document_text", ""),
                "version": item.get("version", 1),
                "amendment_of": item.get("amendment_of"),
                "amendment_sources": item.get("amendment_sources", []),
                "change_summary": item.get("change_summary"),
                "verification_notes": item.get("verification_notes"),
            })
        return history
    except Exception:
        return []


def save_history_to_disk(history):
    """Persist the full history list to disk as JSON."""
    try:
        serializable = []
        for item in history:
            serializable.append({
                "filename": item["filename"],
                "timestamp": item["timestamp"].isoformat(),
                "raw_report": item["raw_report"],
                "formatted_report": item["formatted_report"],
                "files_hash": item.get("files_hash", ""),
                "rfp_id": item.get("rfp_id", "N/A"),
                "family_rfp_id": item.get("family_rfp_id", item.get("rfp_id", "N/A")),
                "document_text": item.get("document_text", ""),
                "version": item.get("version", 1),
                "amendment_of": item.get("amendment_of"),
                "amendment_sources": item.get("amendment_sources", []),
                "change_summary": item.get("change_summary"),
                "verification_notes": item.get("verification_notes"),
            })
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False)
    except Exception:
        pass
