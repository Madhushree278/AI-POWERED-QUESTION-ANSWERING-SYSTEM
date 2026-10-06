import os
import re
from typing import List, Dict, Any, Optional
from config import settings
from database.database import get_setting
from services.vector_store import vector_store_service

STYLE_PROMPTS = {
    "Concise": (
        "STYLE: CONCISE (1-3 sentences max).\n"
        "Provide a direct, high-impact answer without filler, preamble, or repetition. "
        "State the core facts and definitions directly."
    ),
    "Detailed": (
        "STYLE: DETAILED & COMPREHENSIVE.\n"
        "Provide an extensive, well-structured explanation organized with clear Markdown headings:\n"
        "### Overview\n"
        "### Detailed Breakdown\n"
        "### Supporting Evidence & Key Insights\n"
        "Provide thorough depth grounded entirely in the text."
    ),
    "Bullet Points": (
        "STYLE: BULLET POINTS.\n"
        "Format the response ENTIRELY as clean, structured bullet points.\n"
        "Every bullet point MUST begin with a bold topic heading (e.g., '- **Concept Name**: Detailed factual explanation...').\n"
        "Do not write large text paragraphs."
    ),
    "Summary": (
        "STYLE: EXECUTIVE SUMMARY.\n"
        "Provide an executive summary synthesizing the primary thesis, key findings, and conclusions "
        "from the retrieved documents in 2-3 focused paragraphs."
    ),
    "Simple Explanation": (
        "STYLE: SIMPLE EXPLANATION (ELI5).\n"
        "Explain the concept in simple, accessible, conversational language as if teaching a beginner. "
        "Break down complex jargon into intuitive ideas without losing accuracy."
    ),
    "Exam Answer": (
        "STYLE: ACADEMIC EXAM ANSWER.\n"
        "Format the answer strictly like a high-scoring university examination response:\n"
        "### 1. Definition & Theoretical Framework\n"
        "[Clear academic definition]\n\n"
        "### 2. Core Principles & Mechanisms\n"
        "[Detailed explanation of mechanisms]\n\n"
        "### 3. Textual Evidence & Applications\n"
        "[Specific examples and facts cited from the document]\n\n"
        "### 4. Summary & Evaluation\n"
        "[Academic synthesis]"
    ),
    "Step-by-Step": (
        "STYLE: STEP-BY-STEP BREAKDOWN.\n"
        "Present the explanation as a numbered, sequential breakdown (1., 2., 3., 4.).\n"
        "Each step should cover a distinct chronological or conceptual stage with bold step titles."
    ),
    "Key Points": (
        "STYLE: CORE KEY POINTS.\n"
        "Extract the top 5-7 most critical takeaways and core definitions.\n"
        "Use formatted bullet points with prominent bold highlights."
    )
}

