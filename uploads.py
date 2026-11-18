"""Read supported dashboard uploads into planner input text."""

import json
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

MAX_FILE = 8 * 1024 * 1024
MAX_TEXT = 512 * 1024
FORMATS = {".txt", ".md", ".json", ".pdf", ".docx"}
WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def document_text(name, data):
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in {".txt", ".md", ".json"}:
        text = data.decode("utf-8-sig")
        if suffix == ".json":
            json.loads(text)
        return text
    if suffix == ".docx":
        with ZipFile(BytesIO(data)) as document:
            info = document.getinfo("word/document.xml")
            if info.file_size > MAX_FILE:
                raise ValueError("Word document text is too large.")
            root = ElementTree.fromstring(document.read(info))
        return "\n".join("".join(part.text or "" for part in paragraph.iter(WORD + "t"))
                         for paragraph in root.iter(WORD + "p"))
    if suffix == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise ValueError("Unlock the PDF before uploading.")
            if len(reader.pages) > 100:
                raise ValueError("Upload a PDF with at most 100 pages.")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except PdfReadError as error:
            raise ValueError("Could not read the PDF.") from error
        if not text.strip():
            raise ValueError("No selectable PDF text found. Use an OCR copy or paste the text.")
        return text
    raise ValueError(f"Unsupported file type: {suffix or 'no extension'}.")


def read_upload(name, data):
    if not 0 < len(data) <= MAX_FILE:
        raise ValueError("The upload must be between 1 byte and 8 MiB.")
    try:
        if PurePosixPath(name).suffix.lower() == ".zip":
            with ZipFile(BytesIO(data)) as archive:
                entries = [info for info in archive.infolist()
                           if not info.is_dir() and not info.filename.startswith("__MACOSX/")]
                if not entries or len(entries) > 30 or sum(info.file_size for info in entries) > MAX_FILE:
                    raise ValueError("ZIP must contain 1–30 files and at most 8 MiB of expanded data.")
                if any(PurePosixPath(info.filename).suffix.lower() not in FORMATS for info in entries):
                    raise ValueError("ZIP contains an unsupported file type. Use TXT, MD, JSON, PDF, or DOCX members.")
                sections = []
                size = 0
                for info in entries:
                    content = document_text(info.filename, archive.read(info))
                    section = f"File: {info.filename}\n{content}"
                    size += len(section.encode("utf-8")) + 2
                    if size > MAX_TEXT:
                        raise ValueError("Extracted text exceeds 512 KiB.")
                    sections.append(section)
                text = "\n\n".join(sections)
        else:
            text = document_text(name, data)
    except (BadZipFile, KeyError, ElementTree.ParseError, UnicodeError, RuntimeError) as error:
        raise ValueError("Could not read the upload. Check the format, encoding, or password.") from error
    if not text.strip() or len(text.encode("utf-8")) > MAX_TEXT:
        raise ValueError("The upload must contain readable text under 512 KiB.")
    return text
