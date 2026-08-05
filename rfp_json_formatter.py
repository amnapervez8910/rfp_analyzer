"""
rfp_json_formatter.py
=====================================================
Takes the raw markdown report produced by rfp_core.analyze_rfp_headless()
and turns it into a clean, structured JSON-serializable dict, with a
separate key for each deliverable output section — exactly what was
requested: "deliverables ka alag section, evaluation ka alag,
checklist ka alag, scoring/decision ka alag".
=====================================================
"""

import re


# ---------------------------------------------------
# Split the raw markdown report into its top-level sections
# by the exact "# HEADING" markers rfp_core's prompts always produce.
# ---------------------------------------------------

_SECTION_MARKERS = [
    ("deliverables", r"#\s*DELIVERABLES"),
    ("evaluation_criteria", r"#\s*EVALUATION CRITERIA"),
    ("compliance_checklist", r"#\s*COMPLIANCE CHECKLIST"),
    ("scoring_summary", r"#\s*SCORING SUMMARY"),
    ("decision", r"#\s*QUALIFICATION DECISION"),
]


def _split_raw_sections(raw_report: str):
    positions = []
    for key, pattern in _SECTION_MARKERS:
        m = re.search(pattern, raw_report, re.IGNORECASE)
        if m:
            positions.append((m.start(), key))
    positions.sort(key=lambda x: x[0])

    chunks = {}
    for i, (start, key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(raw_report)
        chunks[key] = raw_report[start:end].strip()
    return chunks


# ---------------------------------------------------
# DELIVERABLES: "## Parent" + "- Name :: Desc :: Deadline :: Page :: Ref :: Doc :: Section"
# ---------------------------------------------------


def _parse_deliverables(section_text: str):
    categories = []
    if not section_text:
        return categories

    parent_blocks = re.split(r"\n##\s+", section_text)
    for block in parent_blocks[1:]:  # skip text before first "## "
        lines = block.strip().splitlines()
        if not lines:
            continue
        category_name = lines[0].strip()
        items = []
        for line in lines[1:]:
            line = line.strip()
            if not line.startswith("-"):
                continue
            parts = [p.strip() for p in line.lstrip("-").split("::")]
            parts += [""] * (8 - len(parts))  # pad if model dropped a field
            requirement_type = parts[7].strip() if parts[7].strip() else "Mandatory"
            items.append({
                "name": parts[0],
                "description": parts[1],
                "deadline": parts[2],
                "page_number": parts[3],
                "reference": parts[4],
                "document_name": parts[5],
                "section_name": parts[6],
                "requirement_type": requirement_type,
            })
        categories.append({"category": category_name, "items": items})
    return categories


# ---------------------------------------------------
# EVALUATION CRITERIA:
# Nested structure — top-level "## Group Name" sections (e.g. "Evaluation at
# a Glance", "1. Technical Evaluation Criteria", "5. Disqualification
# Conditions"), where most groups contain repeated "### Card Title" blocks
# with "- **Field:** value" lines, and a couple (the glance summary, the
# thresholds list) are just "- **Field:** value" bullets directly.
# ---------------------------------------------------


def _heading_to_key(heading: str):
    """Turn '1. Technical Evaluation Criteria' -> ('technical_evaluation_criteria', 'Technical Evaluation Criteria')."""
    title = re.sub(r"^\d+\.\s*", "", heading).strip()
    key = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    return key or "section", title


def _parse_field_lines(text: str):
    """Parse '- **Label:** value' lines into {label_key: value}."""
    fields = {}
    for m in re.finditer(r"-\s*\*\*(.+?):\*\*\s*(.*)", text):
        label = m.group(1).strip()
        value = m.group(2).strip()
        label_key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if label_key:
            fields[label_key] = value
    return fields


def _parse_evaluation_cards(body: str):
    """Split a group's body into repeated '### Card Title' blocks."""
    cards = []
    parts = re.split(r"\n###\s+", body)
    for part in parts[1:]:
        lines = part.strip().splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        card_body = "\n".join(lines[1:])
        fields = _parse_field_lines(card_body)
        fields["title"] = title
        cards.append(fields)
    return cards


def _parse_evaluation(section_text: str):
    result = {}
    if not section_text:
        return result

    groups = re.split(r"\n##\s+", section_text)
    for group in groups[1:]:  # skip preamble/"# EVALUATION CRITERIA" heading
        lines = group.strip().splitlines()
        if not lines:
            continue
        heading = lines[0].strip()
        body = "\n".join(lines[1:])
        key, title = _heading_to_key(heading)

        if re.search(r"\n###\s+", "\n" + body):
            result[key] = {"title": title, "items": _parse_evaluation_cards(body)}
        else:
            fields = _parse_field_lines(body)
            if fields:
                result[key] = {"title": title, **fields}
            else:
                result[key] = {"title": title, "content": body.strip()}
    return result


# ---------------------------------------------------
# COMPLIANCE CHECKLIST: "## TEAM" + markdown table rows
#
# The checklist prompt now asks Gemini for 8 columns per row:
# Item | Status | Decision | Explanation | Reference from RFP | Page No |
# Document Name | Section Name
#
# Falls back gracefully to the original 4-column shape (older reports /
# any row that doesn't have the extra fields) so nothing breaks.
# ---------------------------------------------------


def _parse_checklist(section_text: str):
    teams = []
    if not section_text:
        return teams

    team_blocks = re.split(r"\n##\s+", section_text)
    for block in team_blocks[1:]:
        lines = block.strip().splitlines()
        if not lines:
            continue
        team_name = lines[0].strip()
        rows = []
        for line in lines[1:]:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 4:
                continue
            if cols[0].lower() == "item":
                continue
            if re.fullmatch(r"-+", cols[0].replace(" ", "")):
                continue
            row = {
                "item": cols[0],
                "status": cols[1],
                "decision": cols[2],
                "explanation": cols[3],
            }
            # Extra fields (Reference from RFP, Page No, Document Name,
            # Section Name) are appended if the model provided them.
            row["reference"] = cols[4] if len(cols) > 4 else None
            row["page_number"] = cols[5] if len(cols) > 5 else None
            row["document_name"] = cols[6] if len(cols) > 6 else None
            row["section_name"] = cols[7] if len(cols) > 7 else None
            rows.append(row)
        teams.append({"team": team_name, "items": rows})
    return teams


# ---------------------------------------------------
# SCORING SUMMARY: "Label: NN%" lines
# ---------------------------------------------------


def _parse_scoring(section_text: str):
    scores = {}
    if not section_text:
        return scores
    for label_key, label_text in [
        ("finance_score", "Finance Score"),
        ("legal_score", "Legal Score"),
        ("operations_score", "Operations Score"),
        ("technical_score", "Technical Score"),
        ("overall_score", "Overall Score"),
    ]:
        m = re.search(rf"{re.escape(label_text)}:\s*(\d+\.?\d*%)", section_text, re.IGNORECASE)
        scores[label_key] = m.group(1) if m else None
    return scores


# ---------------------------------------------------
# QUALIFICATION DECISION: labelled fields + justification paragraph
# ---------------------------------------------------


def _parse_decision(section_text: str):
    decision = {}
    if not section_text:
        return decision

    for label_key, label_text in [
        ("strategic_fit", "Strategic Fit"),
        ("capability_alignment", "Capability Alignment"),
        ("financial_viability", "Financial Viability"),
        ("risk_assessment", "Risk Assessment"),
    ]:
        m = re.search(rf"{re.escape(label_text)}:\s*(.+)", section_text)
        decision[label_key] = m.group(1).strip() if m else None

    final_match = re.search(r"Final Decision:\s*([^\n]+)", section_text, re.IGNORECASE)
    decision["final_decision"] = final_match.group(1).strip() if final_match else None

    just_match = re.search(
        r"##?\s*JUSTIFICATION\s*\n+(.+)", section_text, re.DOTALL | re.IGNORECASE
    )
    decision["justification"] = just_match.group(1).strip() if just_match else None

    return decision


# ---------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------


def report_to_json(raw_report: str) -> dict:
    """
    Converts a raw markdown report (as produced by
    rfp_core.analyze_rfp_headless) into a structured dict:

    {
      "deliverables": [ {category, items: [...]}, ... ],
      "evaluation_criteria": { key: {title, content}, ... },
      "compliance_checklist": [ {team, items: [...]}, ... ],
      "scoring_summary": { finance_score, legal_score, ... },
      "decision": { strategic_fit, ..., final_decision, justification }
    }
    """
    chunks = _split_raw_sections(raw_report)
    return {
        "deliverables": _parse_deliverables(chunks.get("deliverables", "")),
        "evaluation_criteria": _parse_evaluation(chunks.get("evaluation_criteria", "")),
        "compliance_checklist": _parse_checklist(chunks.get("compliance_checklist", "")),
        "scoring_summary": _parse_scoring(chunks.get("scoring_summary", "")),
        "decision": _parse_decision(chunks.get("decision", "")),
    }