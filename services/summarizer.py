import re
from typing import Dict, Any, List, Optional
from config import settings
from database.database import get_setting
from services.vector_store import vector_store_service

SUMMARY_PROMPTS = {
    "short": "Provide a high-impact, concise executive summary (1-2 paragraphs) of this text.",
    "detailed": "Provide an extensive, detailed summary with major themes, detailed explanations, and key takeaways.",
    "key_points": "Extract the top 8-12 most critical key points and takeaways as clear bullet points.",
    "concepts": "Identify and explain the core conceptual frameworks, theories, and methodologies described in the document.",
    "definitions": "List all important technical terms, keywords, and definitions explicitly introduced or explained in this document.",
    "chapter_wise": "Provide a structured chapter-by-chapter (or section-by-section) summary of the content."
}

class DocumentSummarizer:
    def __init__(self):
        self.vector_store = vector_store_service

    def summarize(
        self,
        doc_id: str,
        filename: str,
        summary_type: str = "short",
        chapter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a document or chapter summary according to the selected summary type.
        """
        # Fetch chunks for this document
        all_chunks = self.vector_store.get_document_chunks(doc_id, limit=300)
        if not all_chunks:
            return {
                "summary": "No document content found to summarize.",
                "doc_id": doc_id,
                "filename": filename,
                "summary_type": summary_type,
                "chapter": chapter
            }

        # Filter by chapter if specified
        if chapter and chapter != "All Chapters":
            chunks = [c for c in all_chunks if c.get("chapter") == chapter]
            if not chunks:
                chunks = all_chunks[:30]
        else:
            # Sample across document for representative coverage
            if len(all_chunks) > 40:
                step = len(all_chunks) // 30
                chunks = all_chunks[::step][:30]
            else:
                chunks = all_chunks

        # Combine text excerpts
        context = "\n\n".join([f"[Page {c['page']} | {c.get('chapter', '')}]: {c['text']}" for c in chunks])
        prompt_instruction = SUMMARY_PROMPTS.get(summary_type, SUMMARY_PROMPTS["short"])

        summary_text = self._generate_summary(context, prompt_instruction, filename, chapter, summary_type)

        return {
            "summary": summary_text,
            "doc_id": doc_id,
            "filename": filename,
            "summary_type": summary_type,
            "chapter": chapter or "Entire Document",
            "chunks_analyzed": len(chunks)
        }

    def _generate_summary(
        self,
        context: str,
        instruction: str,
        filename: str,
        chapter: Optional[str],
        summary_type: str
    ) -> str:
        provider = get_setting("active_provider", settings.DEFAULT_PROVIDER)
        gemini_key = get_setting("gemini_api_key", settings.GEMINI_API_KEY)
        openai_key = get_setting("openai_api_key", settings.OPENAI_API_KEY)
        groq_key = get_setting("groq_api_key", settings.GROQ_API_KEY)

        target = f"Chapter '{chapter}' of {filename}" if chapter and chapter != "All Chapters" else f"Document '{filename}'"
        
        prompt = f"""You are an elite research summarizer.
Your task is to analyze the provided text excerpts from {target} and fulfill this request:
{instruction}

Rules:
- Base your summary strictly on the facts in the text.
- Do not fabricate outside information.
- Format with clean Markdown (headings, bullet points, bold key terms).

TEXT EXCERPTS:
{context[:25000]}
"""

        # Gemini
        if (provider == "gemini" or not provider) and gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                model_name = get_setting("gemini_model", settings.GEMINI_MODEL)
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"Gemini summarization error: {e}")

        # OpenAI
        if provider == "openai" and openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                model_name = get_setting("openai_model", settings.OPENAI_MODEL)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a professional research document summarizer."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"OpenAI summarization error: {e}")

        # Groq
        if provider == "groq" and groq_key:
            try:
                from groq import Groq
                client = Groq(api_key=groq_key)
                model_name = get_setting("groq_model", settings.GROQ_MODEL)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a professional research document summarizer."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"Groq summarization error: {e}")

        # Local fallback synthesis
        return self._local_summary(context, summary_type, target)

    def _local_summary(self, context: str, summary_type: str, target: str) -> str:
        """Heuristic summary generator when offline or no API key set."""
        # Extract lead sentences from each paragraph
        blocks = [b.strip() for b in context.split("\n\n") if len(b.strip()) > 50]
        lead_sentences = []
        for b in blocks:
            # Strip page prefix
            clean_b = re.sub(r'^\[Page \d+[^\]]*\]:\s*', '', b)
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean_b) if len(s.strip()) > 35]
            if sentences:
                lead_sentences.append(sentences[0])

        if not lead_sentences:
            return f"Summary for {target}: Document indexed successfully with {len(blocks)} sections."

        if summary_type == "short":
            summary = " ".join(lead_sentences[:4])
            return f"### Executive Summary ({target})\n\n{summary}\n\n*(Extracted from document key sections)*"

        elif summary_type == "key_points":
            points = "\n".join([f"- **Key Insight {i+1}**: {s}" for i, s in enumerate(lead_sentences[:8])])
            return f"### Core Key Points ({target})\n\n{points}"

        elif summary_type == "definitions":
            definitions = []
            for s in lead_sentences:
                if any(w in s.lower() for w in ["is defined as", "refers to", "is a", "means", "known as", "termed"]):
                    definitions.append(f"- **Concept**: {s}")
            if not definitions:
                definitions = [f"- **Key Passage**: {s}" for s in lead_sentences[:5]]
            return f"### Important Definitions & Terms ({target})\n\n" + "\n".join(definitions[:8])

        elif summary_type == "concepts":
            concepts = "\n".join([f"#### Concept {i+1}\n{s}\n" for i, s in enumerate(lead_sentences[:5])])
            return f"### Important Concepts & Frameworks ({target})\n\n{concepts}"

        else: # Detailed or chapter-wise
            body = "\n\n".join([f"**Section {i+1}**: {s}" for i, s in enumerate(lead_sentences[:8])])
            return f"### Detailed Comprehensive Summary ({target})\n\n{body}"

summarizer_service = DocumentSummarizer()
