import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--budget-from", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()


TASK_BOUNDARY = (
    " Keep learner_prompt within the source and requested activity; do not add source-external "
    "facts or unstated delivery arrangements. This is text-only; chart_questions must be empty."
)

rows = [
    (
        "register-cardinal-slip",
        "Index slip: “Register — token Ilex-7: retained.” A separate line reads “office: Blue.” Available study time is 9 minutes.",
        "Create exactly 2 positive-duration activities totaling 9 minutes. facts keys: register_item, listed_status, office_field. Preserve the source labels and values exactly.",
        {"register_item": "Ilex-7", "listed_status": "retained", "office_field": "Blue"},
        9,
        2,
    ),
    (
        "register-bracken-file",
        "Routing note: file Bracken-5 is listed in the register as open. Its office field reads East Window. Available study time is 7 minutes.",
        "Create exactly one 7-minute activity. facts keys: file, register_status, office_field. Preserve the source wording for each value.",
        {"file": "Bracken-5", "register_status": "open", "office_field": "East Window"},
        7,
        1,
    ),
    (
        "recorded-umber-signal",
        "Event note: signal Umber-2 was recorded at 07:14. Tavi acknowledged the note at 07:19. Current label: waiting. Available study time is 10 minutes.",
        "Create exactly 2 positive-duration activities totaling 10 minutes. facts keys: signal, recorded_at, acknowledgement_by, acknowledgement_at, current_label. Render times exactly as HH:MM and preserve other values.",
        {"signal": "Umber-2", "recorded_at": "07:14", "acknowledgement_by": "Tavi", "acknowledgement_at": "07:19", "current_label": "waiting"},
        10,
        2,
    ),
    (
        "recorded-marlin-message",
        "Ledger line: message Marlin-9 was recorded on 2026-12-04. Asha acknowledged receipt at 16:22. Priority field: low. Available study time is 11 minutes.",
        "Create exactly 2 positive-duration activities totaling 11 minutes. facts keys: message, recorded_date, receipt_acknowledged_by, acknowledged_at, priority. Preserve the ISO date and HH:MM time.",
        {"message": "Marlin-9", "recorded_date": "2026-12-04", "receipt_acknowledged_by": "Asha", "acknowledged_at": "16:22", "priority": "low"},
        11,
        2,
    ),
    (
        "inspection-pending-entry",
        "Chronology: an inspection occurred at 13:25. Lead: Beren. Outcome field: pending. Reference: Flint-8. Available study time is 8 minutes.",
        "Create exactly 2 positive-duration activities totaling 8 minutes. facts keys: event, occurred_at, lead, outcome, reference. Use inspection for event, render time as HH:MM, and preserve the remaining values.",
        {"event": "inspection", "occurred_at": "13:25", "lead": "Beren", "outcome": "pending", "reference": "Flint-8"},
        8,
        2,
    ),
    (
        "visit-willow-fragment",
        "Calendar fragment: visit at 10:05. Visitor: Fara. Reference: Willow-3. Note length: brief. Available study time is 6 minutes.",
        "Create exactly one 6-minute activity. facts keys: event, visit_at, visitor, reference, note_length. Use visit for event, render time as HH:MM, and preserve the remaining values.",
        {"event": "visit", "visit_at": "10:05", "visitor": "Fara", "reference": "Willow-3", "note_length": "brief"},
        6,
        1,
    ),
    (
        "reported-quill-lamp",
        "Shift note: Seki reported that lamp Quill-4 flickered twice. Recorder Uma entered that sentence at 18:05. Available study time is 12 minutes.",
        "Create exactly 3 positive-duration activities totaling 12 minutes. facts keys: reporter, reported_subject, reported_event, recorder, entered_at. Use flickered twice for reported_event and render time as HH:MM.",
        {"reporter": "Seki", "reported_subject": "lamp Quill-4", "reported_event": "flickered twice", "recorder": "Uma", "entered_at": "18:05"},
        12,
        3,
    ),
    (
        "observed-delta-vireo",
        "Observation card: after bell Delta rang, moths gathered at lamp Vireo. Jalen observed this sequence once. Available study time is 13 minutes.",
        "Create exactly 2 positive-duration activities totaling 13 minutes. facts keys: observer, first_event, later_event, observation_count. Preserve the two event clauses; observation_count is a number alone.",
        {"observer": "Jalen", "first_event": "bell Delta rang", "later_event": "moths gathered at lamp Vireo", "observation_count": "1"},
        13,
        2,
    ),
    (
        "scheduled-cobalt-filter",
        "Board note: filter change for unit Cobalt-6 is scheduled for 2026-12-08 11:20. Assigned name: Edda. Status line: scheduled. Available study time is 14 minutes.",
        "Create exactly 3 positive-duration activities totaling 14 minutes. facts keys: task, unit, scheduled_for, assigned_name, status. Use filter change for task, render scheduled_for exactly as YYYY-MM-DD HH:MM, and preserve remaining values.",
        {"task": "filter change", "unit": "Cobalt-6", "scheduled_for": "2026-12-08 11:20", "assigned_name": "Edda", "status": "scheduled"},
        14,
        3,
    ),
    (
        "planned-rill-count",
        "Field card: a shoreline count at Cove Rill is planned for Friday at 06:30. Lead: Tomas. Method: walking transect. Available study time is 15 minutes.",
        "Create exactly 3 positive-duration activities totaling 15 minutes. facts keys: activity, site, planned_day, planned_time, lead, method. Use shoreline count for activity and render planned_time as HH:MM.",
        {"activity": "shoreline count", "site": "Cove Rill", "planned_day": "Friday", "planned_time": "06:30", "lead": "Tomas", "method": "walking transect"},
        15,
        3,
    ),
    (
        "glossary-floral-whorls",
        "Glossary card: calyx — outer floral whorl. corolla — inner floral whorl. Card code: Petal-2. Available study time is 5 minutes.",
        "Create exactly one 5-minute activity. facts keys: first_term, first_definition, second_term, second_definition, card_code. Preserve terms and definitions exactly.",
        {"first_term": "calyx", "first_definition": "outer floral whorl", "second_term": "corolla", "second_definition": "inner floral whorl", "card_code": "Petal-2"},
        5,
        1,
    ),
    (
        "valve-pine-card",
        "Maintenance card: valve Pine closes clockwise. Its marker is white. Card revision: R3. Available study time is 16 minutes.",
        "Create exactly 2 positive-duration activities totaling 16 minutes. facts keys: valve, closing_direction, marker_color, card_revision. Use clockwise and white as the corresponding values.",
        {"valve": "Pine", "closing_direction": "clockwise", "marker_color": "white", "card_revision": "R3"},
        16,
        2,
    ),
]

