import streamlit as st
from datetime import datetime
from html import escape

from .analysis import _apply_verification_fix, _parse_verification_issues, analyze_rfp
from .exports import generate_deliverables_ics, generate_json_report, generate_pdf_report, render_addendum_summary, save_result_to_shared_db
from .history import compute_files_hash, generate_auto_rfp_id, save_history_to_disk
from .pdf_reader import extract_text_with_context
from .presentation import format_report, split_report_sections


def render_new_tab(top_tab_new, uploaded_files):
    with top_tab_new:
        if uploaded_files:
            st.markdown(f"""
            <div class="success-box">
                ✅ {len(uploaded_files)} PDF(s) Uploaded Successfully! Ready for analysis.
            </div>
            """, unsafe_allow_html=True)
    
            # Show list of uploaded files
            file_list_html = '<div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 0.5rem 0 1rem 0;">'
            for f in uploaded_files:
                file_list_html += f'<span style="background: rgba(124,108,255,0.15); padding: 0.3rem 0.8rem; border-radius: 20px; font-size: 0.8rem; color: #cdd2ef; border: 1px solid rgba(124,108,255,0.2);">📄 {f.name}</span>'
            file_list_html += '</div>'
            st.markdown(file_list_html, unsafe_allow_html=True)
    
            if st.button("🚀 Start Analysis", use_container_width=True):
                current_hash = compute_files_hash(uploaded_files)
    
                cached_entry = next(
                    (item for item in st.session_state.history if item.get("files_hash") == current_hash),
                    None
                )
    
                if cached_entry:
                    st.info("♻️ These files have already been analyzed — showing the saved results.")
                    st.session_state.current_result = cached_entry
                    st.rerun()
                else:
                    with st.spinner("📖 Reading PDF documents..."):
                        document_text = extract_text_with_context(uploaded_files)
    
                    report, verification_notes = analyze_rfp(document_text)
    
                    if report and "Analysis failed" not in report:
                        formatted_report = format_report(report)
                        combined_filename = ", ".join(f.name for f in uploaded_files) if uploaded_files else "Multiple_RFPs.pdf"
    
                        source_names = [f.name for f in uploaded_files]
                        final_rfp_id = generate_auto_rfp_id(uploaded_files, current_hash)
    
                        record = {
                            "filename": combined_filename,
                            "timestamp": datetime.now(),
                            "raw_report": report,
                            "formatted_report": formatted_report,
                            "files_hash": current_hash,
                            "rfp_id": final_rfp_id,
                            "family_rfp_id": final_rfp_id,
                            "document_text": document_text,
                            "version": 1,
                            "amendment_of": None,
                            "amendment_sources": [],
                            "change_summary": None,
                            "verification_notes": verification_notes,
                        }
                        st.session_state.current_result = record
                        st.session_state.history.insert(0, record)
                        save_history_to_disk(st.session_state.history)
    
                        saved_ok = save_result_to_shared_db(final_rfp_id, source_names, report)
                        if not saved_ok:
                            st.warning("⚠️ Analysis succeeded, but saving under the RFP ID failed.")
    
                        st.rerun()
                    else:
                        st.error("❌ Analysis failed. Please try again.")
    
    
        if st.session_state.current_result:
            result = st.session_state.current_result
    
            st.markdown("""
            <div class="success-box">
                ✅ Analysis Completed Successfully!
            </div>
            """, unsafe_allow_html=True)
    
            rfp_id_value = result.get("rfp_id", "N/A")
            st.markdown(f"""
            <div style="background: var(--grad-surface); border: 1px solid var(--border-soft);
                        border-left: 4px solid var(--accent-3); border-radius: 14px;
                        padding: 1rem 1.4rem; margin: 1rem 0; display: flex;
                        align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;">
                <div>
                    <div style="font-size: 0.72rem; letter-spacing: 1.5px; text-transform: uppercase;
                                color: var(--text-muted); font-weight: 700; margin-bottom: 0.25rem;">
                        RFP ID
                    </div>
                    <div style="font-family: 'Sora', sans-serif; font-size: 1.15rem; font-weight: 700;
                                color: var(--accent-3);">
                        {rfp_id_value}
                    </div>
                </div>
                <div style="font-size: 0.82rem; color: var(--text-secondary);">
                    📡 Available via the JSON API using this ID
                </div>
            </div>
            """, unsafe_allow_html=True)
    
            if result.get("version", 1) > 1:
                amend_sources = ", ".join(result.get("amendment_sources", [])) or "addendum document(s)"
                st.markdown(f"""
                <div class="amendment-banner">
                    <div class="amendment-banner__eyebrow">
                        <span>🔄</span><span>Addendum v{result.get("version", 1)} · updated from: {amend_sources}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if result.get("change_summary"):
                    with st.expander("📝 What Changed in This Addendum", expanded=True):
                        st.markdown('<span class="addendum-hover-marker"></span>', unsafe_allow_html=True)
                        st.markdown(render_addendum_summary(result["change_summary"]), unsafe_allow_html=True)
            sections = split_report_sections(result["formatted_report"])
    
            st.markdown("---")
    
            tab_deliverables, tab_evaluation, tab_checklist, tab_decision, tab_verification = st.tabs([
                "📋 Deliverables",
                "⚖️ Evaluation Criteria",
                "✅ Compliance Checklist",
                "🎯 Scoring & Decision",
                "🔍 Verification",
            ])
    
            with tab_deliverables:
                deliverables_html = sections.get("sec-deliverables")
                if deliverables_html:
                    st.markdown(deliverables_html, unsafe_allow_html=True)
                else:
                    # Last-resort fallback: show the raw report text so nothing is
                    # ever silently lost, instead of just an unhelpful message.
                    st.warning("⚠️ Couldn't detect a clean Deliverables section — showing the raw analysis below instead.")
                    st.markdown(result["raw_report"])
    
            with tab_evaluation:
                evaluation_html = sections.get(
                    "sec-evaluation", "_No evaluation criteria section found in the report._"
                )
                st.markdown(
                    f'<div class="evaluation-content">{evaluation_html}</div>',
                    unsafe_allow_html=True,
                )
    
            with tab_checklist:
                st.markdown(
                    sections.get("sec-checklist", "_No compliance checklist section found in the report._"),
                    unsafe_allow_html=True
                )
    
            with tab_decision:
                combined_decision = sections.get("sec-scoring", "") + sections.get("sec-decision", "")
                st.markdown(
                    combined_decision or "_No scoring/decision section found in the report._",
                    unsafe_allow_html=True
                )
    
            with tab_verification:
                verification_notes = result.get("verification_notes", "")
                if verification_notes:
                    confidence, issues, no_issues = _parse_verification_issues(verification_notes)
    
                    if no_issues:
                        st.markdown(f"""
                        <div class="verification-card">
                            <div class="verification-check">✓</div>
                            <div class="verification-copy">
                                <div class="verification-eyebrow">Independent Quality Check</div>
                                <div class="verification-title">Verified against the source RFP</div>
                                <p class="verification-subtitle">No material accuracy or completeness issues were identified in this report.</p>
                            </div>
                            <div class="verification-confidence">{escape(confidence)} CONFIDENCE</div>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        # Do not call an audit “verified” when it has identified concrete issues.
                        # Keep it neat and collapsible, while preserving the accuracy warning.
                        count = len(issues)
                        st.markdown(f"""
                        <div class="verification-card review">
                            <div class="verification-check">!</div>
                            <div class="verification-copy">
                                <div class="verification-eyebrow">Independent Quality Check</div>
                                <div class="verification-title">Review recommended before final submission</div>
                                <p class="verification-subtitle">The audit identified {count} item{'s' if count != 1 else ''} that should be checked against the source RFP. Fixable items can be corrected in one click below — no full re-analysis needed.</p>
                            </div>
                            <div class="verification-confidence">{escape(confidence)} CONFIDENCE</div>
                        </div>
                        """, unsafe_allow_html=True)
                        with st.expander(f"View {count} verification item{'s' if count != 1 else ''}", expanded=True):
                            for i, issue in enumerate(issues):
                                col_issue, col_fix = st.columns([5, 1])
                                with col_issue:
                                    st.markdown(f'<div class="verification-detail">{escape(issue["display"])}</div>', unsafe_allow_html=True)
                                with col_fix:
                                    if issue["fixable"]:
                                        if st.button("🔧 Fix", key=f"verif_fix_{rfp_id_value}_{i}", use_container_width=True,
                                                     help="Apply this exact correction to the report"):
                                            new_raw, new_notes, ok, msg = _apply_verification_fix(
                                                result["raw_report"], verification_notes, issue,
                                            )
                                            if ok:
                                                result["raw_report"] = new_raw
                                                result["formatted_report"] = format_report(new_raw)
                                                result["verification_notes"] = new_notes
                                                save_history_to_disk(st.session_state.history)
                                                st.success(msg)
                                                st.rerun()
                                            else:
                                                st.warning(msg)
                                    else:
                                        st.caption("Needs re-run")
    
                    st.caption("This quality check compares the completed report with the original RFP source text.")
                else:
                    st.info("ℹ️ Verification results are not available for this analysis.")
    
            st.markdown("---")
    
            pdf_bytes = generate_pdf_report(result["raw_report"])
            if pdf_bytes:
                st.download_button(
                    label="📥 Download Report (PDF)",
                    data=pdf_bytes,
                    file_name="rfp_analysis_report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            else:
                st.error("❌ PDF generation failed. Please try again.")
    
            json_bytes = generate_json_report(result["raw_report"])
            if json_bytes:
                st.download_button(
                    label="🧾 Download JSON File",
                    data=json_bytes,
                    file_name="rfp_analysis.json",
                    mime="application/json",
                    use_container_width=True
                )
            else:
                st.error("❌ JSON generation failed. Please try again.")
    
            ics_bytes = generate_deliverables_ics(result["raw_report"], result.get("rfp_id", "rfp"))
            st.download_button(
                label="🗓️ Download Deliverables Calendar (.ics)",
                data=ics_bytes,
                file_name="rfp_deliverables_calendar.ics",
                mime="text/calendar",
                use_container_width=True
            )
