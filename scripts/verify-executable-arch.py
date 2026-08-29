#!/usr/bin/env python3

import argparse
import struct
import sys
from pathlib import Path


EXPECTED = {
    "linux/amd64": ("ELF", 62),
    "linux/arm64": ("ELF", 183),
    "darwin/amd64": ("Mach-O", 0x01000007),
    "darwin/arm64": ("Mach-O", 0x0100000C),
    "windows/amd64": ("PE", 0x8664),
    "windows/arm64": ("PE", 0xAA64),
}

FAT_MACHO_MAGICS = {
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf",
    b"\xbf\xba\xfe\xca",
}

MACHO_64_MAGICS = {
    b"\xcf\xfa\xed\xfe": "<",
    b"\xfe\xed\xfa\xcf": ">",
}

MACHO_32_MAGICS = {
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xce",
}


class VerificationError(Exception):
    pass


def parse_elf(data: bytes) -> tuple[str, int]:
    if len(data) < 64:
        raise VerificationError("truncated ELF header")
    if data[4] != 2:
        raise VerificationError("ELF binary is not 64-bit")
    if data[5] == 1:
        byte_order = "<"
    elif data[5] == 2:
        byte_order = ">"
    else:
        raise VerificationError("unsupported ELF byte order")
    return "ELF", struct.unpack_from(f"{byte_order}H", data, 18)[0]


def parse_macho(data: bytes) -> tuple[str, int]:
    if data[:4] in MACHO_32_MAGICS:
        raise VerificationError("Mach-O binary is not 64-bit")
    if len(data) < 32:
        raise VerificationError("truncated Mach-O header")
    byte_order = MACHO_64_MAGICS[data[:4]]
    return "Mach-O", struct.unpack_from(f"{byte_order}I", data, 4)[0]


def parse_pe(data: bytes) -> tuple[str, int]:
    if len(data) < 0x40:
        raise VerificationError("truncated PE DOS header")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 4 > len(data):
        raise VerificationError("truncated PE header")
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise VerificationError("invalid PE signature")
    if pe_offset + 24 > len(data):
        raise VerificationError("truncated PE COFF header")
    return "PE", struct.unpack_from("<H", data, pe_offset + 4)[0]


def parse_executable(data: bytes) -> tuple[str, int]:
    if data.startswith(b"\x7fELF"):
        return parse_elf(data)
    if data[:4] in FAT_MACHO_MAGICS:
        raise VerificationError("fat Mach-O binaries are not supported")
    if data[:4] in MACHO_64_MAGICS or data[:4] in MACHO_32_MAGICS:
        return parse_macho(data)
    if data.startswith(b"MZ"):
        return parse_pe(data)
    raise VerificationError("unknown executable format")


def verify(platform: str, executable: Path) -> tuple[str, int]:
    expected = EXPECTED.get(platform)
    if expected is None:
        raise VerificationError(f"unsupported platform: {platform}")

    try:
        actual = parse_executable(executable.read_bytes())
    except OSError as error:
        raise VerificationError(f"cannot read executable: {error}") from error

    if actual != expected:
        raise VerificationError(
            f"architecture mismatch: expected format={expected[0]} machine={expected[1]}, "
            f"got format={actual[0]} machine={actual[1]}"
        )
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True)
    parser.add_argument("--file", required=True, type=Path)
    args = parser.parse_args()

    try:
        executable_format, machine = verify(args.platform, args.file)
    except VerificationError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"format={executable_format} machine={machine} platform={args.platform}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
