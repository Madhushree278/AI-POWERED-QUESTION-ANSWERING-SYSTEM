import re
import json
from typing import List, Dict, Any, Optional
from config import settings
from database.database import get_setting, get_document
from services.vector_store import vector_store_service

STOP_WORDS = {
    'it', 'this', 'that', 'these', 'those', 'they', 'we', 'our', 'you', 'he', 'she',
    'who', 'which', 'what', 'there', 'here', 'also', 'during', 'overall', 'another',
    'such', 'both', 'each', 'all', 'any', 'some', 'one', 'two', 'first', 'second',
    'need', 'purpose', 'the', 'a', 'an', 'and', 'or', 'in', 'to', 'for', 'with',
    'by', 'from', 'at', 'on', 'about', 'into', 'through', 'after', 'over', 'between',
    'out', 'against', 'without', 'before', 'under', 'around', 'among', 'so', 'then',
    'internship', 'company', 'application', 'scope', 'organization', 'student',
    'system', 'report', 'department', 'project', 'approach', 'training', 'learning opportunities'
}

BOILERPLATE_PHRASES = [
    'bonafide certificate', 'to certify that', 'submitted by', 'partial fulfillment',
    'departmental review', 'internal guide', 'external guide', 'head of department',
    'principal', 'institute of engineering', 'academic year', 'bonafide student',
    'acknowledgement', 'express our thanks', 'moral support', 'signature', 'confirmation letter'
]

