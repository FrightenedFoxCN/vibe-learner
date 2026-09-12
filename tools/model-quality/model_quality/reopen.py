"""Audited restart after a drained provider overload; does not retry samples."""
import argparse
from pathlib import Path
from .ledger import Ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--concurrency', type=int, required=True)
    parser.add_argument('--reason', required=True)
    args = parser.parse_args()
    Ledger(args.ledger).reopen_overload(concurrency=args.concurrency, reason=args.reason)
    print('Overload restart recorded; historical usage and sample outcomes retained.')


if __name__ == '__main__':
    main()
