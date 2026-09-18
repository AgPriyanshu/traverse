"""Tiny hand-built PDFs for tests that need control over ``/Info`` metadata.

pypdfium2 (this project's transitive PDF backend) has no metadata *writer*, so
a fixture file cannot be produced by round-tripping it through pdfium. Its
recovery parser is lenient enough to accept a PDF with no cross-reference
table, which is the shortest byte string that still carries a real ``/Info``
dictionary.
"""


def minimal_pdf_with_metadata(title: str, author: str) -> bytes:
    """Return a minimal, valid-enough one-page PDF carrying ``title``/``author``."""
    pdf = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> >>
endobj
4 0 obj
<< /Title ({title}) /Author ({author}) >>
endobj
trailer
<< /Root 1 0 R /Info 4 0 R >>
%%EOF
"""

    return pdf.encode()
