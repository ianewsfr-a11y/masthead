"""Check that the sources of the shipped preset lists still answer.

Runs Horizon's collector on each source alone, over the last 7 days, in a scratch folder,
exactly as MastHead's source test does. Reads every source: it needs the network and takes
a while. No model is called.

    python tools/check_preset_sources.py                 # the lists in masthead/presets/
    python tools/check_preset_sources.py my-list.json    # one file

Exit code 1 when a source failed, so it can run on a schedule.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from masthead import tls
from masthead.horizon_setup import test
from masthead.preset_lists import HORIZON_FILE, SHIPPED_DIR, _check_list


async def main(paths: list[Path]) -> int:
    tls.use_system_trust()
    failed = 0
    for path in paths:
        for theme in _check_list(json.loads(path.read_text(encoding="utf-8"))):
            print(f"\n{path.name} - {theme['name']}")
            for source in theme["sources"]:
                result = await test(source)
                label = source["description"] or json.dumps(source["config"])
                print(f"  {result['status']:6} {result['items']:3}  {label}"
                      + (f"  ({result['error']})" if result["status"] == "failed" else ""))
                failed += result["status"] == "failed"
    print(f"\n{failed} failed" if failed else "\nEvery source answered.")
    return 1 if failed else 0


if __name__ == "__main__":
    chosen = [Path(arg) for arg in sys.argv[1:]] or [p for p in sorted(SHIPPED_DIR.glob("*.json")) if p != HORIZON_FILE]
    raise SystemExit(asyncio.run(main(chosen)))
