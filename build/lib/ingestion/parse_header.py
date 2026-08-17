import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pdfplumber

# ---------------------------------------------------------------------------
# shared data model
# ---------------------------------------------------------------------------


@dataclass
class BlockLot:
    block: str
    lots: list[str]


@dataclass
class AgendaItem:
    agenda_section: str | None
    item_number: int
    application_id: str
    premises: str
    blocks: list[BlockLot]
    ward: str
    applicant: str
    attorney: str | None
    project_text: str
    variances_raw: str | None


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

_DIVIDER_RE = re.compile(r"^[_\-=]{3,}$")


def _is_divider(line: str) -> bool:
    return bool(_DIVIDER_RE.match(line))


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Word-processor-generated PDFs (Livingston's) render bulleted list markers as
# private-use-area glyphs, not real whitespace — str.strip() leaves them in
# place as a literal leading character.
_BULLET_CHARS = "•·◦▪"


def _strip_line(raw_line: str) -> str:
    return raw_line.strip().lstrip(_BULLET_CHARS).strip()


def _ordinal_from_letter(letter: str) -> int:
    return ord(letter.lower()) - ord("a") + 1


QUOTED_VARIANCE_TOKEN_RE = re.compile(r"(?:\d+\s*)?['‘’\"][a-zA-Z]\d?(?:\(\d+\))?['‘’\"]")
VARIANCE_WORD_RE = re.compile(r"\bvariances?\b", re.IGNORECASE)


def _extract_variances_raw(project_text: str) -> str | None:
    match = QUOTED_VARIANCE_TOKEN_RE.search(project_text) or VARIANCE_WORD_RE.search(project_text)
    return project_text[match.start():].strip() if match else None


# Newark's own format: bare numbers, `|`, `:`, or `-` delimiter ("3042|1,5",
# "322: 5", "915-26, 30" as seen in zoning agendas).
_NEWARK_BLOCK_LOT_DELIM_RE = re.compile(r"[|:-]")


def _parse_block_lot(value: str) -> list[BlockLot]:
    value = value.strip()
    if not value:
        return []

    groups = [g.strip() for g in value.split(";") if g.strip()]
    result: list[BlockLot] = []
    for group in groups:
        delim = _NEWARK_BLOCK_LOT_DELIM_RE.search(group)
        if delim:
            block_part, lots_part = group[: delim.start()], group[delim.end() :]
            lots_part = re.sub(r"\band\b", ",", lots_part, flags=re.IGNORECASE)
            lots = [lot.strip() for lot in lots_part.split(",") if lot.strip()]
        else:
            block_part, lots = group, []
        result.append(BlockLot(block=block_part.strip(), lots=lots))
    return result


# Every other town's format: labeled words ("Block 1171, Lot 10", "Block:2101; Lot:8.03",
# "(Block 3305, Lot 3.01)", "Block 1301, Lot 30 and 31").
_NUM = r"\d+(?:\.\d+)?"
BLOCK_LOT_LABELED_RE = re.compile(
    rf"Block:?\s*({_NUM})\s*[,;]\s*Lots?:?\s*({_NUM}(?:\s*(?:,|and|&)\s*{_NUM})*)",
    re.IGNORECASE,
)


def _parse_block_lot_labeled(text: str) -> list[BlockLot]:
    match = BLOCK_LOT_LABELED_RE.search(text)
    if not match:
        return []
    lots_part = re.sub(r"(?i)\b(?:and|&)\b", ",", match.group(2))
    lots = [lot.strip() for lot in lots_part.split(",") if lot.strip()]
    return [BlockLot(block=match.group(1).strip(), lots=lots)]


# ---------------------------------------------------------------------------
# Newark (CPB / ZBA)
# ---------------------------------------------------------------------------

NEWARK_SECTION_KEYWORDS = {
    "new application": "New Application",
    "new applications": "New Application",
    "extension": "Extension",
    "extensions": "Extension",
    "memorialization": "Memorialization",
    "memorializations": "Memorialization",
    "carried over": "Carried Over",
    "carry-over": "Carried Over",
    "withdrawn": "Withdrawn",
    "pending applications": "Pending Applications",
}

# Lines like "Memorialization of Minutes: June 22nd..." carry trailing content, so they
# don't match NEWARK_SECTION_KEYWORDS (an exact bare-label match) — they need their own
# "close whatever item is open" rule instead, or that trailing text leaks into the last
# real item's project_text.
NEWARK_CLOSE_RE = re.compile(
    r"(?i)^(memorialization of (minutes|resolutions)"
    r"|resolution to convene into executive session"
    r"|end of meeting|next meeting)\b"
)

NEWARK_ITEM_START_RE = re.compile(r"(?i)^application\s*:")
NEWARK_LONE_NUMBER_RE = re.compile(r"^(\d+)[.)]$")

NEWARK_FIELD_LABELS = [
    ("application", "app", "Application", True),
    ("premises", "premises", "Premises", True),
    ("block_lot", "block_lot", r"Block\(s\)/Lot\(s\)", False),
    ("ward", "ward", "Ward", True),
    ("applicant", "applicant", "Applicant", True),
    # Newark item CPB-25-115 uses `Owner:` in place of `Applicant:` — no item seen so
    # far carries both, so aliasing straight to `applicant` is safe.
    ("applicant", "owner", "Owner", True),
    ("attorney", "attorney", "Attorney", True),
    ("project", "project", "Project", True),
]
_NEWARK_LABEL_GROUP_TO_KEY = {group: key for key, group, _label, _required in NEWARK_FIELD_LABELS}
NEWARK_LABEL_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(
        f"(?P<lbl_{group}>{label})\\s*{':' if required else ':?'}"
        for _key, group, label, required in NEWARK_FIELD_LABELS
    )
    + r")",
    re.IGNORECASE,
)


