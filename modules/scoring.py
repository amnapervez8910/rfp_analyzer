import re

from .presentation import _deadline_status, _explicit_deadline_date

TEAM_HEADERS = [
    ("FINANCE TEAM", "Finance Score"),
    ("LEGAL TEAM", "Legal Score"),
    ("OPERATIONS TEAM", "Operations Score"),
    ("TECHNICAL TEAM", "Technical Score"),
]


def _format_pct(value: float) -> str:
    rounded = round(value, 1)
    if rounded == int(rounded):
        return f"{int(rounded)}%"
    return f"{rounded}%"


def _count_decisions_in_section(section_text: str):
    go = maybe = nogo = 0
    for line in section_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 3:
            continue
        if cols[0].lower() == "item":
            continue
        if re.fullmatch(r"-+", cols[0].replace(" ", "")):
            continue
        decision_col = cols[2].upper()
        if "NO-GO" in decision_col or "NO GO" in decision_col or "NOGO" in decision_col:
            nogo += 1
        elif "MAYBE" in decision_col:
            maybe += 1
        elif "GO" in decision_col:
            go += 1
    total = go + maybe + nogo
    return go, maybe, nogo, total


def recompute_scores(report_text: str):
    """
    Returns a dict: { "Finance Score": {"pct": .., "go": .., "maybe": .., "nogo": .., "total": ..}, ... }
    This is calculated directly from the Decision column of every table row —
    it never trusts any percentage Gemini wrote itself.
    """
    scores = {}
    header_positions = []
    for header, label in TEAM_HEADERS:
        m = re.search(r"##\s*" + re.escape(header), report_text, re.IGNORECASE)
        if m:
            header_positions.append((m.start(), m.end(), label))
    header_positions.sort(key=lambda x: x[0])

    scoring_summary_match = re.search(r"#\s*SCORING SUMMARY", report_text, re.IGNORECASE)
    doc_end = scoring_summary_match.start() if scoring_summary_match else len(report_text)

    for i, (start, end, label) in enumerate(header_positions):
        next_start = header_positions[i + 1][0] if i + 1 < len(header_positions) else doc_end
        section = report_text[end:next_start]
        go, maybe, nogo, total = _count_decisions_in_section(section)
        if total == 0:
            continue
        pct = (go * 1.0 + maybe * 0.5) / total * 100
        scores[label] = {"pct": pct, "go": go, "maybe": maybe, "nogo": nogo, "total": total}

    return scores


def _primary_deadline_overdue(deliverables_text: str) -> bool:
    """Detect whether the RFP's PRIMARY bid-submission deadline has already
    passed. A single overdue minor item (e.g. an optional pre-bid RSVP form)
    shouldn't sink the whole opportunity — but the normal pattern in these
    RFPs is that every core Mandatory submission item (bid PDF, PIA copy,
    transmittal letter, affidavits, bid price form, etc.) shares the exact
    same closing date/time. When 2+ Mandatory deliverables share that same
    absolute deadline and it has already passed, the bid window itself is
    closed, regardless of how well the RFP otherwise scores.
    """
    from collections import Counter
    deadlines = []
    for line in deliverables_text.splitlines():
        line = line.strip()
        if not line.startswith('-') or '::' not in line:
            continue
        parts = [p.strip() for p in line.lstrip('-').split('::')]
        if len(parts) < 8:
            continue
        deadline, requirement_type = parts[2], parts[7]
        if requirement_type.strip().casefold() != 'mandatory':
            continue
        if _explicit_deadline_date(deadline):
            deadlines.append(deadline)
    if len(deadlines) < 2:
        return False
    common_deadline, count = Counter(deadlines).most_common(1)[0]
    if count < 2:
        return False
    return _deadline_status(common_deadline) == 'Overdue'


def determine_final_decision(overall_pct: float, finance_maybe: int, finance_nogo: int,
                              deadline_overdue: bool = False) -> str:
    """
    Same rule the prompt describes, but computed in Python so it can NEVER
    disagree with the recomputed Overall Score. Priority order matters:
      1. The primary bid-submission deadline already passed -> automatic
         NO-GO, no matter how high the score is (the bid window is closed).
      2. Anything under 60% is an automatic NO-GO, no matter what.
      3. 80%+ AND every Finance row is GO -> GO.
      4. Everything else (60-79%, or a Finance MAYBE/NO-GO exists) -> MAYBE.
    """
    if deadline_overdue:
        return "NO-GO"
    if overall_pct < 60:
        return "NO-GO"
    if overall_pct >= 80 and finance_maybe == 0 and finance_nogo == 0:
        return "GO"
    return "MAYBE"