cases = [
    {
        "id": case_id,
        "family": case_id,
        "lane": "roles",
        "split": "development",
        "provenance": "synthetic-authored",
        "source": source,
        "request": request + TASK_BOUNDARY,
        "gold": json.dumps(
            {
                "facts": facts,
                "minutes": minutes,
                "activity_count": activity_count,
                "forbidden": [],
            }
        ),
        "rubric": "role-exact-v1",
    }
    for case_id, source, request, facts, minutes, activity_count in rows
]

manifest = {
    "version": "quality-campaign-v1",
    "id": "m3-text-iteration-20260913-round3",
    "purpose": (
        "Third entity/source-disjoint synthetic pure-text development round comparing baseline "
        "with one source-minimal generation. Automated results cover structure and exact fields, "
        "not semantic quality; every complete Draft requires clause-by-clause manual semantic review."
    ),
    "transport": "minimax",
    "adapter": "vibe_learner.role_exploration:run_sample",
    "concurrency": 2,
    "seed": 913,
    "repetitions": 1,
    "timeout_seconds": 60,
    "sample_deadline_seconds": 600,
    "sample_wire_limit": 1,
    "max_output_tokens": 4096,
    "input_reservation_tokens": 100000,
    "thinking": "adaptive",
    "temperature": 0.1,
    "budget": json.loads(args.budget_from.read_text())["budget"],
    "cases": cases,
    "variants": [
        {"id": "baseline", "instruction": "One generation"},
        {
            "id": "source-minimal",
            "instruction": "One generation constrained to a source-minimal learner prompt",
        },
    ],
}

args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