def _match_newark_section(line: str) -> str | None:
    key = line.strip().lower().rstrip(":")
    return NEWARK_SECTION_KEYWORDS.get(key)


def _group_newark(text: str) -> list[dict]:
    current_section: str | None = None
    current_item: dict | None = None
    pending_number: int | None = None
    counters: dict[str | None, int] = {}
    items: list[dict] = []

    for raw_line in text.splitlines():
        line = _strip_line(raw_line)
        if not line or _is_divider(line):
            continue

        section = _match_newark_section(line)
        if section is not None:
            current_section = section
            pending_number = None
            continue

        if NEWARK_CLOSE_RE.match(line):
            if current_item is not None:
                items.append(current_item)
                current_item = None
            continue

        lone_number = NEWARK_LONE_NUMBER_RE.match(line)
        if lone_number:
            pending_number = int(lone_number.group(1))
            continue

        if NEWARK_ITEM_START_RE.match(line):
            if current_item is not None:
                items.append(current_item)
            if pending_number is not None:
                item_number = pending_number
            else:
                counters[current_section] = counters.get(current_section, 0) + 1
                item_number = counters[current_section]
            pending_number = None
            current_item = {"section": current_section, "item_number": item_number, "lines": [line]}
            continue

        if current_item is not None:
            current_item["lines"].append(line)

    if current_item is not None:
        items.append(current_item)

    return items


def _extract_newark_fields(block_text: str) -> dict[str, str]:
    matches = list(NEWARK_LABEL_PATTERN.finditer(block_text))
    fields: dict[str, str] = {}
    for i, match in enumerate(matches):
        key = _NEWARK_LABEL_GROUP_TO_KEY[match.lastgroup.removeprefix("lbl_")]
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block_text)
        fields[key] = block_text[start:end].strip(" \t·:•")
    return fields


def _parse_newark_item(raw_item: dict) -> AgendaItem:
    block_text = _clean(" ".join(raw_item["lines"]))
    fields = _extract_newark_fields(block_text)
    project_text = fields.get("project", "").strip()
    attorney = fields.get("attorney", "").strip() or None

    return AgendaItem(
        agenda_section=raw_item["section"],
        item_number=raw_item["item_number"],
        application_id=fields.get("application", "").strip(),
        premises=fields.get("premises", "").strip(),
        blocks=_parse_block_lot(fields.get("block_lot", "")),
        ward=fields.get("ward", "").strip(),
        applicant=fields.get("applicant", "").strip(),
        attorney=attorney,
        project_text=project_text,
        variances_raw=_extract_variances_raw(project_text),
    )


def _parse_newark(text: str) -> list[AgendaItem]:
    return [_parse_newark_item(raw) for raw in _group_newark(text)]


# ---------------------------------------------------------------------------
# Bloomfield (planning: lettered items under "Resolutions:"; zoning: lettered
# items under "Old Business:" / "New Business:", each with Block/Lot + labels)
# ---------------------------------------------------------------------------

_NUMBERED_SECTION_RE = re.compile(r"^(\d+)\.\s*(.*)$")
_LETTERED_ITEM_RE = re.compile(r"^([A-Za-z])\.\s*(.*)$")


