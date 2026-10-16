from __future__ import annotations

import re
from typing import Any

FOLLOW_UP = {
    "annual follow up": re.compile(r"\bannual\s+follow\s*up\b", re.I),
    "close follow up": re.compile(r"\bclose\s+follow\s*up\b", re.I),
}
BIRADS = re.compile(r"\bB\s*I\s*[- ]?RADS?\s*([0-6]\s*[A-Ca-c]?)|\bBIRAD\s*([0-6]\s*[A-Ca-c]?)", re.I)


def explicit_facts(text: str) -> set[str]:
    facts = {label for label, pattern in FOLLOW_UP.items() if pattern.search(text or "")}
    for m in BIRADS.finditer(text or ""):
        facts.add("birads:" + re.sub(r"\s+", "", m.group(1) or m.group(2)).lower())
    return facts


def check_generated_answer(answer: str, evidence: list[dict[str, Any]], query_patient_id: str | None = None) -> dict[str, Any]:
    """Strict citation and explicit fact check over the exact supplied passages."""
    by_alias = {f"E{i}": row for i, row in enumerate(evidence, 1)}
    if query_patient_id and any(str(row.get("patient_id")) == str(query_patient_id) for row in evidence):
        return {"decision": "abstain", "claims_checked": 0, "problems": [{"status": "query_patient_leakage"}]}
    factual_lines = [line.strip() for line in (answer or "").splitlines() if line.strip()]
    claims = []
    problems = []
    for line in factual_lines:
        aliases = re.findall(r"\[(E\d+)\]", line)
        content = re.sub(r"\[(E\d+)\]", "", line).strip(" -*\t")
        if not content or content.lower().startswith(("answer:", "evidence:")):
            continue
        line_facts = explicit_facts(content)
        if not line_facts:
            # Reject nontrivial uncited claims; allow explicit insufficiency language.
            if re.search(r"\b(no explicit|not stated|insufficient|cannot determine)\b", content, re.I):
                continue
            problems.append({"claim": content[:200], "status": "unsupported_claim_type"})
            continue
        if not aliases:
            problems.append({"claim": content[:200], "status": "missing_citation"})
            continue
        cited_facts: set[str] = set()
        explicit_patient = re.search(r"\bpatient\s+([A-Za-z0-9_-]+)\b", content, re.I)
        cited_patient_ids = set()
        for alias in aliases:
            row = by_alias.get(alias)
            if row is None:
                problems.append({"claim": content[:200], "status": "invalid_citation", "citation": alias})
            else:
                cited_facts |= explicit_facts(str(row.get("text", "")))
                if row.get("patient_id") is not None:
                    cited_patient_ids.add(str(row["patient_id"]))
        if explicit_patient:
            mentioned = explicit_patient.group(1)
            if mentioned == str(query_patient_id) or cited_patient_ids != {mentioned}:
                problems.append({"claim": content[:200], "status": "patient_attribution_mismatch"})
        unsupported = sorted(line_facts - cited_facts)
        if unsupported:
            problems.append({"claim": content[:200], "status": "unsupported_explicit_fact", "facts": unsupported})
        claims.append({"text": content[:200], "citations": aliases, "facts": sorted(line_facts)})
    decision = "accept" if claims and not problems else "abstain"
    return {"decision": decision, "claims_checked": len(claims), "problems": problems}