def sync_justification_score(report_text: str, overall_pct: float, correct_decision: str,
                              deadline_overdue: bool = False) -> str:
    """
    Gemini writes the Justification paragraph as free text and sometimes
    quotes a score number OR a decision word (GO/NO-GO/MAYBE) that doesn't
    match the recomputed Overall Score / Final Decision. This finds those
    phrases ONLY inside the Justification section and forces them to the
    correct values, without touching unrelated percentages elsewhere in the
    RFP facts (e.g. '40% SWAM target', '99.99% uptime'). When the primary
    bid deadline has already passed, a plain-language override note is
    prepended so the reader immediately sees WHY a high score still ended
    in NO-GO.
    """
    correct = _format_pct(overall_pct)
    match = re.search(
        r'(##?\s*JUSTIFICATION\s*\n+)(.+?)(?=\n\n|\Z)',
        report_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return report_text

    just_text = match.group(2)

    # Fix any quoted score number
    fixed_just = re.sub(
        r"score\s*(?:of|is|:)?\s*\d+\.?\d*%",
        f"score of {correct}",
        just_text,
        flags=re.IGNORECASE,
    )

    # Fix any quoted decision word (GO / NO-GO / MAYBE) so it matches
    # the actual computed Final Decision, e.g. "the final recommendation
    # is MAYBE" when the real decision is NO-GO.
    fixed_just = re.sub(
        r"(recommendation|decision)\s+is\s+(?:a\s+)?(?:GO|NO-GO|NO GO|MAYBE)\b",
        rf"\1 is {correct_decision}",
        fixed_just,
        flags=re.IGNORECASE,
    )

    if deadline_overdue:
        override_note = (
            "⚠️ OVERRIDE: The primary bid submission deadline stated in this "
            "RFP has already passed as of today, so the bid window is closed "
            "and this opportunity cannot be submitted regardless of the score "
            "below — this is why the Final Decision is NO-GO even though the "
            "compliance score may look strong. "
        )
        if override_note.strip() not in fixed_just:
            fixed_just = override_note + fixed_just

    return report_text[:match.start(2)] + fixed_just + report_text[match.end(2):]

def _ensure_decision_rationale(report_text: str) -> str:
    """Safety net for the Compliance Checklist: guarantee every row's
    Explanation ends with a short clause naming the Decision it led to
    (e.g. "...which leads to a GO decision."), even on the rare row where
    the model's own prompt-following slipped. Purely additive — never
    rewrites existing text, only appends the missing clause.
    """
    lines = report_text.split('\n')
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith('|'):
            out.append(line)
            continue
        cols = [c.strip() for c in stripped.strip('|').split('|')]
        if len(cols) < 4:
            out.append(line)
            continue
        if cols[0].casefold() == 'item' or re.fullmatch(r'-+', cols[0].replace(' ', '')):
            out.append(line)
            continue
        decision_col = cols[2].upper()
        if 'NO-GO' in decision_col or 'NO GO' in decision_col or 'NOGO' in decision_col:
            decision_word = 'NO-GO'
        elif 'MAYBE' in decision_col:
            decision_word = 'MAYBE'
        elif re.search(r'\bGO\b', decision_col):
            decision_word = 'GO'
        else:
            out.append(line)
            continue

        explanation = cols[3]
        already_present = re.search(
            r'\b(GO|NO-GO|NO GO|MAYBE)\s*decision\b|\bdecision\s*(?:of|is)?\s*(?:a\s*)?(GO|NO-GO|NO GO|MAYBE)\b',
            explanation, re.IGNORECASE,
        )
        if not already_present and explanation and 'not specified' not in explanation.casefold():
            cols[3] = explanation.rstrip('.').rstrip() + f", leading to a **{decision_word}** decision."
            leading_ws = line[:len(line) - len(line.lstrip())]
            out.append(leading_ws + '| ' + ' | '.join(cols) + ' |')
        else:
            out.append(line)
    return '\n'.join(out)


def apply_score_fix(report_text: str) -> str:
    """
    Single source of truth for everything numeric in the report:
    1. Recomputes each team's % strictly from Decision columns.
    2. Recomputes Overall Score as the average of the four team %s.
    3. Recomputes Final Decision using the exact same numbers (so it can
       never contradict the score shown).
    4. Forces the Justification paragraph's quoted score to match.
    This guarantees the Scoring Summary, Final Decision, and Justification
    are always internally consistent, regardless of any arithmetic mistake
    Gemini might have made in its own draft.
    """
    scores = recompute_scores(report_text)
    if not scores:
        return report_text

    fixed = report_text
    for header, label in TEAM_HEADERS:
        if label in scores:
            new_line = f"{label}: {_format_pct(scores[label]['pct'])}"
            fixed = re.sub(
                rf"{re.escape(label)}:\s*\d+\.?\d*%",
                new_line,
                fixed,
                flags=re.IGNORECASE,
            )

    overall_pct = sum(v["pct"] for v in scores.values()) / len(scores)
    fixed = re.sub(
        r"Overall Score:\s*\d+\.?\d*%",
        f"Overall Score: {_format_pct(overall_pct)}",
        fixed,
        flags=re.IGNORECASE,
    )

    finance = scores.get("Finance Score")
    finance_maybe = finance["maybe"] if finance else 0
    finance_nogo = finance["nogo"] if finance else 0
    deadline_overdue = _primary_deadline_overdue(report_text)
    correct_decision = determine_final_decision(overall_pct, finance_maybe, finance_nogo, deadline_overdue)

    if re.search(r"Final Decision:\s*[^\n]*", fixed, re.IGNORECASE):
        fixed = re.sub(
            r"Final Decision:\s*[^\n]*",
            f"Final Decision: {correct_decision}",
            fixed,
            flags=re.IGNORECASE,
        )
    else:
        fixed += f"\n\nFinal Decision: {correct_decision}\n"

    fixed = sync_justification_score(fixed, overall_pct, correct_decision, deadline_overdue)
    fixed = _ensure_decision_rationale(fixed)

    return fixed