def _bloomfield_resolution_item(section: str, item_number: int, text: str) -> AgendaItem:
    # These items are thin — just an applicant name or just an address, never
    # both (no block/lot or project text survives to a resolution vote in the
    # source). A leading digit is the only reliable signal it's an address.
    is_address = bool(re.match(r"^\d", text))
    return AgendaItem(
        agenda_section=section,
        item_number=item_number,
        application_id="",
        premises=text if is_address else "",
        blocks=[],
        ward="",
        applicant="" if is_address else text,
        attorney=None,
        project_text="",
        variances_raw=None,
    )


# Two label shapes seen in real agendas: combined "Applicant/Owner:" (one
# entity), and separate "Applicant: X" ... "Owner: Y" (an individual acting
# for a distinct LLC owner) — the optional `owner` group only matches when
# a standalone "Owner:" label is actually present.
BLOOMFIELD_RICH_ITEM_RE = re.compile(
    r"(?i)Applicant(?:/Owner)?:?\s*(?P<applicant>.+?)"
    r"(?:\s*Owner:?\s*(?P<owner>.+?))?"
    r"\s*Application:?\s*(?P<project>.+)$"
)
BLOOMFIELD_ZONE_RE = re.compile(r"(?i)\bZone:?\s*[\w-]+")


def _bloomfield_rich_item(section: str, item_number: int, lines: list[str]) -> AgendaItem:
    premises = _clean(lines[0])
    rest = _clean(" ".join(lines[1:]))
    blocks = _parse_block_lot_labeled(rest)
    match = BLOOMFIELD_RICH_ITEM_RE.search(rest)
    applicant = match.group("applicant").strip() if match else ""
    owner = match.group("owner").strip() if match and match.group("owner") else ""
    if owner:
        applicant = f"{applicant} / {owner}"
    project_text = match.group("project").strip() if match else ""

    # "Zone: B-2" sits between the block/lot line and "Applicant/Owner:" —
    # outside both capture groups above. Keep it in project_text (rather than
    # drop it) since Milestone 4's Claude extraction reads `zone` from here.
    zone_match = BLOOMFIELD_ZONE_RE.search(rest)
    if zone_match and project_text:
        project_text = f"{zone_match.group(0)}. {project_text}"
    return AgendaItem(
        agenda_section=section,
        item_number=item_number,
        application_id="",
        premises=premises,
        blocks=blocks,
        ward="",
        applicant=applicant,
        attorney=None,
        project_text=project_text,
        variances_raw=_extract_variances_raw(project_text),
    )


def _bloomfield_section_mode(title: str) -> str | None:
    """Both Bloomfield boards share the same two item shapes, under section
    titles that vary a little board to board and month to month (confirmed
    against 27 real Bloomfield planning meetings and their zoning
    counterparts, not just the single fixture each board started with):
    thin lettered items under "Resolutions", and rich block/lot/zone/
    applicant items under "Old Business", "New Business", or an "Applications
    to consider for [the] Board Planner and/or [the] Board Traffic Expert"
    section (sometimes suffixed "('d' variances)")."""
    key = title.lower()
    if key == "resolutions":
        return "thin"
    if key in {"old business", "new business"} or "applications to consider" in key:
        return "rich"
    return None


def _bloomfield_canonical_section(title: str) -> str:
    # Observed variants: "...for Board Planner and/or the Board Traffic
    # Expert:", "...for Board Planner and/or Traffic Expert ('d' variances):"
    # — same section, collapse to one label rather than fragmenting the
    # section filter across near-duplicate strings.
    if "applications to consider" in title.lower():
        return "Applications to Consider"
    return title


def _parse_bloomfield(text: str) -> list[AgendaItem]:
    items: list[AgendaItem] = []
    mode: str | None = None
    current_section: str | None = None
    current_letter: str | None = None
    current_lines: list[str] | None = None
    counters: dict[str | None, int] = {}

    def flush() -> None:
        nonlocal current_letter, current_lines
        if current_lines is not None:
            counters[current_section] = counters.get(current_section, 0) + 1
            item_number = counters[current_section]
            if mode == "thin":
                items.append(_bloomfield_resolution_item(current_section, item_number, _clean(" ".join(current_lines))))
            elif mode == "rich":
                items.append(_bloomfield_rich_item(current_section, item_number, current_lines))
        current_letter, current_lines = None, None

    for raw_line in text.splitlines():
        line = _strip_line(raw_line)
        if not line or _is_divider(line):
            continue

        numbered = _NUMBERED_SECTION_RE.match(line)
        if numbered:
            flush()
            title = numbered.group(2).strip().rstrip(":")
            mode = _bloomfield_section_mode(title)
            current_section = _bloomfield_canonical_section(title) if mode else None
            continue

        if mode is not None:
            lettered = _LETTERED_ITEM_RE.match(line)
            if lettered:
                flush()
                current_letter, current_lines = lettered.group(1), [lettered.group(2)]
                continue
            if current_lines is not None:
                current_lines.append(line)

    flush()
    return items


