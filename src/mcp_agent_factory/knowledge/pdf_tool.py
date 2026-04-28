"""
file_context_extractor — local PDF text extraction MCP tool.

Reads a PDF from disk using pypdf, returns page-level text snippets.
The raw file never leaves the local environment — only extracted text
is returned to the caller for downstream pruning and routing.
"""
from __future__ import annotations

import os
from typing import Any


def file_context_extractor(
	path: str,
	query: str = "",
	max_pages: int = 20,
) -> dict[str, Any]:
	"""Extract text snippets from a local PDF file.

	Args:
		path:      Absolute or relative path to the PDF file.
		query:     Optional hint used to label snippets (not used for filtering here —
		           that is ContextPruner's job downstream).
		max_pages: Maximum number of pages to read (default 20).

	Returns:
		dict with keys:
		  - ``snippets``: list of dicts {page: int, text: str}
		  - ``total_pages``: total page count in the document
		  - ``pages_read``: number of pages actually read
		  - ``source``: resolved file path

	Raises:
		FileNotFoundError: if the path does not exist.
		RuntimeError:      if pypdf is not installed or the file cannot be parsed.
	"""
	if not os.path.exists(path):
		raise FileNotFoundError(f"PDF not found: {path}")

	try:
		import pypdf  # noqa: PLC0415
	except ImportError as exc:
		raise RuntimeError("pypdf is required for PDF extraction — install it with: pip install pypdf") from exc

	snippets: list[dict[str, Any]] = []
	try:
		reader = pypdf.PdfReader(path)
		total_pages = len(reader.pages)
		pages_to_read = min(total_pages, max_pages)

		for i in range(pages_to_read):
			text = reader.pages[i].extract_text() or ""
			text = text.strip()
			if text:
				snippets.append({"page": i + 1, "text": text})
	except Exception as exc:
		raise RuntimeError(f"Failed to parse PDF at {path}: {exc}") from exc

	return {
		"snippets": snippets,
		"total_pages": total_pages,
		"pages_read": pages_to_read,
		"source": os.path.abspath(path),
		"query": query,
	}
