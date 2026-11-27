#!/usr/bin/env python3
"""Fail if the proto.h copies in the firmware folders differ (Arduino sketches cannot share a header)."""
import hashlib, pathlib, sys
fw = pathlib.Path(__file__).resolve().parent.parent / "firmware"
h = {p.parent.name: hashlib.sha1(p.read_bytes()).hexdigest()[:10] for p in sorted(fw.glob("*/proto.h"))}
print(h)
sys.exit(0 if len(set(h.values())) == 1 else "proto.h copies differ: copy firmware/xiao_usb_stream/proto.h to the others")
