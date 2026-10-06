import re
import json
from typing import List, Dict, Any, Optional
from config import settings
from database.database import get_setting
from services.vector_store import vector_store_service

class QuizService:
    def __init__(self):
        self.vector_store = vector_store_service

    def generate_quiz(
        self,
        doc_id: str,
        filename: str,
        chapter: Optional[str] = None,
        num_questions: int = 5,
        difficulty: str = "Medium"
    ) -> Dict[str, Any]:
        """
        Generate multiple-choice quiz questions strictly based on document chunks.
        """
        all_chunks = self.vector_store.get_document_chunks(doc_id, limit=200)
        if not all_chunks:
            return {
                "questions": [],
                "error": "No document content found to generate quiz."
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
        questions = self._generate_with_llm(context, filename, chapter, num_questions, difficulty)
        if not questions:
            # Fallback to local heuristic question generator
            questions = self._generate_local(chunks, filename, num_questions)

        return {
            "doc_id": doc_id,
            "filename": filename,
            "chapter": chapter or "Entire Document",
            "total_questions": len(questions),
            "questions": questions
        }

    def _generate_with_llm(
        self,
        context: str,
        filename: str,
        chapter: Optional[str],
        num_questions: int,
        difficulty: str
    ) -> List[Dict[str, Any]]:
        provider = get_setting("active_provider", settings.DEFAULT_PROVIDER)
        gemini_key = get_setting("gemini_api_key", settings.GEMINI_API_KEY)
        openai_key = get_setting("openai_api_key", settings.OPENAI_API_KEY)
        groq_key = get_setting("groq_api_key", settings.GROQ_API_KEY)

        prompt = f"""You are an educational assessment expert.
Generate exactly {num_questions} multiple-choice quiz questions based STRICTLY on the document excerpts provided below.

DIFFICULTY: {difficulty}
DOCUMENT: {filename} {f"(Chapter: {chapter})" if chapter else ""}

REQUIREMENTS:
1. Every question must be grounded in the excerpts. Do NOT hallucinate.
2. Provide 4 options (A, B, C, D) with exactly ONE correct answer.
3. Provide a clear explanation citing the document context.
4. Output ONLY valid JSON array with this exact structure:
[
  {{
    "id": 1,
    "question": "Question text here?",
    "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
    "correct_index": 0,
    "explanation": "Detailed explanation grounded in the document text.",
    "source": "{filename}, Page X"
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
                    return self._parse_json_questions(res.text)
            except Exception as e:
                print(f"Gemini quiz error: {e}")

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
                    return self._parse_json_questions(res.choices[0].message.content)
            except Exception as e:
                print(f"OpenAI quiz error: {e}")

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
                    return self._parse_json_questions(res.choices[0].message.content)
            except Exception as e:
                print(f"Groq quiz error: {e}")

        return []

    def _parse_json_questions(self, raw_text: str) -> List[Dict[str, Any]]:
        try:
            # Extract JSON block
            match = re.search(r'\[\s*\{.*\}\s*\]', raw_text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            print(f"Failed to parse quiz JSON: {e}")
        return []

    def _generate_local(
        self,
        chunks: List[Dict[str, Any]],
        filename: str,
        num_questions: int
    ) -> List[Dict[str, Any]]:
        """Heuristic quiz generator from document sentences when offline."""
        questions = []
        q_id = 1

        for c in chunks:
            text = c["text"]
            page = c["page"]
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 45]

            for s in sentences:
                # Check for definition or key factual statement
                if any(w in s.lower() for w in ["is defined as", "refers to", "is a subset of", "is the primary", "introduced in", "utilizes", "consists of"]):
                    parts = re.split(r'\s+(?:is defined as|refers to|is a subset of|is the primary|introduced in|utilizes)\s+', s, flags=re.IGNORECASE)
                    if len(parts) == 2 and len(parts[0]) < 80 and len(parts[1]) > 20:
                        subject = parts[0].strip().capitalize()
                        fact = parts[1].strip()

                        # Build question
                        q_text = f"According to the document, what is {subject}?"
                        correct_opt = f"A) {fact[:90]}..."
                        wrong_opt1 = f"B) A traditional non-computational mechanical framework"
                        wrong_opt2 = f"C) A deprecated standard replaced by older systems"
                        wrong_opt3 = f"D) A hardware protocol unrelated to {subject.lower()}"

                        questions.append({
                            "id": q_id,
                            "question": q_text,
                            "options": [correct_opt, wrong_opt1, wrong_opt2, wrong_opt3],
                            "correct_index": 0,
                            "explanation": s,
                            "source": f"{filename}, Page {page}"
                        })
                        q_id += 1
                        if len(questions) >= num_questions:
                            return questions

        # If we need more questions, create general factual questions
        for c in chunks:
            if len(questions) >= num_questions:
                break
            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', c["text"]) if len(s.strip()) > 50]
            if sentences:
                s = sentences[0]
                words = s.split()
                if len(words) > 8:
                    questions.append({
                        "id": q_id,
                        "question": f"Which of the following statements is directly confirmed in {filename} (Page {c['page']})?",
                        "options": [
                            f"A) {s[:95]}...",
                            "B) The system relies exclusively on unverified assumptions",
                            "C) This technology was discontinued in the early 1900s",
                            "D) The principles have no real-world application"
                        ],
                        "correct_index": 0,
                        "explanation": s,
                        "source": f"{filename}, Page {c['page']}"
                    })
                    q_id += 1

        return questions[:num_questions]

quiz_service = QuizService()
