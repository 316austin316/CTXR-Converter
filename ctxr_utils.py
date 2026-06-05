"""
Header layout (big-endian)
-------------------------------------------

    Offset  Size  Field              Notes
    ------  ----  -----------------  -------------------------------------
    0x00    4     magic              'TXTR'
    0x04    4     version            == 7
    0x08    2     width              uint16
    0x0A    2     height             uint16
    0x0C    2     depth              uint16  (1 for 2D)
    0x0E    4     format             uint32, see EFormat below
    0x12    1     hasAlpha           uint8
    0x13    4     additionalFlags    uint32, EAdditionalFlags bitfield
    0x17    4     minRGBA            uint32, packed 0xRRGGBBAA
    0x1B    4     maxRGBA            uint32, packed 0xRRGGBBAA
    0x1F    1     filterHint         int8,   EFilterHint (-1 = Default)
    0x20    1     alphaRefValue      uint8
    0x21    1     maxLODOffset       int8
    0x22    4     type               uint32  (0=Normal, 1=Cube)
    0x26    1     numLevels          uint8
    0x27..  0     padding            zeros to byte 128
"""

from __future__ import annotations

import logging
import os
import struct
from dataclasses import dataclass, field
from typing import BinaryIO, List, Optional, Tuple

logger = logging.getLogger(__name__)

# -afevis bugfix
# bp's texture cooker only wrote hasAlpha = false if all pixels were >= 255
# but mgs2 & mgs3 used ps2 alpha range, where 128 was opaque.
# doesn't actually change anything in game since it still uses the per-pixel 
# alpha levels, it's more just a header metadata correction for stuff we author.
HAS_ALPHA_USE_128_THRESHOLD = True


# ---------------------------------------------------------------------------

CTXR_MAGIC = b"TXTR"
CTXR_VERSION = 7
CTXR_HEADER_SIZE = 128
MIP_ALIGNMENT = 32

# CBaseTexture::EFormat values (CTexture.h)
FORMAT_A8R8G8B8 = 0
FORMAT_X8R8G8B8 = 1
FORMAT_A16B16G16R16F = 2
FORMAT_R32F = 3
FORMAT_D24X8 = 4
FORMAT_DXT1 = 5
FORMAT_DXT3 = 6
FORMAT_DXT5 = 7
FORMAT_A32B32G32R32F = 8
FORMAT_LUMINANCE8 = 9
FORMAT_D24FS8 = 10
FORMAT_YVU420P2_CSC1 = 11

FORMAT_NAMES = {
    0: "A8R8G8B8",
    1: "X8R8G8B8",
    2: "A16B16G16R16F",
    3: "R32F",
    4: "D24X8",
    5: "DXT1",
    6: "DXT3",
    7: "DXT5",
    8: "A32B32G32R32F",
    9: "Luminance8",
    10: "D24FS8",
    11: "YVU420P2_CSC1",
}

# CBaseTexture::EType
TYPE_NORMAL = 0
TYPE_CUBE = 1

# CBaseTexture::EFilterHint  (filterHint of -1 == kFH_Default in source)
FILTER_DEFAULT = -1
FILTER_POINT = 0
FILTER_BILINEAR = 1
FILTER_TRILINEAR = 2
FILTER_ANISO = 3


