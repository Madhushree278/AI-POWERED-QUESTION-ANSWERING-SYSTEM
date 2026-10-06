import re
import io
from pathlib import Path
from typing import List, Dict, Any, Tuple
import pymupdf  # PyMuPDF
import docx
from utils.helpers import clean_text

class DocumentProcessor:
    def __init__(self, chunk_size: int = 750, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process_file(self, filepath: Path, filename: str, doc_id: str) -> Dict[str, Any]:
        """
        Extracts pages, detects chapters, generates chunks, and builds suggested questions.
        """
        ext = filepath.suffix.lower()
        if ext == ".pdf":
            pages, is_scanned, chapters = self._process_pdf(filepath)
        elif ext == ".docx":
            pages, is_scanned, chapters = self._process_docx(filepath)
        elif ext in [".txt", ".md"]:
            pages, is_scanned, chapters = self._process_text(filepath)
        else:
            raise ValueError(f"Unsupported file format: {ext}. Supported formats: PDF, DOCX, TXT, MD.")

        if not pages or all(not p["text"].strip() for p in pages):
            if is_scanned:
                raise ValueError("This PDF appears to be scanned or image-based. Text extraction requires OCR.")
            raise ValueError("The uploaded document is empty or could not yield any readable text.")

        # Assign end pages to chapters
        chapters = self._finalize_chapters(chapters, len(pages))

        # Create chunks with chapter and page metadata
        chunks = self._create_chunks(pages, chapters, doc_id, filename)

        # Generate suggested questions
        suggested_questions = self._generate_suggested_questions(filename, chapters, pages)

        return {
            "page_count": len(pages),
            "chunk_count": len(chunks),
            "is_scanned": is_scanned,
            "chapters": chapters,
            "chunks": chunks,
            "suggested_questions": suggested_questions,
            "pages": pages
        }

    def _process_pdf(self, filepath: Path) -> Tuple[List[Dict[str, Any]], bool, List[Dict[str, Any]]]:
        doc = pymupdf.open(str(filepath))
        pages = []
        total_words = 0
        
        # 1. Extract text page by page
        for page_num in range(len(doc)):
            page = doc[page_num]
            raw_text = page.get_text("text") or ""
            cleaned = clean_text(raw_text)
            words = len(cleaned.split())
            total_words += words
            pages.append({
                "page": page_num + 1,
                "text": cleaned,
                "word_count": words
            })

        avg_words = total_words / max(len(pages), 1)
        is_scanned = avg_words < 12 and len(pages) > 0

        # 2. Extract chapters
        chapters = []
        # Try native TOC
        toc = doc.get_toc() # [[lvl, title, page], ...]
        if toc:
            for item in toc:
                lvl, title, start_page = item[0], item[1].strip(), item[2]
                if lvl <= 2 and title:  # top two levels
                    chapters.append({
                        "number": len(chapters) + 1,
                        "title": title,
                        "start_page": max(1, start_page),
                        "end_page": len(pages)
                    })
        
        # If no TOC found, fallback to regex heading detection
        if not chapters:
            chapters = self._detect_chapters_from_text(pages)

        doc.close()
        return pages, is_scanned, chapters

    def _process_docx(self, filepath: Path) -> Tuple[List[Dict[str, Any]], bool, List[Dict[str, Any]]]:
        doc = docx.Document(str(filepath))
        full_text = []
        chapters = []
        page_approx = []
        current_page_text = []
        words_count = 0
        current_page_num = 1

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            # Check if heading is styled as Heading 1 or starts with Chapter
            style_name = para.style.name.lower() if para.style else ""
            if "heading 1" in style_name or re.match(r'^(?:Chapter|CHAPTER|Section|SECTION)\s+[0-9IVXLCDM]+', text):
                chapters.append({
                    "number": len(chapters) + 1,
                    "title": text[:80],
                    "start_page": current_page_num,
                    "end_page": current_page_num
                })

            current_page_text.append(text)
            words_count += len(text.split())

            # Synthesize ~500 words per page for DOCX
            if words_count >= 500:
                page_approx.append({
                    "page": current_page_num,
                    "text": clean_text("\n".join(current_page_text)),
                    "word_count": words_count
                })
                current_page_text = []
                words_count = 0
                current_page_num += 1

        if current_page_text:
            page_approx.append({
                "page": current_page_num,
                "text": clean_text("\n".join(current_page_text)),
                "word_count": words_count
            })

        return page_approx, False, chapters

    def _process_text(self, filepath: Path) -> Tuple[List[Dict[str, Any]], bool, List[Dict[str, Any]]]:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        pages = []
        current_page_lines = []
        current_page_num = 1
        chapters = []

        for line in lines:
            trimmed = line.strip()
            if re.match(r'^(?:#\s+|Chapter\s+[0-9IVXLCDM]+|CHAPTER\s+[0-9IVXLCDM]+)', trimmed):
                chapters.append({
                    "number": len(chapters) + 1,
                    "title": trimmed.lstrip('#').strip()[:80],
                    "start_page": current_page_num,
                    "end_page": current_page_num
                })

            current_page_lines.append(line)
            # ~60 lines per synthetic page
            if len(current_page_lines) >= 60:
                pages.append({
                    "page": current_page_num,
                    "text": clean_text("".join(current_page_lines)),
                    "word_count": len("".join(current_page_lines).split())
                })
                current_page_lines = []
                current_page_num += 1

        if current_page_lines:
            pages.append({
                "page": current_page_num,
                "text": clean_text("".join(current_page_lines)),
                "word_count": len("".join(current_page_lines).split())
            })

        return pages, False, chapters

    def _detect_chapters_from_text(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chapters = []
        chapter_regex = re.compile(
            r'^(?:(?:Chapter|CHAPTER|Unit|UNIT|Part|PART|Section|SECTION)\s+([0-9IVXLCDM]+)[\s:.\-]+(.*)|([0-9]+)\s+([A-Z][A-Za-z0-9 ]{3,50}))$',
            re.MULTILINE
        )

        for page in pages:
            text = page["text"]
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for line in lines[:8]:  # inspect header lines of each page
                match = chapter_regex.match(line)
                if match:
                    title = line[:70]
                    # Avoid duplicate chapter names
                    if not any(c["title"].lower() == title.lower() for c in chapters):
                        chapters.append({
                            "number": len(chapters) + 1,
                            "title": title,
                            "start_page": page["page"],
                            "end_page": len(pages)
                        })
                    break
        return chapters

    def _finalize_chapters(self, chapters: List[Dict[str, Any]], total_pages: int) -> List[Dict[str, Any]]:
        """Fix chapter boundary end pages so they don't overlap."""
        if not chapters:
            return []
        
        # Sort by start_page
        chapters = sorted(chapters, key=lambda c: c["start_page"])
        for i in range(len(chapters)):
            chapters[i]["number"] = i + 1
            if i < len(chapters) - 1:
                next_start = chapters[i + 1]["start_page"]
                chapters[i]["end_page"] = max(chapters[i]["start_page"], next_start - 1)
            else:
                chapters[i]["end_page"] = total_pages
        return chapters

    def _create_chunks(
        self, 
        pages: List[Dict[str, Any]], 
        chapters: List[Dict[str, Any]], 
        doc_id: str, 
        filename: str
    ) -> List[Dict[str, Any]]:
        chunks = []
        chunk_idx = 0

        def get_chapter_for_page(page_num: int) -> str:
            for ch in chapters:
                if ch["start_page"] <= page_num <= ch["end_page"]:
                    return ch["title"]
            return "General Content"

        for page in pages:
            text = page["text"]
            page_num = page["page"]
            chapter_name = get_chapter_for_page(page_num)

            if not text.strip():
                continue

            # Split text by paragraphs first
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            current_chunk = ""

            for p in paragraphs:
                if len(current_chunk) + len(p) + 2 <= self.chunk_size:
                    current_chunk = (current_chunk + "\n\n" + p).strip()
                else:
                    if current_chunk:
                        chunks.append({
                            "chunk_id": f"{doc_id}_{chunk_idx}",
                            "doc_id": doc_id,
                            "filename": filename,
                            "page": page_num,
                            "chapter": chapter_name,
                            "chunk_index": chunk_idx,
                            "text": current_chunk
                        })
                        chunk_idx += 1
                        # Retain overlap
                        overlap_text = current_chunk[-self.chunk_overlap:] if len(current_chunk) > self.chunk_overlap else ""
                        current_chunk = (overlap_text + "\n\n" + p).strip()
                    else:
                        # Single paragraph exceeds chunk_size, split by sentences or chars
                        start = 0
                        while start < len(p):
                            end = start + self.chunk_size
                            part = p[start:end]
                            chunks.append({
                                "chunk_id": f"{doc_id}_{chunk_idx}",
                                "doc_id": doc_id,
                                "filename": filename,
                                "page": page_num,
                                "chapter": chapter_name,
                                "chunk_index": chunk_idx,
                                "text": part
                            })
                            chunk_idx += 1
                            start += (self.chunk_size - self.chunk_overlap)
                        current_chunk = ""

            if current_chunk:
                chunks.append({
                    "chunk_id": f"{doc_id}_{chunk_idx}",
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": page_num,
                    "chapter": chapter_name,
                    "chunk_index": chunk_idx,
                    "text": current_chunk
                })
                chunk_idx += 1

        return chunks

    def _generate_suggested_questions(
        self, 
        filename: str, 
        chapters: List[Dict[str, Any]], 
        pages: List[Dict[str, Any]]
    ) -> List[str]:
        clean_name = Path(filename).stem.replace("_", " ").title()
        questions = [
            f"What is {clean_name} mainly about?",
            "What are the core concepts and principles discussed?",
            "What are the most important definitions in this document?",
            "Provide a comprehensive summary of key findings.",
            "What are the practical applications or steps described?"
        ]

        # Add chapter-specific questions if available
        if chapters:
            first_ch = chapters[0]["title"]
            questions.insert(1, f"What does '{first_ch}' discuss?")
            if len(chapters) > 1:
                second_ch = chapters[1]["title"]
                questions.append(f"Summarize the main points of '{second_ch}'.")

        return questions[:7]

    def render_pdf_page_image(self, filepath: Path, page_num: int) -> bytes:
        """Render a single PDF page as PNG bytes for the PDF viewer."""
        doc = pymupdf.open(str(filepath))
        if page_num < 1 or page_num > len(doc):
            doc.close()
            raise ValueError(f"Page {page_num} out of bounds (1-{len(doc)})")
        page = doc[page_num - 1]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()
        return img_bytes
