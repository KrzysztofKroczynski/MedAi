# PDF loader for medication documents.
# Uses LangChain PyPDFLoader to load each PDF from the data/pdfs/ directory.
# For each page, attaches metadata: { source_file, page_number, doc_type }.
# doc_type is inferred from filename keywords (e.g. "PIL", "SmPC").
# Returns a flat list of LangChain Document objects across all PDFs.