def _parse_bloomfield_planning(text: str) -> list[AgendaItem]:
    return _parse_bloomfield(text)


def _parse_bloomfield_zoning(text: str) -> list[AgendaItem]:
    return _parse_bloomfield(text)


# ---------------------------------------------------------------------------
# Fairfield (no item numbering at all — a case-number-prefixed paragraph
# break is the only item boundary, and there is no project narrative)
# ---------------------------------------------------------------------------

# No trailing `\b`: after an optional "(2)" suffix, the next char is a space —
# neither side of that boundary is a word char, so `\b` would never match
# there and the engine backtracks to drop the suffix entirely.
# [\w]+(?:\s*-\s*[\w]+)* (not a plain [\w-]+) tolerates stray whitespace
# around the hyphen in a case number — confirmed live: "App # 3- 2025".
FAIRFIELD_CASE_START_RE = re.compile(
    r"^(?P<case>App\s*#\s*[\w]+(?:\s*-\s*[\w]+)*|\d{4}-\d+(?:\s*\(\d+\))?)"
)
FAIRFIELD_HEADER_RE = re.compile(r"^[A-Z0-9 ,#/'’.\-]+:$")

BUSINESS_SUFFIX_RE = re.compile(r"^(.*?\b(?:LLC|L\.L\.C\.|Inc\.?|Corp\.?|Co\.|LP|L\.P\.))\b", re.IGNORECASE)
VARIANCE_TAIL_RE = re.compile(r"^(.*?)\s+([A-Za-z]\d{0,2}\s+Variance[s]?)\.?\s*$", re.IGNORECASE)
STREET_ADDRESS_RE = re.compile(
    r"^\d+[\w\s.,&\-#/]*?\b(?:Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Lane|Ln|Place|Pl|Way|Court|Ct|"
    r"Boulevard|Blvd|Terrace|Ter|Circle|Cir|Highway|Hwy|Parkway|Pkwy)\b\.?",
    re.IGNORECASE,
)


def _looks_like_motion_tracker(line: str) -> bool:
    return line.count("____") >= 2


def _clean_premises_fragment(line: str) -> str:
    match = STREET_ADDRESS_RE.match(line)
    if match:
        return match.group(0).strip()
    return line.strip().rstrip(",")


def _fairfield_item(section: str, item_number: int, lines: list[str]) -> AgendaItem:
    case_match = FAIRFIELD_CASE_START_RE.match(lines[0])
    assert case_match is not None  # guaranteed by the caller's boundary check
    case_str = case_match.group("case")
    if case_str.lower().startswith("app"):
        application_id = re.sub(r"(?i)^app\s*#?\s*", "", case_str).strip()
    else:
        application_id = case_str.strip()
    # Collapse whitespace the case-number regex had to tolerate around a
    # hyphen ("3- 2025") — a PDF-extraction artifact, not how anyone writes
    # the number, so normalize rather than reproduce it verbatim.
    application_id = re.sub(r"\s*-\s*", "-", application_id)

    rest0 = lines[0][case_match.end():].strip()
    variances_raw: str | None = None
    business = BUSINESS_SUFFIX_RE.match(rest0)
    if business:
        applicant = business.group(1).strip()
    else:
        variance = VARIANCE_TAIL_RE.match(rest0)
        if variance:
            applicant, variances_raw = variance.group(1).strip(), variance.group(2).strip()
        else:
            applicant = rest0.strip()

    premises_lines = [l for l in lines[1:] if not re.search(r"(?i)\bblock\b", l)]
    premises = ", ".join(_clean_premises_fragment(l) for l in premises_lines)

    blocks = _parse_block_lot_labeled(_clean(" ".join(lines)))

    return AgendaItem(
        agenda_section=section,
        item_number=item_number,
        application_id=application_id,
        premises=premises,
        blocks=blocks,
        ward="",
        applicant=applicant,
        attorney=None,
        project_text="",
        variances_raw=variances_raw,
    )


