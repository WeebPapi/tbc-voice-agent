from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{" + W_NS + "}"


def main() -> None:
    source = Path(sys.argv[1])
    output = Path(sys.argv[2])
    with zipfile.ZipFile(source) as zf:
        root = etree.fromstring(zf.read("word/document.xml"))

    pages: list[list[str]] = [[]]
    page_index = 0

    for event, node in etree.iterwalk(root, events=("start", "end")):
        if event == "start" and (
            node.tag == W + "lastRenderedPageBreak"
            or (node.tag == W + "br" and node.get(W + "type") == "page")
        ):
            page_index += 1
            pages.append([])
        elif event == "start" and node.tag in {W + "t", W + "delText"}:
            if node.text:
                pages[page_index].append(node.text)
        elif event == "start" and node.tag == W + "tab":
            pages[page_index].append("\t")
        elif event == "end" and node.tag in {W + "p", W + "tr"}:
            pages[page_index].append("\n")
        elif event == "end" and node.tag == W + "tc":
            pages[page_index].append(" | ")

    result = []
    for i, parts in enumerate(pages, 1):
        text = "".join(parts)
        lines = [" ".join(line.split()) for line in text.splitlines()]
        clean = "\n".join(line for line in lines if line)
        result.append({"page": i, "text": clean})

    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"saved_pages": len(result), "characters": sum(len(x["text"]) for x in result)}))


if __name__ == "__main__":
    main()
