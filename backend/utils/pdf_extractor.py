import fitz
from fastapi import UploadFile


async def extract_resume_text_and_links(file: UploadFile) -> tuple[str, int]:
    """
    Extracts text and hyperlink annotations from an uploaded PDF file using PyMuPDF.
    """
    resume_text = ""
    try:
        pdf_bytes = await file.read()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        extracted_links: list[str] = []
        page_count = len(doc)
        for page in doc:
            text = page.get_text()
            if isinstance(text, str):
                resume_text += text

            # Extract hyperlink annotations with their anchor text
            for link in page.get_links():
                uri = link.get("uri", "")
                if uri and uri.startswith("http"):
                    rect = link.get("from")
                    anchor_text = ""
                    if rect:
                        raw_text = page.get_text("text", clip=rect)
                        if isinstance(raw_text, str):
                            anchor_text = raw_text.strip()
                        elif isinstance(raw_text, dict):
                            anchor_text = raw_text.get("text", "").strip()
                        elif isinstance(raw_text, list):
                            anchor_text = " ".join(str(x) for x in raw_text).strip()
                        else:
                            anchor_text = str(raw_text).strip()
                        anchor_text = " ".join(anchor_text.split())

                    if anchor_text:
                        extracted_links.append(f"Text: '{anchor_text}' -> URL: {uri}")
                    else:
                        extracted_links.append(f"URL: {uri}")

        if extracted_links:
            # Deduplicate while preserving order
            seen: set[str] = set()
            unique_links = [u for u in extracted_links if not (u in seen or seen.add(u))]
            resume_text += "\n\n[HYPERLINKS FOUND IN RESUME — use these to fill profile_links and project links]\n"
            resume_text += "\n".join(unique_links)

        return resume_text, page_count
    except Exception as e:
        raise ValueError(f"Failed to read PDF: {e!s}")