def _parse_fairfield(text: str, target_sections: dict[str, str]) -> list[AgendaItem]:
    items: list[AgendaItem] = []
    harvesting = False
    current_section: str | None = None
    current_lines: list[str] | None = None
    counters: dict[str | None, int] = {}

    def flush() -> None:
        nonlocal current_lines
        if current_lines is not None:
            counters[current_section] = counters.get(current_section, 0) + 1
            items.append(_fairfield_item(current_section, counters[current_section], current_lines))
        current_lines = None

    for raw_line in text.splitlines():
        line = _strip_line(raw_line)
        if not line or _is_divider(line):
            continue

        if _looks_like_motion_tracker(line) or line.lower().startswith("enclosed:"):
            flush()
            continue

        if FAIRFIELD_HEADER_RE.match(line):
            flush()
            canonical = target_sections.get(line.rstrip(":").lower())
            harvesting = canonical is not None
            current_section = canonical
            continue

        if harvesting and FAIRFIELD_CASE_START_RE.match(line):
            flush()
            current_lines = [line]
            continue

        if current_lines is not None:
            current_lines.append(line)

    flush()
    return items


# "Old Business:"/"New Business:" confirmed live in real Fairfield planning
# agendas (case-numbered items identical in shape to the memorialization
# ones) — the Milestone 2 fixture only had a memorialization item, so this
# was missed entirely until crawling real data surfaced it.
FAIRFIELD_PLANNING_TARGETS = {
    "memorialization of resolutions": "Memorialization",
    "old business": "Old Business",
    "new business": "New Business",
}
FAIRFIELD_ZONING_TARGETS = {
    "memorialization of resolutions": "Memorialization",
    "old business": "Old Business",
    "new business": "New Business",
}


def _parse_fairfield_planning(text: str) -> list[AgendaItem]:
    return _parse_fairfield(text, FAIRFIELD_PLANNING_TARGETS)


def _parse_fairfield_zoning(text: str) -> list[AgendaItem]:
    return _parse_fairfield(text, FAIRFIELD_ZONING_TARGETS)


# ---------------------------------------------------------------------------
# Livingston (planning: lettered memorializations, no block/lot; zoning: a
# bulleted memorialization list plus numbered "N)" items with itemized
# per-section variance bullets — the richest non-Newark source)
# ---------------------------------------------------------------------------


def _livingston_planning_item(section: str, item_number: int, lines: list[str]) -> AgendaItem:
    first = lines[0]
    dash = "–" if "–" in first else ("-" if "-" in first else None)
    if dash:
        applicant, premises = (p.strip() for p in first.split(dash, 1))
    else:
        applicant, premises = first.strip(), ""

    app_text = _clean(" ".join(lines[1:]))
    application_id = re.sub(r"(?i)^application\s*no\.?\s*", "", app_text).strip()

    return AgendaItem(
        agenda_section=section,
        item_number=item_number,
        application_id=application_id,
        premises=premises,
        blocks=[],
        ward="",
        applicant=applicant,
        attorney=None,
        project_text="",
        variances_raw=None,
    )


def _parse_ordinal_marker(marker: str) -> int:
    """Livingston planning uses both "(a)" and "(1)" style markers for
    memorialization items (confirmed live — same section, different months)."""
    return int(marker) if marker.isdigit() else _ordinal_from_letter(marker)


# Confirmed live: planning has the same "Conference Meeting Agenda" +
# "Regular Meeting Agenda" dual structure as zoning (Milestone 2's fixture
# only had a thin conference-only agenda, so this was missed entirely).
# Unlike zoning's "Continued Matters"/"New Business" bare-title sections
# with nested "1)" items, planning's real items sit directly on the Regular
# Meeting Agenda's own numbered list ("4. Preliminary & Final Site Plan...")
# alongside plain admin entries — distinguished by title, not markup.
_LIVINGSTON_ADMIN_LABELS = ("call to order", "statement of compliance", "roll call", "adjournment")


def _is_livingston_admin_label(title: str) -> bool:
    key = title.strip().lower()
    return any(key.startswith(label) for label in _LIVINGSTON_ADMIN_LABELS)


# Confirmed live: "Regular Meeting Agenda" and "Special Meeting Agenda" both
# run under the same "items" mode — items appear in three different shapes,
# even within a single meeting:
#   1. the numbered line itself IS the item's title ("4. Preliminary & Final
#      Site Plan (Amendment)") — nothing to skip, block/app/premises/
#      applicant/narrative start on the very next line.
#   2. a generic section label ("Old Business"/"New Business"/"Continued
#      Matter(s)") opens the section, and the item's real title is a
#      separate line right after — that one line must be discarded too.
#   3. a lettered "(a)"/"a)" marker carries the title inline with the
#      marker itself, discarding the whole marker line.
# All three converge on the same body shape, modeled by _livingston_rich_item.
_LIVINGSTON_LETTER_ITEM_RE = re.compile(r"^\(?([a-zA-Z])\)\s+(.*)$")
_LIVINGSTON_GENERIC_SECTION_LABELS = ("old business", "new business", "continued matter", "continued matters")


