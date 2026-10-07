"""Print the extracted text of a PDF (used by the i18n/PDF E2E group)."""

from __future__ import annotations

import sys

from pypdf import PdfReader


def main() -> None:
    reader = PdfReader(sys.argv[1])
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(page.extract_text() or "" for page in reader.pages))


if __name__ == "__main__":
    main()
