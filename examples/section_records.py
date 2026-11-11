"""Section records for RAG: one JSON object per section with its title, heading path, level, page
span, where the heading is printed and the section's text (the shape docling#2147 asks for).

usage: python examples/section_records.py paper.pdf          (free mode: no model, $0)
       python examples/section_records.py paper.pdf --langchain"""

import json
import sys

from section_anything import section

tree = section(sys.argv[1], mode="free")
if "--langchain" not in sys.argv:
    for sec in tree.to_dict(text=True)["sections"]:
        record = {k: sec[k] for k in ("title", "heading_path", "level", "page_start", "page_end", "heading_bbox", "text")}
        print(json.dumps(record, ensure_ascii=False))
else:  # the same records as LangChain Documents: pip install langchain-section-anything
    from langchain_section_anything import SectionAnythingLoader

    for doc in SectionAnythingLoader(sys.argv[1], mode="free").load():
        print(json.dumps({"metadata": doc.metadata, "page_content": doc.page_content}, ensure_ascii=False))
