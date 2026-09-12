"""Explicit, audited extension of an existing resource window; never resets usage."""
import argparse
from pathlib import Path

from .ledger import Ledger
from .protocol import Campaign


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    campaign = Campaign.model_validate_json(args.manifest.read_text())
    ledger = Ledger(args.ledger)
    # Upgrade table layout using the current configuration, not the requested grant.
    with ledger.transaction() as db:
        import json
        from .protocol import Budget
        current = json.loads(db.execute('SELECT config FROM settings WHERE id=1').fetchone()[0])
    if campaign.transport != current['transport']:
        raise ValueError('transport mismatch')
    ledger.initialize(Budget.model_validate(current['budget']), current['transport'])
    ledger.amend_budget(campaign.budget, args.reason)
    print('Budget amendment recorded; existing usage retained.')


if __name__ == '__main__':
    main()
