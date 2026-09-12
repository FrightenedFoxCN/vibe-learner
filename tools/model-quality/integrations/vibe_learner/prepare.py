"""Prepare four bounded adapter samples, without sending provider requests."""
import argparse
import json
from pathlib import Path

from .fixtures import campaign


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=['fake', 'minimax'], default='fake')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--prefix', default='domain-v1')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    budget = campaign('study').budget.model_dump()
    for domain in ('study', 'tavern'):
        c = campaign(domain, args.transport, args.prefix + '-' + domain, budget)
        with (args.output_dir / (domain + '.json')).open('x', encoding='utf-8') as stream:
            json.dump(c.model_dump(), stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(args.output_dir.resolve())


if __name__ == '__main__':
    main()
