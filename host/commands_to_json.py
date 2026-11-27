#!/usr/bin/env python3
"""Write the voice commands (commands.example.yaml) as JSON for the phone page (phone/commands.json), so the
PC (voice.py) and the phone (voice.js) match against the same list. Re-run after editing the YAML:

  python3 host/commands_to_json.py [commands.example.yaml] [phone/commands.json]
"""
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "commands.example.yaml"
dst = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else HERE.parent / "phone/commands.json"
cfg = yaml.safe_load(src.read_text(encoding="utf-8"))
out = {"min_score": cfg.get("min_score", 0.75)}
for key in ("prefixes", "players", "commands"):
    out[key] = [{**row, "say": {"ko": row["say"]} if isinstance(row["say"], list) else row["say"]}
                for row in cfg.get(key, [])]
out["source"] = f"generated from host/{src.name} by commands_to_json.py"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{len(out['commands'])} commands -> {dst}")
