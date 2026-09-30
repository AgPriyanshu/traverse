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
