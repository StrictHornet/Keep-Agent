"""
🧠 LLM Extraction Layer
=========================
Handles all OpenAI API interaction for note classification.

Principles:
  - LLM does reasoning (classify, extract, deduplicate)
  - Output is STRICT JSON — no free-text drift
  - Chunk-aware to avoid token overflow
  - Validates response structure before returning
"""

import os
import json
import logging
from openai import OpenAI

log = logging.getLogger("keep_agent.llm")

# ---------------------------------------------------------------------------
# System Prompt — surgical constraints
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a task extraction and classification engine for personal notes.

YOUR JOB:
Analyse the provided Google Keep notes and classify each into exactly ONE category.

RULES — STRICT:
1. Convert vague notes into explicit, actionable task descriptions where possible.
2. Do NOT hallucinate deadlines that don't exist in the note.
3. Do NOT invent tasks — only extract what is clearly implied or stated.
4. Preserve original meaning — do not embellish.
5. Merge semantically similar tasks into one (note the originals in "merged_from").
6. Return ONLY valid JSON — no markdown, no commentary, no explanation.

CATEGORIES:
- tasks: Actionable items the user should do
- ideas: Creative thoughts, project concepts, wishes — not immediately actionable
- references: Information to keep (links, contacts, codes, recipes, addresses)
- vague: Notes too unclear to classify — need human clarification
- duplicates: Groups of notes that say essentially the same thing

DOMAIN TAGS (assign one to each task):
- health
- career
- finance
- learning
- relationships
- admin
- personal_projects
- uncategorised

URGENCY DETECTION — flag if ANY of these appear:
- Words: today, urgent, ASAP, now, immediately, deadline, overdue, critical
- Dates: any specific date or relative time reference
- Consequences: "or else", "last chance", "expires", "final"

OUTPUT SCHEMA (strict):
{
  "tasks": [
    {
      "task": "Clear, actionable description",
      "domain": "career",
      "urgency_detected": true,
      "urgency_words": ["deadline", "Friday"],
      "deadline_raw": "Friday" or null,
      "source_note_ids": ["note_0001"],
      "merged_from": [] or ["note_0002", "note_0003"],
      "original_snippet": "First 80 chars of original note"
    }
  ],
  "ideas": [
    {
      "title": "Short idea title",
      "content": "Idea description",
      "domain": "personal_projects",
      "source_note_id": "note_0005"
    }
  ],
  "references": [
    {
      "title": "What this reference is",
      "content": "The reference content",
      "source_note_id": "note_0010"
    }
  ],
  "vague": [
    {
      "title": "Original note title",
      "content": "Original note content (truncated)",
      "source_note_id": "note_0020",
      "reason": "Why it's unclear"
    }
  ],
  "duplicates": [
    {
      "canonical": "The best version of the duplicated content",
      "note_ids": ["note_0030", "note_0031"],
      "action": "merge" or "discard_older"
    }
  ]
}

RESPOND WITH ONLY THE JSON OBJECT. NO OTHER TEXT."""


def extract_and_classify(notes: list[dict]) -> dict | None:
    """
    Send a chunk of notes to OpenAI for classification.
    Returns validated structured dict or None on failure.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        log.error("OPENAI_API_KEY not set")
        return None

    client = OpenAI(api_key=api_key)

    # Format notes for the prompt
    notes_text = _format_notes_for_prompt(notes)

    user_prompt = f"""Analyse and classify these {len(notes)} Google Keep notes.

NOTES:
{notes_text}

Return ONLY the JSON classification object as specified."""

    try:
        log.info(f"Sending {len(notes)} notes to OpenAI for classification...")

        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,  # Low temp for deterministic classification
            response_format={"type": "json_object"},
            max_tokens=4096,
        )

        raw_output = response.choices[0].message.content
        log.debug(f"Raw LLM output (first 500 chars): {raw_output[:500]}")

        result = json.loads(raw_output)
        validated = _validate_result(result)

        if validated:
            log.info(
                f"LLM returned: {len(validated.get('tasks', []))} tasks, "
                f"{len(validated.get('ideas', []))} ideas, "
                f"{len(validated.get('vague', []))} vague"
            )
        return validated

    except json.JSONDecodeError as e:
        log.error(f"LLM returned invalid JSON: {e}")
        return None
    except Exception as e:
        log.error(f"OpenAI API error: {e}")
        return None


def _format_notes_for_prompt(notes: list[dict]) -> str:
    """Format notes into a clean text block for the LLM."""
    parts = []
    for note in notes:
        header = f"--- NOTE [{note['id']}] ---"
        title = f"Title: {note['title']}" if note['title'] else "Title: (none)"
        content = f"Content: {note['content'][:500]}"  # Truncate long notes
        created = f"Created: {note['created_at']}"
        updated = f"Updated: {note['updated_at']}"
        labels = f"Labels: {', '.join(note['labels'])}" if note['labels'] else ""

        entry = f"{header}\n{title}\n{content}\n{created}\n{updated}"
        if labels:
            entry += f"\n{labels}"
        parts.append(entry)

    return "\n\n".join(parts)


def _validate_result(result: dict) -> dict | None:
    """
    Validate the LLM output has the expected structure.
    Fixes minor issues, rejects garbage.
    """
    required_keys = ["tasks", "ideas", "references", "vague", "duplicates"]

    for key in required_keys:
        if key not in result:
            log.warning(f"Missing key '{key}' in LLM output — adding empty list")
            result[key] = []

    # Validate tasks have required fields
    valid_tasks = []
    for t in result["tasks"]:
        if isinstance(t, dict) and "task" in t:
            # Ensure defaults
            t.setdefault("domain", "uncategorised")
            t.setdefault("urgency_detected", False)
            t.setdefault("urgency_words", [])
            t.setdefault("deadline_raw", None)
            t.setdefault("source_note_ids", [])
            t.setdefault("merged_from", [])
            t.setdefault("original_snippet", "")
            valid_tasks.append(t)
        else:
            log.warning(f"Dropping malformed task: {t}")

    result["tasks"] = valid_tasks
    return result
