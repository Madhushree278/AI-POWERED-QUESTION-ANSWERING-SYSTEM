import re
import json
from typing import List, Dict, Any, Optional
from config import settings
from database.database import get_setting
from services.vector_store import vector_store_service

class FlashcardService:
    def __init__(self):
        self.vector_store = vector_store_service

    def generate_flashcards(
        self,
        doc_id: str,
        filename: str,
        chapter: Optional[str] = None,
        num_cards: int = 8
    ) -> Dict[str, Any]:
        """
        Generate study flashcards from document chunks.
        """
        all_chunks = self.vector_store.get_document_chunks(doc_id, limit=200)
        if not all_chunks:
            return {
                "flashcards": [],
                "error": "No document content found to generate flashcards."
            }

        # Filter by chapter if specified
        if chapter and chapter != "All Chapters":
            chunks = [c for c in all_chunks if c.get("chapter") == chapter]
            if not chunks:
                chunks = all_chunks[:25]
        else:
            chunks = all_chunks[:35]

        context = "\n\n".join([f"[Page {c['page']} | {c.get('chapter', '')}]: {c['text']}" for c in chunks])

        # Attempt LLM generation first
        cards = self._generate_with_llm(context, filename, chapter, num_cards)
        if not cards:
            # Fallback to local heuristic flashcard extraction
            cards = self._generate_local(chunks, filename, num_cards)

        return {
            "doc_id": doc_id,
            "filename": filename,
            "chapter": chapter or "Entire Document",
            "total_cards": len(cards),
            "flashcards": cards
        }

    def _generate_with_llm(
        self,
        context: str,
        filename: str,
        chapter: Optional[str],
        num_cards: int
    ) -> List[Dict[str, Any]]:
        provider = get_setting("active_provider", settings.DEFAULT_PROVIDER)
        gemini_key = get_setting("gemini_api_key", settings.GEMINI_API_KEY)
        openai_key = get_setting("openai_api_key", settings.OPENAI_API_KEY)
        groq_key = get_setting("groq_api_key", settings.GROQ_API_KEY)

        prompt = f"""You are an educational study materials generator.
Extract exactly {num_cards} high-yield study flashcards based STRICTLY on the document excerpts provided below.

DOCUMENT: {filename} {f"(Chapter: {chapter})" if chapter else ""}

REQUIREMENTS:
1. 'front' should be a concise Concept, Term, or Direct Question.
2. 'back' should be a clear, informative explanation/definition grounded in the text.
3. 'category' should be a short tag (e.g., 'Definition', 'Algorithm', 'Core Concept').
4. 'source' should be '{filename}, Page X'.
5. Output ONLY a valid JSON array matching this schema:
[
  {{
    "id": 1,
    "front": "What is Supervised Learning?",
    "back": "A machine learning paradigm where algorithms are trained on labeled datasets where inputs are paired with correct outputs.",
    "category": "Core Concept",
    "source": "{filename}, Page 2"
  }}
]

DOCUMENT EXCERPTS:
{context[:20000]}
"""

        # Gemini
        if (provider == "gemini" or not provider) and gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                model_name = get_setting("gemini_model", settings.GEMINI_MODEL)
                res = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if res and res.text:
                    return self._parse_json_cards(res.text)
            except Exception as e:
                print(f"Gemini flashcard error: {e}")

        # OpenAI
        if provider == "openai" and openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                model_name = get_setting("openai_model", settings.OPENAI_MODEL)
                res = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                if res.choices and res.choices[0].message.content:
                    return self._parse_json_cards(res.choices[0].message.content)
            except Exception as e:
                print(f"OpenAI flashcard error: {e}")

        # Groq
        if provider == "groq" and groq_key:
            try:
                from groq import Groq
                client = Groq(api_key=groq_key)
                model_name = get_setting("groq_model", settings.GROQ_MODEL)
                res = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                if res.choices and res.choices[0].message.content:
                    return self._parse_json_cards(res.choices[0].message.content)
            except Exception as e:
                print(f"Groq flashcard error: {e}")

        return []

    def _parse_json_cards(self, raw_text: str) -> List[Dict[str, Any]]:
        try:
            match = re.search(r'\[\s*\{.*\}\s*\]', raw_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            print(f"Failed to parse flashcards JSON: {e}")
        return []

    def _generate_local(
        self,
        chunks: List[Dict[str, Any]],
        filename: str,
        num_cards: int
    ) -> List[Dict[str, Any]]:
        """Heuristic flashcard generator extracting definitions and key concepts when offline."""
        cards = []
        card_id = 1
        seen_fronts = set()

        for c in chunks:
            text = c["text"]
            page = c["page"]
            chapter = c.get("chapter", "Overview")

            # Look for numbered or bullet points or definitions
            lines = text.split("\n")
            for line in lines:
                line_clean = line.strip()
                if not line_clean:
                    continue

                # Pattern: "Term: Definition" or "1. Term: Definition"
                match_colon = re.match(r'^(?:[0-9]+[.)]\s*)?([A-Za-z0-9\s\-]{3,40}):\s*(.+)$', line_clean)
                if match_colon:
                    term = match_colon.group(1).strip()
                    definition = match_colon.group(2).strip()
                    if term.lower() not in seen_fronts and len(definition) > 20:
                        seen_fronts.add(term.lower())
                        cards.append({
                            "id": card_id,
                            "front": f"What is {term}?",
                            "back": definition,
                            "category": chapter if chapter != "General Content" else "Key Concept",
                            "source": f"{filename}, Page {page}"
                        })
                        card_id += 1
                        if len(cards) >= num_cards:
                            return cards

                # Pattern: "Term is defined as..." or "Term refers to..."
                match_def = re.search(r'([A-Za-z0-9\s]{3,35})\s+(?:is defined as|is a subset of|is the primary|refers to|utilizes)\s+(.+?)(?:\.|$)', line_clean, re.IGNORECASE)
                if match_def:
                    term = match_def.group(1).strip()
                    rest = match_def.group(2).strip()
                    if term.lower() not in seen_fronts and len(rest) > 20 and len(term.split()) <= 4:
                        seen_fronts.add(term.lower())
                        cards.append({
                            "id": card_id,
                            "front": f"Define: {term.capitalize()}",
                            "back": f"{term.capitalize()} {line_clean[len(match_def.group(1)):].strip()}",
                            "category": "Definition",
                            "source": f"{filename}, Page {page}"
                        })
                        card_id += 1
                        if len(cards) >= num_cards:
                            return cards

        # Fallback if more cards needed
        for c in chunks:
            if len(cards) >= num_cards:
                break
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', c["text"]) if len(s.strip()) > 50]
            for s in sentences:
                words = s.split()
                if len(words) > 10:
                    topic = " ".join(words[:4])
                    if topic.lower() not in seen_fronts:
                        seen_fronts.add(topic.lower())
                        cards.append({
                            "id": card_id,
                            "front": f"Key Principle: {topic}...",
                            "back": s,
                            "category": "Core Concept",
                            "source": f"{filename}, Page {c['page']}"
                        })
                        card_id += 1
                        if len(cards) >= num_cards:
                            break

        return cards[:num_cards]

flashcard_service = FlashcardService()