def _is_livingston_generic_section_label(title: str) -> bool:
    key = title.strip().lower().rstrip(":").strip()
    return key in _LIVINGSTON_GENERIC_SECTION_LABELS


def _parse_livingston_planning(text: str) -> list[AgendaItem]:
    items: list[AgendaItem] = []
    mode: str | None = None  # None | "memorialization" | "items"
    current_section: str | None = None
    current_letter: str | None = None
    current_lines: list[str] | None = None
    skip_title = False
    counters: dict[str | None, int] = {}

    def flush() -> None:
        nonlocal current_letter, current_lines
        if current_lines is not None:
            if mode == "memorialization":
                items.append(_livingston_planning_item("Memorialization", _parse_ordinal_marker(current_letter), current_lines))
            elif mode == "items" and len(current_lines) >= 4:
                counters[current_section] = counters.get(current_section, 0) + 1
                items.append(_livingston_rich_item(current_section, counters[current_section], current_lines))
        current_letter, current_lines = None, None

    for raw_line in text.splitlines():
        line = _strip_line(raw_line)
        if not line or _is_divider(line):
            continue

        if line == "Regular Meeting Agenda":
            flush()
            mode, current_section, skip_title = "items", "Regular Meeting", False
            continue
        if line == "Special Meeting Agenda":
            flush()
            mode, current_section, skip_title = "items", "Special Meeting", False
            continue

        numbered = _NUMBERED_SECTION_RE.match(line)
        if numbered:
            title = numbered.group(2).strip()
            if mode == "items":
                flush()
                if _is_livingston_admin_label(title):
                    current_lines = None
                elif _is_livingston_generic_section_label(title):
                    current_lines, skip_title = [], True
                else:
                    current_lines, skip_title = [], False
                continue
            flush()
            mode = "memorialization" if "memorializ" in title.lower() else None
            continue

        if mode == "items":
            lettered = _LIVINGSTON_LETTER_ITEM_RE.match(line)
            if lettered:
                flush()
                current_lines, skip_title = [], False
                continue

        if mode == "memorialization":
            lettered = re.match(r"^\(([a-zA-Z0-9]+)\)\s*(.*)$", line)
            if lettered:
                flush()
                current_letter, current_lines = lettered.group(1), [lettered.group(2)]
                continue
            if current_lines is not None:
                current_lines.append(line)
        elif mode == "items" and current_lines is not None:
            if skip_title:
                skip_title = False
                continue
            current_lines.append(line)

    flush()
    return items


_LIVINGSTON_BULLET_APP_RE = re.compile(r"(?i)application\s*no\.?\s*([^;]+)")


def _livingston_bullet_item(section: str, item_number: int, line: str) -> AgendaItem:
    # Premises/applicant are usually semicolon-separated ("6 Ross Road;
    # Application No. 2025-91-V; Amit Thakur"), but confirmed live: the same
    # meeting can switch to an en-dash before "Application No." ("16 West
    # Lawn Rd – Application No. 2026-6-V; Meredith Schwartz") — locate the
    # application number by content rather than assuming a fixed delimiter.
    match = _LIVINGSTON_BULLET_APP_RE.search(line)
    if match:
        premises = line[: match.start()].strip(" ;–-")
        application_id = match.group(1).strip()
        applicant = line[match.end() :].strip(" ;–-")
    else:
        premises, application_id, applicant = line.strip(), "", ""
    return AgendaItem(
        agenda_section=section,
        item_number=item_number,
        application_id=application_id,
        premises=premises,
        blocks=[],
        ward="",
        applicant=applicant,
        attorney=None,
        project_text="",
        variances_raw=None,
    )


# Zone descriptors vary more than "R-2 Zone": confirmed live "R-5Q Residence
# Overlay Zone" (multi-word), "I-Zone" (bare letter code, hyphen with no
# space before "Zone"), and "P-B3 Zone" (a letter, not just a digit, right
# after the hyphen). Every confirmed real code has a hyphen right after its
# 1-4 letter prefix — require it. This is what keeps the match from
# over-capturing an ordinary applicant-name suffix like "LLC" (no hyphen)
# that happens to sit one space before a real "I-Zone".
LIVINGSTON_ZONE_SUFFIX_RE = re.compile(
    r"\s+([A-Z]{1,4}-(?:Zone|[A-Za-z0-9]{1,4}(?:\s+[A-Za-z]+)*\s+Zone))\s*$", re.IGNORECASE
)


_LIVINGSTON_APPLICATION_LINE_RE = re.compile(r"(?i)^application\s*nos?\.?\s")


