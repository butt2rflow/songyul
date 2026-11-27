"""Intel HEX -> UF2 for the XIAO nRF52840 bootloader (family 0xADA52840), for flashing locally built firmware via the bootloader drive.
  python hex_to_uf2.py in.hex out.uf2"""
import struct, sys

def read_hex(path):
    mem, base = {}, 0
    for line in open(path):
        line = line.strip()
        if not line.startswith(":"): continue
        b = bytes.fromhex(line[1:]); n, addr, typ, data = b[0], (b[1] << 8) | b[2], b[3], b[4:4 + b[0]]
        if (sum(b) & 0xFF) != 0: raise ValueError(f"bad checksum: {line}")
        if typ == 0:
            for i, x in enumerate(data): mem[base + addr + i] = x
        elif typ == 2: base = int.from_bytes(data, "big") << 4
        elif typ == 4: base = int.from_bytes(data, "big") << 16
        elif typ == 1: break
    return mem

def to_uf2(mem, family=0xADA52840):
    pages = sorted({a & ~0xFF for a in mem})
    out = []
    for i, p in enumerate(pages):
        data = bytes(mem.get(p + k, 0xFF) for k in range(256))
        hdr = struct.pack("<IIIIIIII", 0x0A324655, 0x9E5D5157, 0x00002000, p, 256, i, len(pages), family)
        out.append(hdr + data + b"\x00" * (476 - 256) + struct.pack("<I", 0x0AB16F30))
    return b"".join(out)

if __name__ == "__main__":
    mem = read_hex(sys.argv[1]); uf2 = to_uf2(mem)
    open(sys.argv[2], "wb").write(uf2)
    print(f"{len(mem)} bytes at 0x{min(mem):X}-0x{max(mem):X} -> {len(uf2) // 512} blocks, {sys.argv[2]}")
