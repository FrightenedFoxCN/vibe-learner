import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--budget-from", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()


TASK_BOUNDARY = " This is text-only; chart_questions must be empty."

rows = [
    (
        "tram-dwell-nacre",
        "Transit digest: tram Nacre-12 remained at Platform Moss from 05:48 until 06:17; the documented dwell was 29 minutes. Learner study budget: 8 minutes.",
        "Create exactly 2 positive-duration activities totaling 8 minutes. facts keys: tram, platform, dwell_start, dwell_end, dwell_minutes. Preserve the source identifiers, render times as HH:MM, and use a number alone for dwell_minutes.",
        {"tram": "Nacre-12", "platform": "Platform Moss", "dwell_start": "05:48", "dwell_end": "06:17", "dwell_minutes": "29"},
        8,
        2,
    ),
    (
        "batch-cooling-saffron",
        "Process summary: batch Saffron-21 cooled from 110 °C to 24 °C over 75 minutes. Learning time available: 7 minutes.",
        "Create exactly one 7-minute activity. facts keys: batch, start_temperature, end_temperature, temperature_unit, cooling_minutes. Temperatures and cooling_minutes are numbers alone; preserve the stated unit.",
        {"batch": "Saffron-21", "start_temperature": "110", "end_temperature": "24", "temperature_unit": "°C", "cooling_minutes": "75"},
        7,
        1,
    ),
    (
        "rehearsal-span-echo",
        "Archive log: rehearsal Echo-17 ran from 19:10 to 20:35 and lasted 85 minutes. Conductor: Luma. Time reserved for learning: 11 minutes.",
        "Create exactly 2 positive-duration activities totaling 11 minutes. facts keys: rehearsal, start_time, end_time, duration_minutes, conductor. Render times as HH:MM and duration_minutes as a number alone.",
        {"rehearsal": "Echo-17", "start_time": "19:10", "end_time": "20:35", "duration_minutes": "85", "conductor": "Luma"},
        11,
        2,
    ),
    (
        "barge-unloading-tern",
        "Freight receipt: unloading barge Tern-44 at Quay Amber began at 03:12 and occupied 44 minutes. Foreperson: Kes. Study allocation: 9 minutes.",
        "Create exactly 3 positive-duration activities totaling 9 minutes. facts keys: barge, quay, unloading_start, unloading_minutes, foreperson. Render the time as HH:MM and unloading_minutes as a number alone.",
        {"barge": "Tern-44", "quay": "Quay Amber", "unloading_start": "03:12", "unloading_minutes": "44", "foreperson": "Kes"},
        9,
        3,
    ),
    (
        "proposed-marsh-survey",
        "Concept brief: an aerial survey of Marsh Fenwick is proposed for next Tuesday at 09:15. Proposed lead: Oren. Suggested instrument: magnetometer. Study allowance: 12 minutes.",
        "Create exactly 3 positive-duration activities totaling 12 minutes. facts keys: proposed_activity, site, proposed_day, proposed_time, proposed_lead, suggested_instrument. Use aerial survey for proposed_activity and render proposed_time as HH:MM.",
        {"proposed_activity": "aerial survey", "site": "Marsh Fenwick", "proposed_day": "next Tuesday", "proposed_time": "09:15", "proposed_lead": "Oren", "suggested_instrument": "magnetometer"},
        12,
        3,
    ),
    (
        "scheduled-mural-cleaning",
        "The conservation calendar holds mural cleaning for Gallery Sable on 2027-01-09 at 08:00. Niva is assigned. Calendar state: scheduled. Learning budget: 10 minutes.",
        "Create exactly 2 positive-duration activities totaling 10 minutes. facts keys: activity, location, scheduled_date, scheduled_time, assigned_person, calendar_state. Preserve source values and render the date/time as ISO date and HH:MM.",
        {"activity": "mural cleaning", "location": "Gallery Sable", "scheduled_date": "2027-01-09", "scheduled_time": "08:00", "assigned_person": "Niva", "calendar_state": "scheduled"},
        10,
        2,
    ),
    (
        "planned-mesa-core",
        "Planning memo: soil-core collection at Mesa Dray is planned for Monday. Coordinator: Yara. Named equipment: rotary corer. Study period: 13 minutes.",
        "Create exactly 2 positive-duration activities totaling 13 minutes. facts keys: planned_activity, site, planned_day, coordinator, named_equipment. Use soil-core collection for planned_activity and preserve the remaining source values.",
        {"planned_activity": "soil-core collection", "site": "Mesa Dray", "planned_day": "Monday", "coordinator": "Yara", "named_equipment": "rotary corer"},
        13,
        2,
    ),
    (
        "proposed-case-relocation",
        "Draft proposal: relocate archive case Kite-28 from Bay Linen to Vault Pecan on 2027-02-18. Proposal owner: Dev. Proposal status: proposed. Available learning time: 6 minutes.",
        "Create exactly one 6-minute activity. facts keys: case, origin, proposed_destination, proposed_date, proposal_owner, proposal_status. Preserve names and the ISO date.",
        {"case": "Kite-28", "origin": "Bay Linen", "proposed_destination": "Vault Pecan", "proposed_date": "2027-02-18", "proposal_owner": "Dev", "proposal_status": "proposed"},
        6,
        1,
    ),
    (
        "reported-solace-tones",
        "Telephone note: Niko reported that beacon Solace-3 emitted three short tones. Scribe Pera wrote down the report at 21:06. Learning budget: 14 minutes.",
        "Create exactly 3 positive-duration activities totaling 14 minutes. facts keys: reporter, reported_subject, reported_event, scribe, note_time. Use emitted three short tones for reported_event and render note_time as HH:MM.",
        {"reporter": "Niko", "reported_subject": "beacon Solace-3", "reported_event": "emitted three short tones", "scribe": "Pera", "note_time": "21:06"},
        14,
        3,
    ),
    (
        "listed-thistle-condition",
        "Catalog excerpt: specimen Thistle-26 is listed as brittle in drawer Quartz. Cataloguer: Rafi. Entry date: 2027-03-02. Study time: 5 minutes.",
        "Create exactly one 5-minute activity. facts keys: specimen, listed_condition, drawer, cataloguer, entry_date. Preserve identifiers and the ISO date.",
        {"specimen": "Thistle-26", "listed_condition": "brittle", "drawer": "Quartz", "cataloguer": "Rafi", "entry_date": "2027-03-02"},
        5,
        1,
    ),
    (
        "observed-wren-sequence",
        "Observer card: Zuri saw reeds bend after a wake crossed channel Wren. The sequence was observed once. Viewing point: Dock Juniper. Learning allocation: 8 minutes.",
        "Create exactly 2 positive-duration activities totaling 8 minutes. facts keys: observer, first_event, later_event, observation_count, viewing_point. Preserve the event clauses; observation_count is a number alone.",
        {"observer": "Zuri", "first_event": "a wake crossed channel Wren", "later_event": "reeds bend", "observation_count": "1", "viewing_point": "Dock Juniper"},
        8,
        2,
    ),
    (
        "recorded-aster-spike",
        "Instrument ledger: gauge Aster-15 recorded a pressure spike at 04:27. Displayed peak: 18 kPa. Ledger state: retained. Study allowance: 15 minutes.",
        "Create exactly 3 positive-duration activities totaling 15 minutes. facts keys: instrument, recorded_event, recorded_at, peak_value, peak_unit, ledger_state. Use pressure spike for recorded_event, render time as HH:MM, and use a number alone for peak_value.",
        {"instrument": "gauge Aster-15", "recorded_event": "pressure spike", "recorded_at": "04:27", "peak_value": "18", "peak_unit": "kPa", "ledger_state": "retained"},
        15,
        3,
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
            {"facts": facts, "minutes": minutes, "activity_count": activity_count, "forbidden": []}
        ),
        "rubric": "role-exact-v1",
    }
    for case_id, source, request, facts, minutes, activity_count in rows
]

manifest = {
    "version": "quality-campaign-v1",
    "id": "m3-text-iteration-20260913-round4",
    "purpose": (
        "Fourth entity/source-disjoint synthetic pure-text development round comparing source-minimal v1 "
        "with a targeted v2. Automated results cover structure and exact fields, not semantic quality; "
        "every complete Draft requires clause-by-clause manual semantic review."
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
        {"id": "source-minimal", "instruction": "One generation constrained to source-minimal v1"},
        {"id": "source-minimal-v2", "instruction": "One generation constrained to targeted source-minimal v2"},
    ],
}

args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
