import streamlit as st
from pypdf import PdfReader

def extract_text_with_context(uploaded_files):
    """Extract text from multiple PDFs with document name context."""
    all_text = ""
    total_files = len(uploaded_files)
    
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    for idx, pdf_file in enumerate(uploaded_files):
        filename = pdf_file.name
        progress_text.markdown(f"📖 **Reading PDF...** `{filename}` ({idx+1}/{total_files})")
        
        reader = PdfReader(pdf_file)
        text = ""
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += f"\n\n[PAGE {i+1}]\n" + page_text + "\n"
        
        # Add document marker with filename
        all_text += f"\n\n{'='*60}\n[START OF DOCUMENT: {filename}]\n{'='*60}\n"
        all_text += text
        all_text += f"\n{'='*60}\n[END OF DOCUMENT: {filename}]\n{'='*60}\n"
        
        progress = (idx + 1) / total_files
        progress_bar.progress(progress)
    
    progress_bar.empty()
    progress_text.empty()
    
    return all_text