class CTXRError(Exception):
    """Raised for any malformed or unsupported CTXR data."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def num_mip_maps(width: int, height: int, depth: int = 1) -> int:
    # Number of mip levels down to 1x1.
    # 
    # For power-of-two textures, this matches Bluepoint's original cooker exactly.
    # 
    #         - Afevis bugfix from BP cooker:
    # For NPOT textures, Bluepoint's cooker had a bug where it over-counted by one, producing a duplicate 1x1 level at the end at of the file (e.g. 33x17 -> 7 levels instead of 6). 
    # This would cause the header to have the wrong mip count and the game would subsequently try reading garbage padding, breaking the smallest mips levels / causing a green shimmer effect.
    # This bug was probably why they resized all the NPOT textures with the HDC.... ugh.
    size = max(width, max(height, depth))
    if size <= 1:
        return 1
    return 1 + (size.bit_length() - 1) # equivalent to floor(log2(size)) for pos ints


def mip_dim(top: int, level: int) -> int:
    return max(1, top >> level)


def payload_size(width: int, height: int, fmt: int) -> int:
    """Size in bytes of one mip payload for the given top-level dims & format."""
    if fmt in (FORMAT_A8R8G8B8, FORMAT_X8R8G8B8):
        return width * height * 4
    if fmt == FORMAT_LUMINANCE8:
        return width * height
    if fmt == FORMAT_DXT1:
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 8
    if fmt in (FORMAT_DXT3, FORMAT_DXT5):
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
    raise CTXRError(f"unsupported format for size calc: {fmt}")


def align_pad(written_since_align: int, alignment: int = MIP_ALIGNMENT) -> int:
    """Bytes needed to advance a stream to the next ``alignment`` boundary."""
    return (alignment - (written_since_align % alignment)) % alignment


# ---------------------------------------------------------------------------

@dataclass
class CTXRHeader:
    width: int = 0
    height: int = 0
    depth: int = 1
    format: int = FORMAT_A8R8G8B8
    has_alpha: bool = False
    additional_flags: int = 0
    min_rgba: int = 0
    max_rgba: int = 0xFFFFFFFF
    filter_hint: int = FILTER_DEFAULT
    alpha_ref_value: int = 0
    max_lod_offset: int = 0
    type: int = TYPE_NORMAL
    num_levels: int = 1
    version: int = CTXR_VERSION

    def format_name(self) -> str:
        return FORMAT_NAMES.get(self.format, f"format_{self.format}")

    def is_compressed(self) -> bool:
        return self.format in (FORMAT_DXT1, FORMAT_DXT3, FORMAT_DXT5)


@dataclass
class CTXRTexture:
    header: CTXRHeader = field(default_factory=CTXRHeader)
    mips: List[bytes] = field(default_factory=list)


# ---------------------------------------------------------------------------

def parse_header(buf: bytes) -> CTXRHeader:
    if len(buf) < CTXR_HEADER_SIZE:
        raise CTXRError(f"header too short: {len(buf)} < {CTXR_HEADER_SIZE}")
    if buf[0:4] != CTXR_MAGIC:
        raise CTXRError(f"bad magic {buf[0:4]!r}, expected {CTXR_MAGIC!r}")

    h = CTXRHeader()
    h.version          = struct.unpack_from(">I", buf, 0x04)[0]
    h.width            = struct.unpack_from(">H", buf, 0x08)[0]
    h.height           = struct.unpack_from(">H", buf, 0x0A)[0]
    h.depth            = struct.unpack_from(">H", buf, 0x0C)[0]
    h.format           = struct.unpack_from(">I", buf, 0x0E)[0]
    h.has_alpha        = bool(buf[0x12])
    h.additional_flags = struct.unpack_from(">I", buf, 0x13)[0]
    h.min_rgba         = struct.unpack_from(">I", buf, 0x17)[0]
    h.max_rgba         = struct.unpack_from(">I", buf, 0x1B)[0]
    h.filter_hint      = struct.unpack_from(">b", buf, 0x1F)[0]
    h.alpha_ref_value  = buf[0x20]
    h.max_lod_offset   = struct.unpack_from(">b", buf, 0x21)[0]
    h.type             = struct.unpack_from(">I", buf, 0x22)[0]
    h.num_levels       = buf[0x26]
    return h


def read_ctxr(path: str) -> CTXRTexture:
    with open(path, "rb") as fh:
        data = fh.read()

    if len(data) < CTXR_HEADER_SIZE:
        raise CTXRError(f"{path}: file shorter than header ({len(data)} bytes)")

    header = parse_header(data)
    tex = CTXRTexture(header=header)

    pos = CTXR_HEADER_SIZE
    for i in range(header.num_levels):
        if pos + 4 > len(data):
            raise CTXRError(
                f"{path}: mip {i} size field truncated at 0x{pos:X}"
            )
        size = struct.unpack_from(">I", data, pos)[0]
        pos += 4
        if pos + size > len(data):
            raise CTXRError(
                f"{path}: mip {i} payload truncated "
                f"(size={size}, remaining={len(data) - pos})"
            )
        tex.mips.append(data[pos:pos + size])
        pos += size
        # AlignTo32 after each mip
        pos += align_pad(pos)

    if pos != len(data):
        logger.debug(
            "%s: %d trailing bytes after mip stream (file=0x%X, walked=0x%X)",
            os.path.basename(path), len(data) - pos, len(data), pos,
        )
    return tex


# ---------------------------------------------------------------------------

def parse_mipmap_info(
    file_obj: BinaryIO,
    mipmap_count: int,
    width: int,
    height: int,
    is_compressed: bool = False,
    compression_format: str = "UNCOMPRESSED",
) -> Tuple[List[dict], bytes]:
 
    del is_compressed, compression_format, width, height

    mipmap_info: List[dict] = []

    # Mip 0 was just read up to the end of its payload. Skip its AlignTo32 pad.
    prev_pad = file_obj.read(align_pad(file_obj.tell()))

    for i in range(1, mipmap_count):
        size_bytes = file_obj.read(4)
        if len(size_bytes) < 4:
            raise CTXRError(f"mip {i}: truncated size field")
        size = struct.unpack(">I", size_bytes)[0]
        data = file_obj.read(size)
        if len(data) < size:
            raise CTXRError(
                f"mip {i}: truncated payload ({len(data)}/{size} bytes)"
            )
        mipmap_info.append({
            "padding": prev_pad,
            "size": size,
            "data": data,
        })
        prev_pad = file_obj.read(align_pad(file_obj.tell()))

    return mipmap_info, prev_pad


# ---------------------------------------------------------------------------

def serialize_header(h: CTXRHeader) -> bytes:
    """Build the 128-byte header. Field positions match WriteTextureWin32 1:1."""
    buf = bytearray(CTXR_HEADER_SIZE)
    buf[0:4] = CTXR_MAGIC
    struct.pack_into(">I", buf, 0x04, h.version)
    struct.pack_into(">H", buf, 0x08, h.width & 0xFFFF)
    struct.pack_into(">H", buf, 0x0A, h.height & 0xFFFF)
    struct.pack_into(">H", buf, 0x0C, h.depth & 0xFFFF)
    struct.pack_into(">I", buf, 0x0E, h.format & 0xFFFFFFFF)
    buf[0x12] = 1 if h.has_alpha else 0
    struct.pack_into(">I", buf, 0x13, h.additional_flags & 0xFFFFFFFF)
    struct.pack_into(">I", buf, 0x17, h.min_rgba & 0xFFFFFFFF)
    struct.pack_into(">I", buf, 0x1B, h.max_rgba & 0xFFFFFFFF)
    struct.pack_into(">b", buf, 0x1F, max(-128, min(127, h.filter_hint)))
    buf[0x20] = h.alpha_ref_value & 0xFF
    struct.pack_into(">b", buf, 0x21, max(-128, min(127, h.max_lod_offset)))
    struct.pack_into(">I", buf, 0x22, h.type & 0xFFFFFFFF)
    buf[0x26] = h.num_levels & 0xFF
    return bytes(buf)


def write_ctxr(path: str, tex: CTXRTexture) -> None:
    if tex.header.num_levels != len(tex.mips):
        raise CTXRError(
            f"num_levels={tex.header.num_levels} disagrees with mips list "
            f"length={len(tex.mips)}"
        )

    with open(path, "wb") as fh:
        fh.write(serialize_header(tex.header))
        for mip in tex.mips:
            fh.write(struct.pack(">I", len(mip)))
            fh.write(mip)
            pad = align_pad(4 + len(mip))
            if pad:
                fh.write(b"\x00" * pad)


# ---------------------------------------------------------------------------
# Min/max RGBA + has-alpha computation (CalcMinMaxRGBA / HasAlpha in source)
# ---------------------------------------------------------------------------


def calc_min_max_rgba(rgba_pixels_iter) -> Tuple[int, int, bool]:
    threshold = 128 if HAS_ALPHA_USE_128_THRESHOLD else 255
    min_r = min_g = min_b = min_a = 255
    max_r = max_g = max_b = max_a = 0
    has_low_alpha = False  # any pixel with alpha < threshold anywhere

    for buf in rgba_pixels_iter:
        try:
            import numpy as np
            arr = np.frombuffer(buf, dtype=np.uint8)
            if arr.size == 0 or arr.size % 4:
                continue
            arr = arr.reshape(-1, 4)
            r, g, b, a = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
            min_r = min(min_r, int(r.min()))
            min_g = min(min_g, int(g.min()))
            min_b = min(min_b, int(b.min()))
            min_a = min(min_a, int(a.min()))
            max_r = max(max_r, int(r.max()))
            max_g = max(max_g, int(g.max()))
            max_b = max(max_b, int(b.max()))
            max_a = max(max_a, int(a.max()))
            if not has_low_alpha and bool((a < threshold).any()):
                has_low_alpha = True
        except ImportError:  # pragma: no cover
            for i in range(0, len(buf), 4):
                r, g, b, a = buf[i], buf[i+1], buf[i+2], buf[i+3]
                if r < min_r: min_r = r
                if g < min_g: min_g = g
                if b < min_b: min_b = b
                if a < min_a: min_a = a
                if r > max_r: max_r = r
                if g > max_g: max_g = g
                if b > max_b: max_b = b
                if a > max_a: max_a = a
                if a < threshold: has_low_alpha = True

    min_rgba = (min_r << 24) | (min_g << 16) | (min_b << 8) | min_a
    max_rgba = (max_r << 24) | (max_g << 16) | (max_b << 8) | max_a
    return min_rgba, max_rgba, has_low_alpha


# ---------------------------------------------------------------------------
# No-mip regex
# ---------------------------------------------------------------------------
# BP's cooker had per-texture xml based metadata which decided if mips were generated or not
# for the file. Vanilla: all UI files were no-mips, however it should've also applied to atlas textures & specular maps.
#
# Instead of having a billion loose files, all of these files are matched via the patterns in no_mip_regex.txt.

class NoMipPolicy:
    def __init__(self, patterns):
        self.patterns: list[tuple[str, "re.Pattern[str]"]] = []
        import re
        for raw in patterns:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            try:
                self.patterns.append((line, re.compile(line, re.IGNORECASE)))
            except re.error as e:
                logger.warning("ignoring invalid no-mip regex %r: %s", line, e)

    @classmethod
    def from_file(cls, path: str) -> "NoMipPolicy":
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            logger.info("no_mip_regex file not found at %s; all textures mip", path)
            return cls([])
        except OSError as e:
            logger.warning("could not read %s: %s", path, e)
            return cls([])
        return cls(lines)

    @classmethod
    def empty(cls) -> "NoMipPolicy":
        return cls([])

    def __bool__(self) -> bool:
        return bool(self.patterns)

    def __len__(self) -> int:
        return len(self.patterns)

    def stem_for(self, filename: str) -> str:
        s = filename.replace("\\", "/")
        base = s.rsplit("/", 1)[-1]
        if base.lower().endswith(".ctxr"):
            base = base[:-5]
        return base

    def should_skip_mips(self, filename: str) -> bool:
        stem = self.stem_for(filename)
        for _raw, pat in self.patterns:
            if pat.search(stem):
                return True
        return False

    def matching_rule(self, filename: str) -> Optional[str]:
        stem = self.stem_for(filename)
        for raw, pat in self.patterns:
            if pat.search(stem):
                return raw
        return None

class MustBeDxt5Policy:
    def __init__(self, names):
        self.names: set[str] = set()
        for raw in names:
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("//"):
                continue
            self.names.add(self._norm(line))

    _CONTAINER_EXTS = (".ctxr", ".dds", ".png", ".tga")

    @classmethod
    def _norm(cls, name: str) -> str:
        #normalize name to lowercase, and strip extension
        s = name.replace("\\", "/")
        base = s.rsplit("/", 1)[-1].lower()
        for ext in cls._CONTAINER_EXTS:
            if base.endswith(ext):
                return base[: -len(ext)]
        return base

    @classmethod
    def from_file(cls, path: str) -> "MustBeDxt5Policy":
        """Load the list from a file. Missing/empty -> empty policy (nothing
        is required to be DXT5)."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            logger.info("must-be-dxt5 file not found at %s; no DXT5 requirements", path)
            return cls([])
        except OSError as e:
            logger.warning("could not read %s: %s", path, e)
            return cls([])
        return cls(lines)

    @classmethod
    def empty(cls) -> "MustBeDxt5Policy":
        return cls([])

    def __bool__(self) -> bool:
        return bool(self.names)

    def __len__(self) -> int:
        return len(self.names)

    def requires_dxt5(self, output_filename: str) -> bool:
        return self._norm(output_filename) in self.names
