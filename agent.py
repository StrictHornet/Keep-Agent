#!/usr/bin/env python3
"""
🧠 Google Keep Intelligence Agent — Phase 1
=============================================
Personal AI OS | Epic 1 | Keep + Priority Summariser

Pipeline:
  Google Keep JSON → Parse → LLM Classification → Deterministic Scoring → Telegram Alert

Architecture Principles:
  - LLM does reasoning (classification, extraction, dedup)
  - Python does control (scoring, ranking, validation)
  - Never let LLM control priority fully

Usage:
  # Local
  export OPENAI_API_KEY="sk-..."
  export TELEGRAM_BOT_TOKEN="123456:ABC..."
  export TELEGRAM_CHAT_ID="your_chat_id"
  python agent.py

  # GitHub Actions — see .github/workflows/run.yml
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from llm_extractor import extract_and_classify
from scoring import score_tasks, detect_domain_imbalance
from telegram_notify import send_telegram_message

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
KEEP_DATA_PATH = Path(os.getenv("KEEP_DATA_PATH", "keep_data/"))
MAX_NOTES_PER_CHUNK = 30  # avoid token overflow — chunk large exports
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("keep_agent")


# ===========================================================================
# 1. PARSE — Load & normalise Google Keep export
# ===========================================================================

def load_keep_notes(data_path: Path) -> list[dict]:
    """
    Load notes from Google Takeout Keep export.
    Supports both:
      - Single JSON file (keep_data.json)
      - Directory of individual .json note files (Takeout format)
    
    Normalises each note to:
    {
        "id": str,
        "title": str,
        "content": str,
        "created_at": str (ISO),
        "updated_at": str (ISO),
        "labels": list[str],
        "is_archived": bool,
        "is_trashed": bool,
        "raw": dict
    }
    """
    notes = []

    if data_path.is_file() and data_path.suffix == ".json":
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        raw_notes = raw if isinstance(raw, list) else [raw]
    elif data_path.is_dir():
        raw_notes = []
        for f in sorted(data_path.glob("*.json")):
            try:
                raw_notes.append(json.loads(f.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                log.warning(f"Skipping malformed file: {f.name}")
    else:
        log.error(f"Keep data path not found: {data_path}")
        sys.exit(1)

    for i, raw in enumerate(raw_notes):
        # Google Takeout uses 'textContent' or 'listContent'
        content_parts = []
        if "textContent" in raw:
            content_parts.append(raw["textContent"])
        if "listContent" in raw:
            for item in raw["listContent"]:
                text = item.get("text", "")
                checked = item.get("isChecked", False)
                prefix = "✅" if checked else "☐"
                content_parts.append(f"{prefix} {text}")

        content = "\n".join(content_parts).strip()
        title = raw.get("title", "").strip()

        # Skip empty notes and trashed notes
        if not content and not title:
            continue
        if raw.get("isTrashed", False):
            continue

        # Timestamps — Takeout uses microseconds
        created = _parse_timestamp(raw.get("createdTimestampUsec") or raw.get("created_at"))
        updated = _parse_timestamp(raw.get("userEditedTimestampUsec") or raw.get("updated_at") or raw.get("createdTimestampUsec"))

        labels = [l.get("name", "") for l in raw.get("labels", [])]

        notes.append({
            "id": raw.get("id", f"note_{i:04d}"),
            "title": title,
            "content": content,
            "created_at": created,
            "updated_at": updated,
            "labels": labels,
            "is_archived": raw.get("isArchived", False),
            "is_trashed": False,
            "raw": raw,
        })

    log.info(f"Loaded {len(notes)} notes from {data_path}")
    return notes


def _parse_timestamp(ts) -> str:
    """Convert Takeout microsecond timestamp or ISO string to ISO format."""
    if ts is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(ts, (int, float)):
        # Takeout gives microseconds since epoch
        if ts > 1e15:
            ts = ts / 1_000_000
        elif ts > 1e12:
            ts = ts / 1_000
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    return str(ts)


def chunk_notes(notes: list[dict], chunk_size: int = MAX_NOTES_PER_CHUNK) -> list[list[dict]]:
    """Split notes into chunks to avoid LLM token limits."""
    return [notes[i:i + chunk_size] for i in range(0, len(notes), chunk_size)]


# ===========================================================================
# 2. PROCESS — Orchestrate LLM extraction + deterministic scoring
# ===========================================================================

def process_notes(notes: list[dict]) -> dict:
    """
    Full pipeline:
      1. Chunk notes
      2. LLM classifies each chunk → tasks, ideas, references, vague, duplicates
      3. Merge chunk results
      4. Deterministic scoring on extracted tasks
      5. Domain imbalance detection
    """
    all_tasks = []
    all_ideas = []
    all_references = []
    all_vague = []
    all_duplicates = []

    chunks = chunk_notes(notes)
    log.info(f"Processing {len(notes)} notes in {len(chunks)} chunk(s)")

    for i, chunk in enumerate(chunks):
        log.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk)} notes)")
        result = extract_and_classify(chunk)

        if not result:
            log.warning(f"Chunk {i+1} returned empty result — skipping")
            continue

        # Validate structure
        all_tasks.extend(result.get("tasks", []))
        all_ideas.extend(result.get("ideas", []))
        all_references.extend(result.get("references", []))
        all_vague.extend(result.get("vague", []))
        all_duplicates.extend(result.get("duplicates", []))

    log.info(
        f"Extraction complete: {len(all_tasks)} tasks, {len(all_ideas)} ideas, "
        f"{len(all_references)} refs, {len(all_vague)} vague, {len(all_duplicates)} duplicate groups"
    )

    # Deterministic scoring — Python controls priority, not LLM
    scored_tasks = score_tasks(all_tasks)
    domain_warnings = detect_domain_imbalance(scored_tasks)

    return {
        "tasks": scored_tasks,
        "ideas": all_ideas,
        "references": all_references,
        "vague": all_vague,
        "duplicates": all_duplicates,
        "domain_warnings": domain_warnings,
        "stats": {
            "total_notes": len(notes),
            "tasks_extracted": len(all_tasks),
            "ideas_extracted": len(all_ideas),
            "vague_count": len(all_vague),
            "duplicate_groups": len(all_duplicates),
            "domains_neglected": len(domain_warnings),
        }
    }


# ===========================================================================
# 3. OUTPUT — Format & send Telegram notification
# ===========================================================================

def format_telegram_message(result: dict) -> str:
    """
    Build a clean, decision-ready Telegram message.
    Signal, not commentary.
    """
    stats = result["stats"]
    tasks = result["tasks"]
    top_tasks = tasks[:5]  # Top 3–5 priorities

    lines = []
    lines.append("🧠 *KEEP INTELLIGENCE BRIEF*")
    lines.append(f"_{datetime.now().strftime('%A, %d %B %Y')}_")
    lines.append("")

    # --- Top Priorities ---
    if top_tasks:
        lines.append("🎯 *TOP PRIORITIES*")
        for i, t in enumerate(top_tasks, 1):
            domain_tag = f"[{t.get('domain', '?')}]"
            score = t.get("priority_score", 0)
            lines.append(f"  {i}. {t['task']}  {domain_tag}  ⚡{score:.0f}")
        lines.append("")

    # --- Domain Warnings ---
    if result["domain_warnings"]:
        lines.append("⚠️ *NEGLECTED DOMAINS*")
        for w in result["domain_warnings"]:
            lines.append(f"  • {w}")
        lines.append("")

    # --- Stats ---
    lines.append("📊 *SCAN SUMMARY*")
    lines.append(f"  Notes scanned: {stats['total_notes']}")
    lines.append(f"  Tasks extracted: {stats['tasks_extracted']}")
    lines.append(f"  Vague notes: {stats['vague_count']}")
    lines.append(f"  Duplicate groups: {stats['duplicate_groups']}")

    if result["vague"]:
        lines.append("")
        lines.append("🌫️ *VAGUE NOTES (need clarity)*")
        for v in result["vague"][:5]:
            snippet = v.get("content", v.get("title", ""))[:60]
            lines.append(f"  • _{snippet}_...")

    return "\n".join(lines)


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    log.info("=" * 60)
    log.info("🧠 Keep Intelligence Agent — Starting")
    log.info("=" * 60)

    # 1. Load
    notes = load_keep_notes(KEEP_DATA_PATH)
    if not notes:
        log.error("No notes found. Exiting.")
        sys.exit(1)

    # 2. Process
    result = process_notes(notes)

    # 3. Save full results to JSON (for audit / future phases)
    output_path = Path("output/keep_analysis.json")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    log.info(f"Full analysis saved to {output_path}")

    # 4. Notify
    message = format_telegram_message(result)
    print("\n" + message + "\n")

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if telegram_token and telegram_chat_id:
        success = send_telegram_message(message, telegram_token, telegram_chat_id)
        if success:
            log.info("✅ Telegram notification sent")
        else:
            log.error("❌ Telegram notification failed")
    else:
        log.warning("Telegram credentials not set — skipping notification")
        log.warning("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable")

    log.info("🧠 Keep Intelligence Agent — Complete")


if __name__ == "__main__":
    main()
