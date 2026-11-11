"""Section-aware chunks with a size cap: one line per chunk with its heading path, pages and size,
then the first chunk in full with its heading path on top (what to embed).

usage: python examples/section_chunks.py paper.pdf [max_chars] [min_chars]     (free mode: no model, $0)
       python examples/section_chunks.py paper.pdf --langchain                 (pip install langchain-section-anything)"""

import sys

from section_anything import section

args = [a for a in sys.argv[1:] if not a.startswith("--")]
max_chars = int(args[1]) if len(args) > 1 else 1500
min_chars = int(args[2]) if len(args) > 2 else 200
if "--langchain" not in sys.argv:
    chunks = section(args[0], mode="free").chunks(max_chars=max_chars, min_chars=min_chars)
    for c in chunks:
        print(f"{' > '.join(c.heading_path) or '(front matter)':60.60} p.{c.page_start}-{c.page_end} #{c.chunk_index} {len(c.text):5d} chars")
    print(f"\n{len(chunks)} chunks, longest {max(len(c.text) for c in chunks)} chars\n")
    print(chunks[0].prefixed_text)
else:  # the same chunks as LangChain Documents, heading_path and chunk_index in the metadata
    from langchain_section_anything import SectionAnythingLoader

    for doc in SectionAnythingLoader(args[0], mode="free", chunk={"max_chars": max_chars, "min_chars": min_chars}).load():
        print(doc.metadata["heading_path"], doc.metadata["chunk_index"], len(doc.page_content))