class ConceptMapService:
    def __init__(self):
        self.vector_store = vector_store_service

    def generate_concept_map(
        self,
        doc_ids: List[str],
        focus_topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dynamically generate an interconnected concept map from actual uploaded document content.
        Identifies main topic, subtopics, key concepts, explanations, and relationships.
        """
        if not doc_ids:
            return {
                "error": "No documents specified for concept map generation.",
                "nodes": [],
                "edges": [],
                "main_topic": "No Document Selected"
            }

        all_chunks: List[Dict[str, Any]] = []
        doc_names_map: Dict[str, str] = {}

        for doc_id in doc_ids:
            doc = get_document(doc_id)
            if doc:
                doc_names_map[doc_id] = doc["filename"]
            chunks = self.vector_store.get_document_chunks(doc_id, limit=250)
            all_chunks.extend(chunks)

        if not all_chunks:
            return {
                "error": "No text content found in selected document(s) to generate concept map.",
                "nodes": [],
                "edges": [],
                "main_topic": "No Content Found"
            }

        # Filter boilerplate chunks (certificates, signatures, acknowledgements)
        content_chunks = []
        for c in all_chunks:
            t_lower = c["text"].lower()
            if any(bp in t_lower for bp in BOILERPLATE_PHRASES):
                continue
            content_chunks.append(c)

        if not content_chunks:
            content_chunks = all_chunks

        # Sample representative chunks across the document(s)
        if len(content_chunks) > 40:
            step = max(1, len(content_chunks) // 35)
            sampled_chunks = content_chunks[::step][:35]
        else:
            sampled_chunks = content_chunks

        # Build context lines
        context_lines = []
        for c in sampled_chunks:
            fname = c.get("filename") or doc_names_map.get(c.get("doc_id", ""), "Document")
            page = c.get("page", 1)
            ch = c.get("chapter", "")
            context_lines.append(f"[Document: {fname} | Page: {page} | Chapter: {ch}]: {c['text']}")

        context = "\n\n".join(context_lines)

        # 1. Attempt LLM generation
        result = self._generate_with_llm(context, list(doc_names_map.values()), focus_topic)
        if result and result.get("nodes") and len(result["nodes"]) >= 3:
            result["doc_names"] = list(doc_names_map.values())
            # Ensure every node has source_doc and source_page
            primary_fname = list(doc_names_map.values())[0] if doc_names_map else "Document"
            for n in result["nodes"]:
                if not n.get("source_doc"):
                    n["source_doc"] = primary_fname
                if not n.get("source_page"):
                    n["source_page"] = 1
            return result

        # 2. Heuristic fallback directly from document content
        return self._generate_local(content_chunks, list(doc_names_map.values()), focus_topic)

    def _generate_with_llm(
        self,
        context: str,
        filenames: List[str],
        focus_topic: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        provider = get_setting("active_provider", settings.DEFAULT_PROVIDER)
        gemini_key = get_setting("gemini_api_key", settings.GEMINI_API_KEY)
        openai_key = get_setting("openai_api_key", settings.OPENAI_API_KEY)
        groq_key = get_setting("groq_api_key", settings.GROQ_API_KEY)

        target_docs = ", ".join(filenames) if filenames else "the document"
        topic_instruction = f"Focus particularly on the topic '{focus_topic}'." if focus_topic else "Capture the central architecture and major concepts."

        prompt = f"""You are an elite knowledge graph architect and academic concept mapper.
Your task is to analyze the following excerpts from {target_docs} and construct an interconnected concept map.
{topic_instruction}

STRICT RULES:
1. Base your concepts and relationships strictly on the provided text. Do not invent facts or outside theories.
2. Return ONLY a single valid JSON object. Do not wrap in markdown or backticks (e.g. no ```json).

JSON SCHEMA:
{{
  "main_topic": "Clear central title for the map",
  "summary": "1-2 sentence overview of the concept landscape",
  "nodes": [
    {{
      "id": "node_1",
      "label": "Concise concept name (2-4 words)",
      "category": "root" | "subtopic" | "concept" | "method" | "application",
      "explanation": "2-3 sentence grounded explanation of this concept from the document.",
      "source_doc": "Filename where discussed",
      "source_page": 1
    }}
  ],
  "edges": [
    {{
      "source": "node_1",
      "target": "node_2",
      "label": "Short relationship verb/phrase (e.g. 'comprises', 'utilizes', 'implements', 'defines', 'analyzes')"
    }}
  ]
}}

Generate between 8 and 14 meaningful concept nodes and 10 to 18 interconnected edges.
Ensure every node is connected to at least one edge.

EXCERPTS FROM DOCUMENTS:
{context[:25000]}
"""

        raw_text = ""
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
                    raw_text = response.text.strip()
            except Exception as e:
                print(f"Gemini concept map error: {e}")

        # OpenAI
        if not raw_text and provider == "openai" and openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                model_name = get_setting("openai_model", settings.OPENAI_MODEL)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a concept map generator outputting strictly valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2
                )
                if response.choices and response.choices[0].message.content:
                    raw_text = response.choices[0].message.content.strip()
            except Exception as e:
                print(f"OpenAI concept map error: {e}")

        # Groq
        if not raw_text and provider == "groq" and groq_key:
            try:
                from groq import Groq
                client = Groq(api_key=groq_key)
                model_name = get_setting("groq_model", settings.GROQ_MODEL)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a concept map generator outputting strictly valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2
                )
                if response.choices and response.choices[0].message.content:
                    raw_text = response.choices[0].message.content.strip()
            except Exception as e:
                print(f"Groq concept map error: {e}")

        if not raw_text:
            return None

        # Clean JSON markdown if present
        clean_json = re.sub(r'^```(?:json)?\s*', '', raw_text.strip())
        clean_json = re.sub(r'\s*```$', '', clean_json.strip())

        # Extract JSON object using regex if wrapped in conversation
        match = re.search(r'\{[\s\S]*\}', clean_json)
        if match:
            clean_json = match.group(0)

        try:
            parsed = json.loads(clean_json)
            if "nodes" in parsed and "edges" in parsed and len(parsed["nodes"]) >= 3:
                return parsed
        except Exception as e:
            print(f"Failed to parse LLM concept map JSON: {e}")

        return None

    def _clean_term(self, t: str) -> str:
        t = re.sub(r'^(?:the|a|an|in|during|also|and|or|for|to|with|by|from|at|on)\s+', '', t.strip(), flags=re.IGNORECASE).strip()
        t = re.sub(r'^\d+[\.\)]\s*', '', t).strip()
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    def _determine_category(self, label: str) -> str:
        ll = label.lower()
        if any(w in ll for w in ["app", "pilot", "system", "platform", "tool", "dashboard", "service", "interface"]):
            return "application"
        if any(w in ll for w in ["algorithm", "model", "learning", "network", "ast", "generator", "tree", "parser", "pipeline", "framework"]):
            return "method"
        if any(w in ll for w in ["phase", "overview", "domain", "architecture", "activities", "profile"]):
            return "subtopic"
        return "concept"

    def _generate_local(
        self,
        chunks: List[Dict[str, Any]],
        filenames: List[str],
        focus_topic: Optional[str]
    ) -> Dict[str, Any]:
        """
        Grounded heuristic concept map builder directly parsing actual document text chunks.
        Extracts entities, definition sentences, and hierarchical relationships.
        """
        primary_filename = filenames[0] if filenames else "Document"

        # 1. Determine Main Topic
        main_topic = focus_topic
        if not main_topic:
            # Look for a meaningful title line across the first 4 chunks
            for chunk in chunks[:4]:
                lines = [line.strip() for line in chunk["text"].split("\n") if line.strip()]
                for line in lines:
                    clean_l = re.sub(r'^\s*\d+\s*', '', line).strip()
                    generic_headings = {"executive summary", "table of contents", "contents", "preface", "foreword", "abstract", "acknowledgement", "introduction", "background", "company introduction", "bonafide certificate", "confirmation letter"}
                    if (
                        4 <= len(clean_l) <= 50
                        and any(c.isalpha() for c in clean_l)
                        and clean_l[0].isupper()
                        and not clean_l.endswith(('.', ',', ';', ':', '?', '!'))
                        and len(clean_l.split()) <= 6
                        and clean_l.lower().split()[0] not in STOP_WORDS
                        and not clean_l.lower().startswith(("author", "page", "chapter", "table", "submitted", "bonafide", "certificate"))
                        and clean_l.lower() not in STOP_WORDS
                        and clean_l.lower() not in generic_headings
                    ):
                        main_topic = clean_l
                        break
                if main_topic:
                    break

        if not main_topic:
            clean_name = primary_filename.replace(".pdf", "").replace(".docx", "").replace(".txt", "").replace("_", " ")
            main_topic = re.sub(r'^[a-f0-9\-]{36}_', '', clean_name).title()

        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        seen_labels = set()

        # Root Node
        root_id = "node_root"
        root_page = chunks[0].get("page", 1) if chunks else 1
        nodes.append({
            "id": root_id,
            "label": main_topic[:32],
            "category": "root",
            "explanation": f"Central topic and foundational knowledge domain covered across {', '.join(filenames)}.",
            "source_doc": chunks[0].get("filename", primary_filename) if chunks else primary_filename,
            "source_page": root_page
        })
        seen_labels.add(main_topic.lower())

        # 2. Extract Subtopics / Chapters / Thematic Sections
        chapter_nodes_map: Dict[str, str] = {}
        for chunk in chunks:
            ch = chunk.get("chapter")
            if ch and ch not in ["General Content", "All Chapters"]:
                clean_ch = re.sub(r'^Chapter\s*\d+\s*:\s*', '', ch).strip()
                ch_key = clean_ch.lower()
                if ch_key not in seen_labels and len(chapter_nodes_map) < 4:
                    node_id = f"subtopic_{len(chapter_nodes_map) + 1}"
                    nodes.append({
                        "id": node_id,
                        "label": clean_ch[:30],
                        "category": "subtopic",
                        "explanation": f"Major thematic section discussing {clean_ch} within {chunk.get('filename', primary_filename)}.",
                        "source_doc": chunk.get("filename", primary_filename),
                        "source_page": chunk.get("page", 1)
                    })
                    seen_labels.add(ch_key)
                    chapter_nodes_map[ch] = node_id
                    edges.append({
                        "source": root_id,
                        "target": node_id,
                        "label": "comprises"
                    })

        # 3. Extract Definitions & Key Concepts using high-yield patterns
        # Pattern A: "Term (Acronym): Definition" or "Term: Definition"
        term_def_pattern = re.compile(
            r'\b([A-Z][A-Za-z0-9_\s]{1,30}(?:\s*\([A-Za-z0-9\s]{2,15}\))?):\s+([A-Z][^.\n]{20,240}\.)'
        )

        # Pattern B: "Term is a / refers to / consists of / utilizes ..."
        verbs = r'(?:is defined as|refers to|is a specialized|is a Python module used to|is a Python module|is a mobile application|is a technology that|is an artificial intelligence|is a branch of|is a subset of|consists of|utilizes|relies on|is used to analyze|is used to develop|is designed to|focuses on|enables|provides)'
        inline_def_pattern = re.compile(
            rf'\b([A-Z][A-Za-z0-9_\-\s]{{2,30}}?)\s+({verbs})\s+([^.\n]{{20,180}})',
            re.IGNORECASE
        )

        # Pattern C: Acronym extraction "Full Name (ACR)"
        acronym_pattern = re.compile(
            r'\b([A-Z][a-zA-Z\s]{3,28})\s*\(([A-Z]{2,6})\)'
        )

        concept_counter = 1

        for chunk in chunks:
            text = chunk["text"]
            fname = chunk.get("filename", primary_filename)
            page = chunk.get("page", 1)
            ch = chunk.get("chapter", "")
            parent_id = chapter_nodes_map.get(ch, root_id)

            # Match Pattern A: Term: Definition
            norm_text = re.sub(r'\s+', ' ', text)
            for raw_term, explanation in term_def_pattern.findall(norm_text):
                clean_t = self._clean_term(raw_term)
                if len(clean_t) < 3 or len(clean_t) > 32 or clean_t.lower() in seen_labels:
                    continue
                first_w = clean_t.lower().split()[0]
                if (
                    first_w in STOP_WORDS
                    or clean_t.lower() in STOP_WORDS
                    or clean_t.lower().startswith(('and ', 'also ', 'or ', 'it ', 'this ', 'that ', 's '))
                    or clean_t.lower().endswith((' also', ' internship', ' company', ' letter'))
                    or any(bp in clean_t.lower() for bp in BOILERPLATE_PHRASES)
                    or any(w in clean_t.lower() for w in ['address', 'activities phase', 'wise activities', 'oriented applications', 'learning opportunities', 'review meeting', 'bonafide'])
                ):
                    continue

                node_id = f"concept_{concept_counter}"
                concept_counter += 1
                cat = self._determine_category(clean_t)
                nodes.append({
                    "id": node_id,
                    "label": clean_t,
                    "category": cat,
                    "explanation": f"{clean_t}: {explanation.strip()}",
                    "source_doc": fname,
                    "source_page": page
                })
                seen_labels.add(clean_t.lower())
                edges.append({
                    "source": parent_id,
                    "target": node_id,
                    "label": "defines" if cat == "concept" else "implements"
                })

                if len(nodes) >= 12:
                    break

            if len(nodes) >= 12:
                break

            # Match Pattern B: Inline definitions
            for raw_term, verb, explanation in inline_def_pattern.findall(norm_text):
                clean_t = self._clean_term(raw_term)
                if len(clean_t) < 3 or len(clean_t) > 32 or clean_t.lower() in seen_labels:
                    continue
                first_w = clean_t.lower().split()[0]
                if (
                    first_w in STOP_WORDS
                    or clean_t.lower() in STOP_WORDS
                    or clean_t.lower().startswith(('and ', 'also ', 'or ', 'it ', 'this ', 'that ', 's '))
                    or clean_t.lower().endswith((' also', ' internship', ' company', ' letter'))
                    or any(bp in clean_t.lower() for bp in BOILERPLATE_PHRASES)
                    or any(w in clean_t.lower() for w in ['address', 'activities phase', 'wise activities', 'oriented applications', 'learning opportunities', 'review meeting', 'bonafide'])
                ):
                    continue

                node_id = f"concept_{concept_counter}"
                concept_counter += 1
                cat = self._determine_category(clean_t)
                full_exp = f"{clean_t} {verb.strip()} {explanation.strip()}."
                nodes.append({
                    "id": node_id,
                    "label": clean_t,
                    "category": cat,
                    "explanation": full_exp,
                    "source_doc": fname,
                    "source_page": page
                })
                seen_labels.add(clean_t.lower())
                edge_label = verb.lower().strip()
                if len(edge_label) > 16:
                    edge_label = "utilizes"
                edges.append({
                    "source": parent_id,
                    "target": node_id,
                    "label": edge_label
                })

                if len(nodes) >= 12:
                    break

            if len(nodes) >= 12:
                break

            # Match Pattern C: Acronyms
            for full_name, acr in acronym_pattern.findall(norm_text):
                clean_full = self._clean_term(full_name)
                combined = f"{acr} ({clean_full})"
                if acr.lower() in seen_labels or clean_full.lower() in seen_labels:
                    continue
                if len(clean_full) < 3 or any(sw in clean_full.lower().split() for sw in ['page', 'figure', 'table', 'section']):
                    continue

                node_id = f"concept_{concept_counter}"
                concept_counter += 1
                cat = self._determine_category(clean_full)

                # Find surrounding sentence for grounded explanation
                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', norm_text) if acr in s or clean_full in s]
                exp = sentences[0] if sentences else f"{clean_full} ({acr}) is a foundational framework discussed in the document."

                nodes.append({
                    "id": node_id,
                    "label": combined[:30],
                    "category": cat,
                    "explanation": exp[:220],
                    "source_doc": fname,
                    "source_page": page
                })
                seen_labels.add(acr.lower())
                seen_labels.add(clean_full.lower())
                edges.append({
                    "source": parent_id,
                    "target": node_id,
                    "label": "utilizes"
                })

                if len(nodes) >= 12:
                    break

            if len(nodes) >= 12:
                break

        # Fallback if very few concepts extracted
        if len(nodes) < 5:
            for chunk in chunks:
                fname = chunk.get("filename", primary_filename)
                page = chunk.get("page", 1)
                norm_text = re.sub(r'\s+', ' ', chunk["text"])
                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', norm_text) if 40 <= len(s.strip()) <= 200]
                for s in sentences:
                    m = re.match(r'^([A-Z][a-zA-Z0-9_\-\s]{2,24}?)\s+([a-z].*)', s)
                    if m:
                        term = self._clean_term(m.group(1))
                        if (
                            len(term) >= 3
                            and len(term.split()) <= 4
                            and term.lower() not in seen_labels
                            and term.lower().split()[0] not in STOP_WORDS
                        ):
                            node_id = f"concept_{concept_counter}"
                            concept_counter += 1
                            nodes.append({
                                "id": node_id,
                                "label": term,
                                "category": "concept",
                                "explanation": s,
                                "source_doc": fname,
                                "source_page": page
                            })
                            seen_labels.add(term.lower())
                            edges.append({
                                "source": root_id,
                                "target": node_id,
                                "label": "introduces"
                            })
                    if len(nodes) >= 8:
                        break
                if len(nodes) >= 8:
                    break

        # Connect related sibling nodes to produce an interconnected knowledge graph
        if len(nodes) >= 4:
            for i in range(1, len(nodes) - 1):
                if i % 2 == 1:
                    edges.append({
                        "source": nodes[i]["id"],
                        "target": nodes[i + 1]["id"],
                        "label": "relates to"
                    })

        return {
            "main_topic": main_topic,
            "summary": f"Interconnected concept map dynamically generated from {', '.join(filenames)} featuring {len(nodes)} core concept nodes and {len(edges)} semantic relationships.",
            "doc_names": filenames,
            "nodes": nodes,
            "edges": edges
        }

concept_map_service = ConceptMapService()
