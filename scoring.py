"""
⚡ Priority Scoring Engine
============================
Deterministic scoring layer — Python controls priority, NOT the LLM.

Formula v1:
  Priority Score = Urgency + Impact + Staleness + Domain Weight

Design:
  - LLM provides classification and extraction
  - This module applies numerical scoring with transparent weights
  - All weights are tunable constants — iterate based on usefulness
"""

import logging
from datetime import datetime, timezone

log = logging.getLogger("keep_agent.scoring")

# ---------------------------------------------------------------------------
# Tunable Weights — adjust these based on what surfaces useful tasks
# ---------------------------------------------------------------------------

# Urgency: bonus for time-sensitive keywords
URGENCY_BASE_SCORE = 30
URGENCY_WORD_BONUS = {
    "today": 25,
    "now": 25,
    "immediately": 25,
    "urgent": 20,
    "asap": 20,
    "critical": 20,
    "deadline": 15,
    "overdue": 15,
    "tomorrow": 12,
    "this week": 10,
    "expires": 10,
    "final": 8,
    "last chance": 8,
    "soon": 5,
}

# Impact: domain-based importance weights
DOMAIN_IMPACT_WEIGHT = {
    "health": 25,
    "finance": 22,
    "career": 20,
    "admin": 15,
    "relationships": 12,
    "learning": 10,
    "personal_projects": 8,
    "uncategorised": 5,
}

# Staleness: older unactioned notes get boosted
# (days since last update → score)
STALENESS_THRESHOLDS = [
    (180, 20),  # 6+ months old → +20
    (90, 15),   # 3+ months old → +15
    (30, 10),   # 1+ month old → +10
    (14, 5),    # 2+ weeks old → +5
    (0, 0),     # Recent → no bonus
]

# Domain balance: expected minimum % of tasks per domain
# If a domain has fewer tasks than this %, it's "neglected"
DOMAIN_BALANCE_THRESHOLDS = {
    "health": 0.10,
    "career": 0.10,
    "finance": 0.08,
    "admin": 0.05,
    "relationships": 0.05,
    "learning": 0.05,
    "personal_projects": 0.05,
}


# ===========================================================================
# Scoring Functions
# ===========================================================================

def score_tasks(tasks: list[dict]) -> list[dict]:
    """
    Apply deterministic priority scoring to each task.
    Returns tasks sorted by priority_score (descending).
    """
    for task in tasks:
        urgency = _score_urgency(task)
        impact = _score_impact(task)
        staleness = _score_staleness(task)

        task["score_urgency"] = urgency
        task["score_impact"] = impact
        task["score_staleness"] = staleness
        task["priority_score"] = urgency + impact + staleness

    # Sort descending by priority score
    tasks.sort(key=lambda t: t["priority_score"], reverse=True)

    log.info(f"Scored {len(tasks)} tasks. Top score: {tasks[0]['priority_score']:.0f}" if tasks else "No tasks to score")
    return tasks


def _score_urgency(task: dict) -> float:
    """Score based on urgency signals detected by LLM."""
    score = 0.0

    if task.get("urgency_detected"):
        score += URGENCY_BASE_SCORE

    for word in task.get("urgency_words", []):
        word_lower = word.lower().strip()
        for key, bonus in URGENCY_WORD_BONUS.items():
            if key in word_lower:
                score += bonus
                break  # Only count each word once

    # Bonus if a specific deadline was detected
    if task.get("deadline_raw"):
        score += 10

    return min(score, 80)  # Cap urgency contribution


def _score_impact(task: dict) -> float:
    """Score based on life domain importance."""
    domain = task.get("domain", "uncategorised").lower()
    return DOMAIN_IMPACT_WEIGHT.get(domain, 5)


def _score_staleness(task: dict) -> float:
    """Score based on note age — older unactioned notes need attention."""
    # Try to parse the creation date from source note
    # The LLM extraction may not carry this forward, so we handle gracefully
    updated = task.get("note_updated_at") or task.get("created_at")

    if not updated:
        return 0

    try:
        if isinstance(updated, str):
            # Handle ISO format
            updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
        else:
            return 0

        now = datetime.now(timezone.utc)
        days_old = (now - updated_dt).days

        for threshold_days, bonus in STALENESS_THRESHOLDS:
            if days_old >= threshold_days:
                return bonus

    except (ValueError, TypeError):
        pass

    return 0


# ===========================================================================
# Domain Imbalance Detection
# ===========================================================================

def detect_domain_imbalance(tasks: list[dict]) -> list[str]:
    """
    Detect neglected life domains based on task distribution.
    Returns list of warning strings.
    """
    if not tasks:
        return ["⚠️ No tasks extracted — cannot assess domain balance"]

    # Count tasks per domain
    domain_counts = {}
    for t in tasks:
        d = t.get("domain", "uncategorised").lower()
        domain_counts[d] = domain_counts.get(d, 0) + 1

    total = len(tasks)
    warnings = []

    for domain, min_pct in DOMAIN_BALANCE_THRESHOLDS.items():
        actual_count = domain_counts.get(domain, 0)
        actual_pct = actual_count / total if total > 0 else 0

        if actual_count == 0:
            warnings.append(
                f"🚨 {domain.upper()}: Zero tasks detected — "
                f"this domain may be completely neglected"
            )
        elif actual_pct < min_pct:
            warnings.append(
                f"⚠️ {domain.upper()}: Only {actual_count} task(s) "
                f"({actual_pct:.0%}) — below {min_pct:.0%} threshold"
            )

    if not warnings:
        log.info("Domain balance looks healthy")
    else:
        log.warning(f"Detected {len(warnings)} domain imbalance(s)")

    return warnings
