import streamlit as st
from datetime import datetime

from .analysis import analyze_rfp_amendment, build_amendment_document_text
from .exports import generate_deliverables_ics, generate_json_report, generate_pdf_report, render_addendum_summary, save_result_to_shared_db
from .history import compute_files_hash, extract_quick_summary, save_history_to_disk
from .pdf_reader import extract_text_with_context
from .presentation import format_report


def render_history_tab(top_tab_history):
    with top_tab_history:
        if not st.session_state.history:
            st.info("📭 No previous RFPs analyzed yet in this session. Once you run an analysis, it'll show up here.")
        else:
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown("Every RFP batch you've analyzed in this session, most recent first.")
            with col_b:
                if st.button("🗑️ Clear History", use_container_width=True, key="clear_history_btn"):
                    st.session_state.history = []
                    st.session_state.current_result = None
                    save_history_to_disk([])
                    st.rerun()
    
            for idx, entry in enumerate(st.session_state.history):
                score_text, decision_label, decision_icon = extract_quick_summary(entry["raw_report"])
                version_badge = f" • 🔄 Addendum v{entry.get('version', 1)}" if entry.get("version", 1) > 1 else ""
                label = (
                    f"📄 {entry['filename']} • "
                    f"{entry['timestamp'].strftime('%b %d, %Y %I:%M %p')} • "
                    f"Score: {score_text} • {decision_icon} {decision_label}{version_badge}"
                )
                with st.expander(label, expanded=False):
                    entry_rfp_id = entry.get("rfp_id", "N/A")
                    col_id, col_del = st.columns([5, 1])
                    with col_id:
                        st.markdown(f"""
                        <div class="history-hover-marker" style="background: var(--grad-surface); border: 1px solid var(--border-soft);
                                    border-left: 4px solid var(--accent-3); border-radius: 12px;
                                    padding: 0.7rem 1.1rem; margin-bottom: 1rem;">
                            <span style="font-size: 0.7rem; letter-spacing: 1.5px; text-transform: uppercase;
                                         color: var(--text-muted); font-weight: 700;">RFP ID&nbsp;</span>
                            <span style="font-family: 'Sora', sans-serif; font-weight: 700; color: var(--accent-3);">
                                {entry_rfp_id}
                            </span>
                        </div>
                        """, unsafe_allow_html=True)
                    with col_del:
                        if st.button(
                            "🗑️ Delete",
                            key=f"delete_entry_{idx}_{entry_rfp_id}",
                            use_container_width=True,
                            help="Delete only this analysis, keep the rest of History",
                        ):
                            if st.session_state.current_result and st.session_state.current_result.get("rfp_id") == entry_rfp_id:
                                st.session_state.current_result = None
                            st.session_state.history.pop(idx)
                            save_history_to_disk(st.session_state.history)
                            st.rerun()
    
                    if entry.get("change_summary"):
                        with st.expander("📝 What Changed in This Addendum", expanded=False):
                            st.markdown('<span class="addendum-hover-marker"></span>', unsafe_allow_html=True)
                            st.markdown(render_addendum_summary(entry["change_summary"]), unsafe_allow_html=True)
    
                    st.markdown(entry["formatted_report"], unsafe_allow_html=True)
    
                    # ---- Addendum upload: add new/updated documents for this RFP ----
                    st.markdown("---")
                    st.markdown("""
                    <div class="amendment-tools">
                        <span>✦</span><span>Addendum workspace</span>
                    </div>
                    """, unsafe_allow_html=True)
                    with st.expander("➕ Upload Addendum / Additional Documents", expanded=False):
                        st.markdown('<span class="upload-addendum-hover-marker"></span>', unsafe_allow_html=True)
                        st.caption(
                            "Upload documents that update or add to this RFP (e.g. addenda, revised "
                            "scope, updated terms). The system will re-run the full analysis using the "
                            "original documents together with these, and show exactly what changed."
                        )
                        amendment_files = st.file_uploader(
                            "Addendum PDF(s) for this RFP",
                            type=["pdf"],
                            accept_multiple_files=True,
                            key=f"amendment_uploader_{idx}",
                        )
                        if amendment_files and st.button(
                            "🔄 Re-analyze with Addendum Documents",
                            use_container_width=True,
                            key=f"amendment_button_{idx}",
                        ):
                            if not entry.get("document_text"):
                                st.error(
                                    "❌ This entry doesn't have its original document text saved "
                                    "(it was analyzed before addendum support was added), so it "
                                    "can't be amended. Please re-run a fresh analysis instead."
                                )
                            else:
                                with st.spinner("📖 Reading addendum PDF(s)..."):
                                    amendment_document_text = extract_text_with_context(amendment_files)
    
                                new_report, change_summary, verification_notes = analyze_rfp_amendment(
                                    entry["document_text"],
                                    amendment_document_text,
                                    [f.name for f in amendment_files],
                                    entry["raw_report"],
                                )
    
                                if new_report and "Analysis failed" not in new_report:
                                    new_formatted_report = format_report(new_report)
                                    new_version = entry.get("version", 1) + 1
                                    family_rfp_id = entry.get("family_rfp_id", entry_rfp_id)
                                    new_rfp_id = f"{family_rfp_id}-v{new_version}"
                                    new_combined_filename = ", ".join(
                                        [entry["filename"]] + [f.name for f in amendment_files]
                                    )
                                    new_document_text = build_amendment_document_text(
                                        entry["document_text"],
                                        amendment_document_text,
                                        [f.name for f in amendment_files],
                                    )
    
                                    new_record = {
                                        "filename": new_combined_filename,
                                        "timestamp": datetime.now(),
                                        "raw_report": new_report,
                                        "formatted_report": new_formatted_report,
                                        "files_hash": compute_files_hash(amendment_files),
                                        "rfp_id": new_rfp_id,
                                        "family_rfp_id": family_rfp_id,
                                        "document_text": new_document_text,
                                        "version": new_version,
                                        "amendment_of": entry_rfp_id,
                                        "amendment_sources": [f.name for f in amendment_files],
                                        "change_summary": change_summary,
                                        "verification_notes": verification_notes,
                                    }
                                    st.session_state.current_result = new_record
                                    st.session_state.history.insert(0, new_record)
                                    save_history_to_disk(st.session_state.history)
    
                                    # Update the shared DB entry under the ORIGINAL family RFP ID,
                                    # so anything consuming the API by that ID always gets the latest.
                                    saved_ok = save_result_to_shared_db(
                                        family_rfp_id,
                                        [entry["filename"]] + [f.name for f in amendment_files],
                                        new_report,
                                    )
                                    if not saved_ok:
                                        st.warning("⚠️ Addendum analysis succeeded, but updating the shared RFP ID failed.")
    
                                    st.success("✅ Addendum analysis complete — see the new version at the top of History, or in New Analysis.")
                                    st.rerun()
                                else:
                                    st.error("❌ Addendum analysis failed. Please try again.")
    
                    pdf_bytes_hist = generate_pdf_report(entry["raw_report"])
                    if pdf_bytes_hist:
                        st.download_button(
                            label="📥 Download This Report (PDF)",
                            data=pdf_bytes_hist,
                            file_name=f"rfp_analysis_{entry['timestamp'].strftime('%Y%m%d_%H%M%S')}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            key=f"history_download_{idx}"
                        )
                    else:
                        st.error("❌ Could not generate PDF for this report.")
    
                    json_bytes_hist = generate_json_report(entry["raw_report"])
                    if json_bytes_hist:
                        st.download_button(
                            label="🧾 Download This Report (JSON)",
                            data=json_bytes_hist,
                            file_name=f"rfp_analysis_{entry['timestamp'].strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json",
                            use_container_width=True,
                            key=f"history_download_json_{idx}"
                        )
                    else:
                        st.error("❌ JSON generation failed for this report.")
    
                    ics_bytes_hist = generate_deliverables_ics(entry["raw_report"], entry.get("rfp_id", "rfp"))
                    st.download_button(
                        label="🗓️ Download Deliverables Calendar (.ics)",
                        data=ics_bytes_hist,
                        file_name=f"rfp_deliverables_{entry['timestamp'].strftime('%Y%m%d_%H%M%S')}.ics",
                        mime="text/calendar",
                        use_container_width=True,
                        key=f"history_download_ics_{idx}"
                    )
