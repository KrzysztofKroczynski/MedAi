# Text chunker for loaded PDF documents.
# Uses LangChain RecursiveCharacterTextSplitter to split documents into overlapping chunks.
# Chunk size and overlap should be configurable (defaults: 800 tokens, 150 overlap).
# Preserves and forwards all source metadata (source_file, page_number, doc_type) to each chunk.
# Returns a list of LangChain Document objects ready for entity extraction.