def _livingston_rich_item(section: str, item_number: int, lines: list[str]) -> AgendaItem:
    """lines = the item's body, containing a block line, an application line,
    a premises line, and an applicant line, plus narrative — but not always
    in that order (confirmed live: Livingston's "Special Meeting Agenda"
    items sometimes list the application line before the block line). The
    block and application lines are located by content rather than position;
    the two remaining lines are assumed to be [premises, applicant] in their
    original relative order, which holds across every confirmed format."""
    app_idx = next((i for i, l in enumerate(lines) if _LIVINGSTON_APPLICATION_LINE_RE.match(l)), None)
    block_idx = next((i for i, l in enumerate(lines) if _parse_block_lot_labeled(l)), None)
    app_line = lines[app_idx] if app_idx is not None else ""
    block_line = lines[block_idx] if block_idx is not None else ""
    remaining = [l for i, l in enumerate(lines) if i != app_idx and i != block_idx]
    premises_line, applicant_line, *narrative_lines = remaining

    application_id = re.sub(r"(?i)^application\s*nos?\.?\s*", "", app_line).strip()
    zone_match = LIVINGSTON_ZONE_SUFFIX_RE.search(applicant_line)
    applicant = LIVINGSTON_ZONE_SUFFIX_RE.sub("", applicant_line).strip()
    narrative = _clean(" ".join(narrative_lines))
    # Keep the zone (e.g. "R-2 Zone") in project_text rather than drop it —
    # Milestone 4's Claude extraction reads `zone` from here.
    project_text = f"{zone_match.group(1)}. {narrative}" if zone_match and narrative else narrative

    return AgendaItem(
        agenda_section=section,
        item_number=item_number,
        application_id=application_id,
        premises=_clean(premises_line),
        blocks=_parse_block_lot_labeled(block_line),
        ward="",
        applicant=applicant,
        attorney=None,
        project_text=project_text,
        variances_raw=_extract_variances_raw(project_text),
    )


def _livingston_variance_item(section: str, item_number: int, lines: list[str]) -> AgendaItem:
    # First line is always a bare "Variance" (occasionally "Variance (Continued
    # from ...)") type label — not a modeled field, drop it.
    body = [l for l in lines if not l.strip().lower().startswith("variance")]
    return _livingston_rich_item(section, item_number, body)


def _parse_livingston_zoning(text: str) -> list[AgendaItem]:
    items: list[AgendaItem] = []
    mode = "admin"  # admin | memorialization | continued
    current_section: str | None = None
    current_lines: list[str] | None = None
    counters: dict[str | None, int] = {}

    def flush() -> None:
        nonlocal current_lines
        if current_lines is not None:
            counters[current_section] = counters.get(current_section, 0) + 1
            items.append(_livingston_variance_item(current_section, counters[current_section], current_lines))
        current_lines = None

    for raw_line in text.splitlines():
        line = _strip_line(raw_line)
        if not line or _is_divider(line):
            continue

        numbered = _NUMBERED_SECTION_RE.match(line)
        if numbered:
            flush()
            title = numbered.group(2).strip()
            if title and "memorializ" in title.lower():
                mode, current_section = "memorialization", "Memorialization"
            else:
                mode, current_section = "admin", None
            continue

        if line in ("Continued Matters", "New Business"):
            flush()
            mode = "continued"
            current_section = "Extension" if line == "Continued Matters" else line
            continue

        # Confirmed live: "memorializing" sometimes appears mid-line (e.g.
        # "(b) Consideration of Memorializing Resolutions:") rather than as
        # a numbered section's own title — detect it wherever it appears.
        if mode != "memorialization" and "memorializ" in line.lower():
            flush()
            mode, current_section = "memorialization", "Memorialization"
            continue

        if mode == "memorialization" and "Application No." in line:
            counters[current_section] = counters.get(current_section, 0) + 1
            items.append(_livingston_bullet_item(current_section, counters[current_section], line))
            continue

        # Confirmed live: a long applicant name can wrap onto its own line
        # below the bullet (e.g. "41 W. McClellan Avenue; Application No.
        # ...; 41 W. McClellan" then "Avenue Inc." on the next line) — merge
        # it into the applicant just recorded rather than losing it.
        if mode == "memorialization" and items and items[-1].agenda_section == current_section:
            items[-1].applicant = _clean(f"{items[-1].applicant} {line}")
            continue

        # Confirmed live: a "Regular Meeting Agenda"/"Special Meeting Agenda"
        # section can list "N)" items directly after its admin lines (Call
        # to Order, Roll Call) with no "Continued Matters"/"New Business"
        # trigger line at all — detect the item start structurally.
        item_start = re.match(r"^(\d+)\)\s*(.*)$", line)
        if item_start:
            flush()
            current_section = current_section if mode == "continued" else "Regular Meeting"
            mode = "continued"
            current_lines = [item_start.group(2)]
            continue

        if mode == "continued" and current_lines is not None:
            current_lines.append(line)

    flush()
    return items


