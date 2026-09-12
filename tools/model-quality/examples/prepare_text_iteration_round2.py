import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--budget-from", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()


rows = [
    (
        "cold-chain-replica-exception",
        "Dispatch rule: an ordinary research specimen may leave cold storage only when its tamper seal is intact. The only exception is a crate explicitly classified as a training replica. Crate Vela-8 is classified as a research specimen, and its seal is broken. Available study time is 11 minutes.",
        "Create exactly 2 positive-duration activities totaling 11 minutes. facts keys: crate_id, classification, seal_status, dispatch_eligible. Preserve source wording for the first three values; use yes or no for eligibility. Do not apply the training-replica exception to a research specimen.",
        {"crate_id": "Vela-8", "classification": "research specimen", "seal_status": "broken", "dispatch_eligible": "no"},
        11,
        2,
    ),
    (
        "roof-endorsement-scope",
        "Badge policy: a general badge covers the ground floor and mezzanine. Roof access requires a separate Zone R endorsement. Amal has a general badge; the register explicitly says Zone R endorsement: no. Amal's requested destination is the roof. Available study time is 8 minutes.",
        "Create exactly 2 positive-duration activities totaling 8 minutes. facts keys: badge_type, zone_r_endorsement, destination, access_eligible. Use the exact values general, no, roof, and the derived yes/no eligibility. Do not broaden the general badge's scope.",
        {"badge_type": "general", "zone_r_endorsement": "no", "destination": "roof", "access_eligible": "no"},
        8,
        2,
    ),
    (
        "ferry-authority-waiver",
        "Reservation policy: cancelling fewer than 24 hours before departure normally incurs an 18-euro fee. The fee is waived when the transit authority cancels the route. The transit authority cancelled Ferry Kestrel. Passenger Elio released the seat 3 hours before departure, after the route cancellation. Available study time is 14 minutes.",
        "Create exactly 3 positive-duration activities totaling 14 minutes. facts keys: route, passenger, notice_hours, fee_due. Route and passenger use source names, notice_hours is a number alone, and fee_due is yes or no. Apply the stated waiver.",
        {"route": "Ferry Kestrel", "passenger": "Elio", "notice_hours": "3", "fee_due": "no"},
        14,
        3,
    ),
    (
        "refurbished-pack-exclusion",
        "Warranty card: cell packs installed on or after 2026-01-01 normally receive two years of coverage. Refurbished packs are excluded regardless of installation date. Pack Mica is refurbished and was installed on 2026-02-14. Available study time is 7 minutes.",
        "Create exactly one 7-minute activity. facts keys: pack, installed_date, refurbished, warranty_eligible. Preserve the ISO date; use yes or no for the last two values. The date threshold does not override the refurbished exclusion.",
        {"pack": "Mica", "installed_date": "2026-02-14", "refurbished": "yes", "warranty_eligible": "no"},
        7,
        1,
    ),
    (
        "tariff-recorded-effective",
        "Tariff memo: the entry was recorded at 09:10 and approved at 09:30 on 2026-11-03. The lunch price changes from 64 credits to 72 credits when the memo takes effect at 12:00 that day. Order Q7 was placed at 11:45. Available study time is 12 minutes.",
        "Create exactly 3 positive-duration activities totaling 12 minutes. facts keys: recorded_at, approved_at, effective_at, order_q7_price. Render timestamps exactly as YYYY-MM-DD HH:MM and the price as a number alone. Use the price effective when Q7 was placed.",
        {"recorded_at": "2026-11-03 09:10", "approved_at": "2026-11-03 09:30", "effective_at": "2026-11-03 12:00", "order_q7_price": "64"},
        12,
        3,
    ),
    (
        "license-entry-suspension",
        "Registry note: license Cedar-4 was entered as scheduled for suspension on 2026-05-02. The suspension begins at 2026-05-08 00:00; the license remains active through 2026-05-07 23:59. An inspection occurred at 2026-05-07 16:20. Available study time is 9 minutes.",
        "Create exactly 2 positive-duration activities totaling 9 minutes. facts keys: registry_entry_date, suspension_effective, inspection_at, status_at_inspection. Render registry_entry_date exactly as YYYY-MM-DD and both timestamps exactly as YYYY-MM-DD HH:MM; status must be active or suspended. Do not treat registry entry as immediate effect.",
        {"registry_entry_date": "2026-05-02", "suspension_effective": "2026-05-08 00:00", "inspection_at": "2026-05-07 16:20", "status_at_inspection": "active"},
        9,
        2,
    ),
    (
        "dispatcher-relayed-report",
        "Handover transcript: dispatcher Amina read aloud, “Courier Hugo reports that parcel Lark arrived wet.” Recipient Sora signed the acknowledgement. Amina did not inspect the parcel. Available study time is 10 minutes.",
        "Create exactly 2 positive-duration activities totaling 10 minutes. facts keys: report_source, relay_speaker, recipient, reported_condition. Keep the reporter, the person speaking aloud, and the recipient distinct.",
        {"report_source": "Hugo", "relay_speaker": "Amina", "recipient": "Sora", "reported_condition": "wet"},
        10,
        2,
    ),
    (
        "supplier-delay-attribution",
        "Meeting minute: Ruan, procurement lead at Ardent Ltd, said, “Our shipment will be 8 days late.” Clerk Inez wrote the minute. Auditor Mei asked a question but gave no delay estimate. Available study time is 15 minutes.",
        "Create exactly 3 positive-duration activities totaling 15 minutes. facts keys: estimate_speaker, speaker_organization, recorder, delay_days. Preserve names and organization; delay_days is a number alone. Do not attribute the estimate to the clerk or auditor.",
        {"estimate_speaker": "Ruan", "speaker_organization": "Ardent Ltd", "recorder": "Inez", "delay_days": "8"},
        15,
        3,
    ),
    (
        "quarantine-bin-unknown",
        "Prose inventory note (not a chart or table): the north bin contains 23 seals and the south bin contains 17 seals. The quarantine-bin count is not reported. The all-bin total is therefore not established by the note. Available study time is 6 minutes.",
        "Create exactly one 6-minute activity. facts keys: north_count, south_count, quarantine_count, all_bins_total. Counts are numbers alone; use exactly unknown for unestablished values. This is a prose fact exercise: chart_questions must be empty.",
        {"north_count": "23", "south_count": "17", "quarantine_count": "unknown", "all_bins_total": "unknown"},
        6,
        1,
    ),
    (
        "appointment-room-only-correction",
        "Appointment entry dated 2026-10-02: visit at 08:20 in Room Elm. Correction dated 2026-10-03: “Only the room changes to Birch; the visit remains at 08:20.” Neither entry names a clinician. Available study time is 13 minutes.",
        "Create exactly 2 positive-duration activities totaling 13 minutes. facts keys: visit_time, room, clinician, corrected_field. Render visit_time exactly as HH:MM. Apply only the explicit correction; use exactly unknown when absent. corrected_field must be the source noun alone.",
        {"visit_time": "08:20", "room": "Birch", "clinician": "unknown", "corrected_field": "room"},
        13,
        2,
    ),
    (
        "pallet-mass-amendment",
        "Cargo manifest: pallet D14, destination Oslo, mass 480 kg. A later amendment says, “Replace only the mass 480 kg with 408 kg; every other manifest field is unchanged.” No departure date appears. Available study time is 16 minutes.",
        "Create exactly 3 positive-duration activities totaling 16 minutes. facts keys: pallet, destination, mass_kg, departure_date. Apply the amendment only to its named field; mass_kg is a number alone and missing information is exactly unknown.",
        {"pallet": "D14", "destination": "Oslo", "mass_kg": "408", "departure_date": "unknown"},
        16,
        3,
    ),
    (
        "single-salinity-no-chart",
        "Field note: Lake Orin salinity was 7 ppt at noon, measured once with a probe. The note contains no time series, comparison group, chart, or table. Available study time is 5 minutes.",
        "Create exactly one 5-minute text activity. facts keys: site, salinity, unit, instrument. Use source words and a number alone for salinity. Do not invent trends, comparisons, media, or chart questions; chart_questions must be empty.",
        {"site": "Lake Orin", "salinity": "7", "unit": "ppt", "instrument": "probe"},
        5,
        1,
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
        "request": request,
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
    "id": "m3-text-iteration-20260913-round2",
    "purpose": (
        "Second entity/source-disjoint synthetic development round comparing baseline "
        "with a single-call constraint checklist. Exact rubric results are audit signals "
        "only, not semantic-quality scores and not independently reviewed evidence."
    ),
    "transport": "minimax",
    "adapter": "vibe_learner.role_exploration:run_sample",
    "concurrency": 2,
    "seed": 913,
    "repetitions": 1,
    "timeout_seconds": 60,
    "sample_deadline_seconds": 600,
    "sample_wire_limit": 3,
    "max_output_tokens": 4096,
    "input_reservation_tokens": 100000,
    "thinking": "adaptive",
    "temperature": 0.1,
    "budget": json.loads(args.budget_from.read_text())["budget"],
    "cases": cases,
    "variants": [
        {"id": "baseline", "instruction": "One generation"},
        {
            "id": "constraint-checklist",
            "instruction": "One generation with a silent constraint checklist",
        },
    ],
}

args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
