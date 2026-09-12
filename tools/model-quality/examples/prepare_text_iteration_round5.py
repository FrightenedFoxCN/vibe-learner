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
        "proposed-neris-acoustic",
        "Design note dated 2027-04-06: an acoustic survey of Inlet Cedar is proposed for Thursday at 07:25. Proposed lead: Ivo. Suggested equipment: towed hydrophone array Neris-40. Learning allowance: 12 minutes.",
        "Create exactly 3 positive-duration activities totaling 12 minutes. facts keys: proposed_activity, survey_site, proposed_day, proposed_time, proposed_lead, suggested_equipment. Use acoustic survey for proposed_activity, render proposed_time as HH:MM, and preserve the remaining source values.",
        {"proposed_activity": "acoustic survey", "survey_site": "Inlet Cedar", "proposed_day": "Thursday", "proposed_time": "07:25", "proposed_lead": "Ivo", "suggested_equipment": "towed hydrophone array Neris-40"},
        12,
        3,
    ),
    (
        "scheduled-orchid-ventilation",
        "Facilities calendar issued 2027-04-08: a ventilation test for Conservatory Wing Orchid is scheduled on 2027-04-19 at 06:40. Assigned engineer: Sena. Calendar status: scheduled. Study budget: 9 minutes.",
        "Create exactly 2 positive-duration activities totaling 9 minutes. facts keys: scheduled_activity, location, scheduled_date, scheduled_time, assigned_engineer, calendar_status. Use ventilation test for scheduled_activity, render the date and time exactly, and preserve the other source values.",
        {"scheduled_activity": "ventilation test", "location": "Conservatory Wing Orchid", "scheduled_date": "2027-04-19", "scheduled_time": "06:40", "assigned_engineer": "Sena", "calendar_status": "scheduled"},
        9,
        2,
    ),
    (
        "planned-lumen-antenna",
        "Coordination memo: antenna alignment at Ridge Lumen is planned for Monday. Coordinator: Pavo. Named equipment: dual-band dish antenna Corax-18. Learning time: 13 minutes.",
        "Create exactly 2 positive-duration activities totaling 13 minutes. facts keys: planned_activity, site, planned_day, coordinator, named_equipment. Use antenna alignment for planned_activity and preserve all remaining values exactly.",
        {"planned_activity": "antenna alignment", "site": "Ridge Lumen", "planned_day": "Monday", "coordinator": "Pavo", "named_equipment": "dual-band dish antenna Corax-18"},
        13,
        2,
    ),
    (
        "proposed-sorrel-transfer",
        "Draft transfer sheet: moving specimen folio Heron-63 from Reading Room Sorrel to Archive Vault Umber is proposed for 2027-05-03. Proposed carrier: insulated document case Vale-22. Sheet state: proposed. Study allocation: 6 minutes.",
        "Create exactly one 6-minute activity. facts keys: folio, origin, proposed_destination, proposed_date, proposed_carrier, sheet_state. Preserve every value and the ISO date exactly.",
        {"folio": "specimen folio Heron-63", "origin": "Reading Room Sorrel", "proposed_destination": "Archive Vault Umber", "proposed_date": "2027-05-03", "proposed_carrier": "insulated document case Vale-22", "sheet_state": "proposed"},
        6,
        1,
    ),
    (
        "scheduled-pyre-turbine",
        "Maintenance board snapshot: inspection of ventilation turbine Pyre-27 is scheduled for 2027-05-11 at 14:10. Assigned name: Kala. Board label: scheduled. Learning budget: 10 minutes.",
        "Create exactly 2 positive-duration activities totaling 10 minutes. facts keys: scheduled_activity, device, scheduled_for, assigned_name, board_label. Use inspection for scheduled_activity, render scheduled_for as YYYY-MM-DD HH:MM, and preserve the remaining values.",
        {"scheduled_activity": "inspection", "device": "ventilation turbine Pyre-27", "scheduled_for": "2027-05-11 14:10", "assigned_name": "Kala", "board_label": "scheduled"},
        10,
        2,
    ),
    (
        "planned-selene-water-sample",
        "Field planning card: groundwater sampling at Monitoring Well Selene is planned for Friday at 08:35. Lead: Runa. Specified device: low-flow sampling pump Aven-9. Study period: 15 minutes.",
        "Create exactly 3 positive-duration activities totaling 15 minutes. facts keys: planned_activity, site, planned_day, planned_time, lead, specified_device. Use groundwater sampling for planned_activity, render planned_time as HH:MM, and preserve other values exactly.",
        {"planned_activity": "groundwater sampling", "site": "Monitoring Well Selene", "planned_day": "Friday", "planned_time": "08:35", "lead": "Runa", "specified_device": "low-flow sampling pump Aven-9"},
        15,
        3,
    ),
    (
        "docked-brindle-service-berth",
        "Harbor entry: cargo tug Brindle-52 docked at Service Berth Lilac at 02:18. Mooring duration: 37 minutes. Harbor clerk: Osa. Study allowance: 8 minutes.",
        "Create exactly 2 positive-duration activities totaling 8 minutes. facts keys: vessel, berth, docked_at, mooring_minutes, harbor_clerk. Render time as HH:MM, use a number alone for mooring_minutes, and preserve source names.",
        {"vessel": "cargo tug Brindle-52", "berth": "Service Berth Lilac", "docked_at": "02:18", "mooring_minutes": "37", "harbor_clerk": "Osa"},
        8,
        2,
    ),
    (
        "measured-elara-spectrum",
        "Bench note: portable Raman spectrometer Elara-14 measured a peak at 812 cm⁻¹ at 11:32. Operator: Toma. Note status: retained. Learning time: 11 minutes.",
        "Create exactly 2 positive-duration activities totaling 11 minutes. facts keys: instrument, measured_peak, peak_unit, measured_at, operator, note_status. Use a number alone for measured_peak, render time as HH:MM, and preserve the unit and other values.",
        {"instrument": "portable Raman spectrometer Elara-14", "measured_peak": "812", "peak_unit": "cm⁻¹", "measured_at": "11:32", "operator": "Toma", "note_status": "retained"},
        11,
        2,
    ),
    (
        "listed-cirrus-fan",
        "Asset excerpt: emergency ventilation fan Cirrus-8 is listed as available in Mechanical Bay Violet. Custodian: Eren. Entry date: 2027-05-16. Study allocation: 5 minutes.",
        "Create exactly one 5-minute activity. facts keys: asset, listed_status, location, custodian, entry_date. Preserve complete source values and the ISO date.",
        {"asset": "emergency ventilation fan Cirrus-8", "listed_status": "available", "location": "Mechanical Bay Violet", "custodian": "Eren", "entry_date": "2027-05-16"},
        5,
        1,
    ),
    (
        "reported-vela-pump",
        "Radio note: technician Mira reported that circulation pump Vela-31 made two clicking sounds. Dispatcher Noa transcribed the statement at 17:46. Learning budget: 14 minutes.",
        "Create exactly 3 positive-duration activities totaling 14 minutes. facts keys: reporter, reported_subject, reported_event, transcriber, transcribed_at. Use made two clicking sounds for reported_event, render time as HH:MM, and preserve the remaining values.",
        {"reporter": "Mira", "reported_subject": "circulation pump Vela-31", "reported_event": "made two clicking sounds", "transcriber": "Noa", "transcribed_at": "17:46"},
        14,
        3,
    ),
    (
        "observed-pelican-shadow",
        "Observation slip: after a cloud shadow crossed Lagoon Pelican, three terns settled beside Marker Post Sienna. Biologist Aru observed the sequence once. Study time: 7 minutes.",
        "Create exactly one 7-minute activity. facts keys: observer, first_event, later_event, observation_count. Preserve both event clauses and use a number alone for observation_count.",
        {"observer": "Aru", "first_event": "a cloud shadow crossed Lagoon Pelican", "later_event": "three terns settled beside Marker Post Sienna", "observation_count": "1"},
        7,
        1,
    ),
    (
        "recorded-lyra-detector",
        "Instrument record: ultraviolet flame detector Lyra-6 recorded one alert at 04:52. Display code: F2. Recorder status: active. Learning allowance: 16 minutes.",
        "Create exactly 3 positive-duration activities totaling 16 minutes. facts keys: instrument, recorded_event, recorded_at, display_code, recorder_status. Use one alert for recorded_event, render time as HH:MM, and preserve complete source values.",
        {"instrument": "ultraviolet flame detector Lyra-6", "recorded_event": "one alert", "recorded_at": "04:52", "display_code": "F2", "recorder_status": "active"},
        16,
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
    "id": "m3-text-iteration-20260913-round5",
    "purpose": (
        "Fifth entity/source-disjoint synthetic pure-text development round comparing source-minimal v2 "
        "with targeted v3. This remains development evidence, not an independent holdout. Automated "
        "results cover structure and exact fields, not semantic quality; every complete Draft requires "
        "clause-by-clause manual semantic review."
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
        {"id": "source-minimal-v2", "instruction": "One generation constrained to source-minimal v2"},
        {"id": "source-minimal-v3", "instruction": "One generation constrained to targeted source-minimal v3"},
    ],
}

args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