# ---------------------------------------------------------------------------
# Montclair (lettered items under numbered sections; only sub-items that
# actually carry an "App. NNNN" case reference are real leads — council
# referrals and litigation references under the same sections are not)
# ---------------------------------------------------------------------------

MONTCLAIR_ITEM_RE = re.compile(
    # The premises/applicant separator must be whitespace-padded — a plain
    # hyphen with no surrounding spaces is an address range ("116-118 Walnut
    # Street"), not the em-dash separator.
    r"(?i)App\.?\s*(?P<app_id>\d+):?\s*(?P<premises>.+?)\s+[–-]\s+(?P<applicant>.+?)\.\s*\(?Block\b"
)
MONTCLAIR_TARGET_SECTIONS = {"resolutions", "old business", "new business"}


def _montclair_item(section: str, item_number: int, text_block: str) -> AgendaItem:
    match = MONTCLAIR_ITEM_RE.search(text_block)
    application_id = match.group("app_id") if match else ""
    premises = match.group("premises").strip() if match else ""
    applicant = match.group("applicant").strip() if match else ""

    blocks = _parse_block_lot_labeled(text_block)
    block_match = BLOCK_LOT_LABELED_RE.search(text_block)
    project_text = text_block[block_match.end():].lstrip(" .)").strip() if block_match else ""

    return AgendaItem(
        agenda_section=section,
        item_number=item_number,
        application_id=application_id,
        premises=premises,
        blocks=blocks,
        ward="",
        applicant=applicant,
        attorney=None,
        project_text=project_text,
        variances_raw=_extract_variances_raw(project_text),
    )


def _parse_montclair(text: str) -> list[AgendaItem]:
    items: list[AgendaItem] = []
    harvesting = False
    current_section: str | None = None
    current_letter: str | None = None
    current_lines: list[str] | None = None

    def flush() -> None:
        nonlocal current_letter, current_lines
        if current_lines is not None:
            text_block = _clean(" ".join(current_lines))
            if MONTCLAIR_ITEM_RE.search(text_block):
                items.append(_montclair_item(current_section, _ordinal_from_letter(current_letter), text_block))
        current_letter, current_lines = None, None

    for raw_line in text.splitlines():
        line = _strip_line(raw_line)
        if not line or _is_divider(line):
            continue

        numbered = _NUMBERED_SECTION_RE.match(line)
        if numbered:
            flush()
            title = numbered.group(2).strip().rstrip(".").rstrip(":")
            harvesting = title.lower() in MONTCLAIR_TARGET_SECTIONS
            current_section = title if harvesting else None
            continue

        if harvesting:
            lettered = re.match(r"^([a-z])\.\s*(.*)$", line)
            if lettered:
                flush()
                current_letter, current_lines = lettered.group(1), [lettered.group(2)]
                continue
            if current_lines is not None:
                current_lines.append(line)

    flush()
    return items


def _parse_montclair_planning(text: str) -> list[AgendaItem]:
    return _parse_montclair(text)


def _parse_montclair_zoning(text: str) -> list[AgendaItem]:
    return _parse_montclair(text)


# ---------------------------------------------------------------------------
# entrypoints
# ---------------------------------------------------------------------------

TOWN_BOARD_PARSERS: dict[tuple[str, str], Callable[[str], list[AgendaItem]]] = {
    ("newark", "planning"): _parse_newark,
    ("newark", "zoning"): _parse_newark,
    ("bloomfield", "planning"): _parse_bloomfield_planning,
    ("bloomfield", "zoning"): _parse_bloomfield_zoning,
    ("fairfield", "planning"): _parse_fairfield_planning,
    ("fairfield", "zoning"): _parse_fairfield_zoning,
    ("livingston", "planning"): _parse_livingston_planning,
    ("livingston", "zoning"): _parse_livingston_zoning,
    ("montclair", "planning"): _parse_montclair_planning,
    ("montclair", "zoning"): _parse_montclair_zoning,
}


def parse_agenda(text: str, town: str, board: str) -> list[AgendaItem]:
    key = (town, board)
    if key not in TOWN_BOARD_PARSERS:
        raise ValueError(f"no agenda parser registered for town={town!r} board={board!r}")
    return TOWN_BOARD_PARSERS[key](text)


def parse_pdf(path: Path, town: str, board: str) -> list[AgendaItem]:
    with pdfplumber.open(path) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    return parse_agenda(text, town, board)