class RAGEngine:
    def __init__(self):
        self.vector_store = vector_store_service

    def rewrite_query_for_context(self, question: str, chat_history: List[Dict[str, Any]]) -> str:
        """
        Rewrite follow-up questions into standalone search queries using conversation context.
        """
        if not chat_history:
            return question

        pronouns = [" it", " this", " that", " they", " these", " them", "its "]
        is_followup = (
            len(question.split()) <= 4 or 
            any(p in question.lower() for p in pronouns) or
            question.lower().startswith(("give an example", "why", "how", "what about", "explain more", "compare"))
        )

        if not is_followup:
            return question

        last_user_msg = ""
        for msg in reversed(chat_history):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if last_user_msg:
            clean_last = re.sub(r'^(what is|explain|define|tell me about)\s+', '', last_user_msg.lower()).strip('?')
            rewritten = f"{clean_last}: {question}"
            return rewritten

        return question

    def answer_question(
        self,
        question: str,
        doc_ids: Optional[List[str]] = None,
        chapter: Optional[str] = None,
        style: str = "Detailed",
        chat_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        End-to-end RAG pipeline with strict grounding and style formatting.
        """
        chat_history = chat_history or []
        rewritten_query = self.rewrite_query_for_context(question, chat_history)

        # 1. Retrieve top chunks from vector store
        chunks = self.vector_store.search(
            query=rewritten_query,
            doc_ids=doc_ids,
            chapter=chapter,
            top_k=settings.TOP_K
        )

        # 2. Check if relevant content was found
        if not chunks or (chunks and chunks[0]["score"] < 0.22):
            return {
                "answer": "I couldn't find this information in the uploaded documents.",
                "confidence": "Low",
                "sources": [],
                "rewritten_query": rewritten_query
            }

        # Calculate confidence
        top_score = chunks[0]["score"]
        if top_score >= 0.65:
            confidence = "High"
        elif top_score >= 0.40:
            confidence = "Medium"
        else:
            confidence = "Low"

        # Format sources
        sources = [
            {
                "doc_id": c["doc_id"],
                "filename": c["filename"],
                "page": c["page"],
                "chapter": c["chapter"],
                "score": round(c["score"] * 100, 1),
                "text": c["text"]
            }
            for c in chunks
        ]

        # 3. Build grounded prompt context
        context_parts = []
        for i, c in enumerate(chunks, 1):
            context_parts.append(
                f"[Source {i} | Document: {c['filename']} | Page: {c['page']} | Chapter: {c['chapter']}]\n{c['text']}\n"
            )
        context_str = "\n".join(context_parts)

        # 4. Generate answer via active LLM or local grounded synthesizer
        answer = self._generate_response(question, context_str, style, chat_history)

        return {
            "answer": answer,
            "confidence": confidence,
            "sources": sources,
            "rewritten_query": rewritten_query
        }

    def _generate_response(
        self,
        question: str,
        context: str,
        style: str,
        chat_history: List[Dict[str, Any]]
    ) -> str:
        """Call active LLM provider or fallback to local stylized synthesizer."""
        provider = get_setting("active_provider", settings.DEFAULT_PROVIDER)
        gemini_key = get_setting("gemini_api_key", settings.GEMINI_API_KEY)
        openai_key = get_setting("openai_api_key", settings.OPENAI_API_KEY)
        groq_key = get_setting("groq_api_key", settings.GROQ_API_KEY)

        style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["Detailed"])

        system_prompt = f"""You are DocuMind AI, an elite document intelligence and research assistant.
Your task is to answer the user's question STRICTLY based on the provided document excerpts below.

CRITICAL ANTI-HALLUCINATION & GROUNDING RULES:
1. Ground your answer ONLY in the provided Context Passages.
2. DO NOT invent facts, assumptions, page numbers, or external knowledge not found in the excerpts.
3. If the answer cannot be found in the context, you MUST say:
   "I couldn't find this information in the uploaded documents."
4. Cite sources directly in your explanation where appropriate (e.g. "[FileName, Page X]").
5. You MUST strictly format your output according to the requested STYLE instructions below.

{style_instruction}

CONTEXT PASSAGES:
{context}
"""

        # Google Gemini
        if (provider == "gemini" or not provider) and gemini_key:
            try:
                from google import genai
                client = genai.Client(api_key=gemini_key)
                model_name = get_setting("gemini_model", settings.GEMINI_MODEL)
                prompt = f"{system_prompt}\n\nUSER QUESTION: {question}\n\nANSWER (in requested style '{style}'):"
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                print(f"Gemini API error: {e}")

        # OpenAI
        if provider == "openai" and openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                model_name = get_setting("openai_model", settings.OPENAI_MODEL)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question}
                    ],
                    temperature=0.2
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"OpenAI API error: {e}")

        # Groq
        if provider == "groq" and groq_key:
            try:
                from groq import Groq
                client = Groq(api_key=groq_key)
                model_name = get_setting("groq_model", settings.GROQ_MODEL)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question}
                    ],
                    temperature=0.2
                )
                if response.choices and response.choices[0].message.content:
                    return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"Groq API error: {e}")

        # Local Grounded Stylized Synthesizer
        return self._local_grounded_synthesis(question, context, style)

    def _local_grounded_synthesis(self, question: str, context: str, style: str) -> str:
        """
        Robust offline synthesizer that structures extracted facts strictly according to the selected style.
        """
        sources_raw = context.split("[Source ")
        extracted_facts = []

        q_terms = set(re.findall(r'\w+', question.lower())) - {
            "what", "is", "the", "a", "an", "how", "why", "of", "in", "to", "for", "and", "or", "are", "does", "describe", "explain"
        }

        for block in sources_raw:
            if not block.strip():
                continue
            lines = block.strip().split("\n")
            header = lines[0] if lines else ""
            
            # Clean header to get filename and page
            m_header = re.search(r'Document:\s*([^|]+)\s*\|\s*Page:\s*(\d+)', header)
            source_tag = f"{m_header.group(1).strip()}, Page {m_header.group(2).strip()}" if m_header else "Document"

            content = " ".join(lines[1:])
            # Clean text: remove raw chapter headers embedded in text
            content = re.sub(r'^(?:Chapter\s+\d+:[^.]+\.\s*)+', '', content)

            sentences = re.split(r'(?<=[.!?])\s+', content)
            for s in sentences:
                s_clean = s.strip()
                # Skip title-like lines
                if len(s_clean) < 30 or s_clean.lower().startswith("author:"):
                    continue
                s_words = set(re.findall(r'\w+', s_clean.lower()))
                overlap = len(q_terms.intersection(s_words))
                if overlap > 0 or len(extracted_facts) < 2:
                    extracted_facts.append({
                        "source": source_tag,
                        "text": s_clean,
                        "overlap": overlap
                    })

        # Sort by relevance
        extracted_facts.sort(key=lambda x: x["overlap"], reverse=True)
        # Deduplicate
        unique_facts = []
        seen = set()
        for f in extracted_facts:
            key = f["text"][:60].lower()
            if key not in seen:
                seen.add(key)
                unique_facts.append(f)

        if not unique_facts:
            return "I couldn't find this information in the uploaded documents."

        top = unique_facts[:6]

        # ----------------- 1. CONCISE -----------------
        if style == "Concise":
            lead = top[0]["text"]
            if len(top) > 1 and len(lead) < 130:
                lead += " " + top[1]["text"]
            return f"{lead}\n\n*(Source: {top[0]['source']})*"

        # ----------------- 2. BULLET POINTS -----------------
        elif style == "Bullet Points":
            bullets = []
            for i, f in enumerate(top[:5], 1):
                # Extract subject heading
                words = f["text"].split()
                heading = " ".join(words[:4]).rstrip(':,.-')
                rest = " ".join(words[4:]) if len(words) > 4 else f["text"]
                bullets.append(f"- **{heading}**: {rest} `[{f['source']}]`")
            return "Here are the primary points from the uploaded documents:\n\n" + "\n".join(bullets)

        # ----------------- 3. EXAM ANSWER -----------------
        elif style == "Exam Answer":
            intro = top[0]["text"]
            points = "\n".join([f"- **Key Point {i+1}**: {f['text']} *(Reference: {f['source']})*" for i, f in enumerate(top[1:4])])
            conclusion = top[min(4, len(top)-1)]["text"]
            return (
                f"### 1. Definition & Core Concept\n{intro}\n\n"
                f"### 2. Principles & Detailed Evidence\n{points}\n\n"
                f"### 3. Conclusion & Summary\n{conclusion}"
            )

        # ----------------- 4. STEP-BY-STEP -----------------
        elif style == "Step-by-Step":
            steps = []
            for i, f in enumerate(top[:4], 1):
                steps.append(
                    f"#### Step {i}: Core Concept Analysis\n"
                    f"{f['text']}\n\n"
                    f"*Source: {f['source']}*"
                )
            return "### Sequential Breakdown\n\n" + "\n\n".join(steps)

        # ----------------- 5. SIMPLE EXPLANATION -----------------
        elif style == "Simple Explanation":
            lead = top[0]["text"]
            body = " ".join([f["text"] for f in top[1:3]])
            return (
                f"**In simple terms:**\n\n"
                f"{lead}\n\n"
                f"To understand further, the document explains that:\n\n"
                f"{body}\n\n"
                f"*(Source: {top[0]['source']})*"
            )

        # ----------------- 6. SUMMARY -----------------
        elif style == "Summary":
            lead = top[0]["text"]
            details = " ".join([f["text"] for f in top[1:4]])
            return f"### Executive Summary\n\n{lead}\n\n{details}\n\n*(Synthesized from: {top[0]['source']})*"

        # ----------------- 7. KEY POINTS -----------------
        elif style == "Key Points":
            points = []
            for i, f in enumerate(top[:5], 1):
                words = f["text"].split()
                tag = " ".join(words[:3]).strip(':')
                points.append(f"- **{tag}**: {f['text']} `({f['source']})`")
            return "### Essential Key Takeaways\n\n" + "\n".join(points)

        # ----------------- 8. DETAILED (Default) -----------------
        else:
            lead = top[0]["text"]
            sections = "\n\n".join([f"**Analysis {i+1}**: {f['text']} `[{f['source']}]`" for i, f in enumerate(top[1:5])])
            return (
                f"### Overview\n{lead}\n\n"
                f"### In-Depth Findings\n{sections}"
            )

rag_engine = RAGEngine()
