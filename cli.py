"""Minimal test launcher. Run `python cli.py` and enter a .txt path."""
import argparse
from contextlib import redirect_stdout
from datetime import datetime
import os
from pathlib import Path
import secrets
import shlex
import sys

from main import extract_for_cli, plan_for_cli, run


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.removeprefix('export ').partition('=')
        key, value = key.strip(), value.strip()
        if separator and key and key.replace('_', '').isalnum():
            if value.startswith(('"', "'")):
                parts = shlex.split(value)
                if len(parts) != 1:
                    raise ValueError(f'Invalid .env value for {key}')
                value = parts[0]
            os.environ.setdefault(key, value)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', nargs='?', help='UTF-8 text file; prompted if omitted')
    parser.add_argument('--session', type=Path, help='Reuse this result directory for an update; default is a fresh test')
    args = parser.parse_args(argv)
    try:
        address = args.file if args.file is not None else input('Test file path: ')
        path = Path(address.strip().strip('\"\'')).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != '.txt':
            raise ValueError('Enter the path to an existing .txt file.')
        load_env(Path.cwd()/'.env')
        destination = args.session or Path('runtime/tests')/(datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(3))
        destination = destination.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        print('Running planner…', flush=True)
        with (destination/'execution.log').open('w',encoding='utf-8') as log, redirect_stdout(log):
            code = run(path,destination,extract_for_cli,plan_for_cli)
        print()
        print((destination/'plan.txt').read_text(encoding='utf-8'),end='')
        print(f'\nPlan saved:  {destination / "plan.txt"}')
        print(f'Trace saved: {destination / "trace.txt"}')
        print(f'For an update, reuse: --session "{destination}"')
        return code
    except (OSError, ValueError, EOFError, KeyboardInterrupt) as error:
        print(f'Could not run: {error}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
