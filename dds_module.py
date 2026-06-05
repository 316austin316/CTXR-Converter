from __future__ import annotations

import logging
import os
import struct
from typing import Optional

from PIL import Image

from ctxr_utils import (
    CTXRError,
    CTXRHeader,
    CTXRTexture,
    FORMAT_A8R8G8B8,
    FORMAT_DXT1,
    FORMAT_DXT3,
    FORMAT_DXT5,
    FORMAT_NAMES,
    calc_min_max_rgba,
    num_mip_maps,
    payload_size,
    read_ctxr,
    write_ctxr,
)

logger = logging.getLogger(__name__)


class DDSError(Exception):
    """Raised for any malformed or unsupported DDS data."""


# ---------------------------------------------------------------------------
# DDS header (Microsoft DDSURFACEDESC2)
# ---------------------------------------------------------------------------

DDS_MAGIC = b"DDS "

# DDSD flags
DDSD_CAPS        = 0x00000001
DDSD_HEIGHT      = 0x00000002
DDSD_WIDTH       = 0x00000004
DDSD_PITCH       = 0x00000008
DDSD_PIXELFORMAT = 0x00001000
DDSD_MIPMAPCOUNT = 0x00020000
DDSD_LINEARSIZE  = 0x00080000
DDSD_DEPTH       = 0x00800000

# DDPF flags
DDPF_ALPHAPIXELS = 0x00000001
DDPF_FOURCC      = 0x00000004
DDPF_RGB         = 0x00000040

# DDSCAPS
DDSCAPS_COMPLEX = 0x00000008
DDSCAPS_TEXTURE = 0x00001000
DDSCAPS_MIPMAP  = 0x00400000


def _ctxr_format_to_dds_fourcc(fmt: int) -> Optional[bytes]:
    return {FORMAT_DXT1: b"DXT1", FORMAT_DXT3: b"DXT3", FORMAT_DXT5: b"DXT5"}.get(fmt)


def _dds_fourcc_to_ctxr_format(fourcc: bytes) -> Optional[int]:
    return {b"DXT1": FORMAT_DXT1, b"DXT3": FORMAT_DXT3, b"DXT5": FORMAT_DXT5}.get(fourcc)


def is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def next_power_of_two(n: int) -> int:
    if n <= 1:
        return 1
    return 1 << ((n - 1).bit_length())


def calculate_mipmap_sizes(width, height, mipmap_count):
    out = []
    for i in range(mipmap_count):
        out.append((max(1, width >> i), max(1, height >> i)))
    return out


def create_dds_header(width: int, height: int, mipmap_count: int,
                     format_type: str = "DXT1") -> bytearray:
    header = bytearray(128)
    header[0:4] = DDS_MAGIC
    struct.pack_into("<I", header, 4, 124)  # dwSize

    is_compressed = format_type in ("DXT1", "DXT3", "DXT5")

    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT
    flags |= DDSD_LINEARSIZE if is_compressed else DDSD_PITCH
    if mipmap_count > 1:
        flags |= DDSD_MIPMAPCOUNT
    struct.pack_into("<I", header, 8, flags)

    struct.pack_into("<I", header, 12, height)
    struct.pack_into("<I", header, 16, width)

    # pitch / linear size
    if format_type == "DXT1":
        pitch = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 8
    elif format_type in ("DXT3", "DXT5"):
        pitch = max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
    else:
        pitch = width * 4  # bytes per scanline for 32bpp
    struct.pack_into("<I", header, 20, pitch)

    struct.pack_into("<I", header, 24, 0)  # depth
    struct.pack_into("<I", header, 28, max(1, mipmap_count))

    # ddpfPixelFormat starts at 76 (after 44 bytes of reserved)
    struct.pack_into("<I", header, 76, 32)  # dwSize of pixel format
    if is_compressed:
        struct.pack_into("<I", header, 80, DDPF_FOURCC)
        header[84:88] = format_type.encode("ascii")
    else:
        struct.pack_into("<I", header, 80, DDPF_RGB | DDPF_ALPHAPIXELS)
        struct.pack_into("<I", header, 84, 0)  # fourCC
        struct.pack_into("<I", header, 88, 32)  # bit count
        # BGRA byte order on disk -> R mask 0x00FF0000, G 0x0000FF00,
        # B 0x000000FF, A 0xFF000000
        struct.pack_into("<I", header, 92,  0x00FF0000)  # R mask
        struct.pack_into("<I", header, 96,  0x0000FF00)  # G mask
        struct.pack_into("<I", header, 100, 0x000000FF)  # B mask
        struct.pack_into("<I", header, 104, 0xFF000000)  # A mask

    caps = DDSCAPS_TEXTURE
    if mipmap_count > 1:
        caps |= DDSCAPS_COMPLEX | DDSCAPS_MIPMAP
    struct.pack_into("<I", header, 108, caps)
    return header


def parse_dds_header(buf: bytes):
    if buf[0:4] != DDS_MAGIC:
        raise DDSError("not a DDS file (bad magic)")
    if struct.unpack_from("<I", buf, 4)[0] != 124:
        raise DDSError("DDS header size != 124")
    height = struct.unpack_from("<I", buf, 12)[0]
    width  = struct.unpack_from("<I", buf, 16)[0]
    mipmap = max(1, struct.unpack_from("<I", buf, 28)[0])
    pf_flags = struct.unpack_from("<I", buf, 80)[0]
    fourcc = bytes(buf[84:88])
    is_compressed = bool(pf_flags & DDPF_FOURCC) and fourcc in (b"DXT1", b"DXT3", b"DXT5")
    return width, height, mipmap, fourcc, is_compressed


# ---------------------------------------------------------------------------

def ctxr_to_dds(ctxr_file_path: str, dds_file_path: str,
                ctxr_header_unused=None) -> bool:
    tex = read_ctxr(ctxr_file_path)
    h = tex.header

    fourcc = _ctxr_format_to_dds_fourcc(h.format)
    if fourcc is not None:
        format_type = fourcc.decode("ascii")
    elif h.format == FORMAT_A8R8G8B8:
        format_type = "RGBA"
    else:
        raise DDSError(
            f"unsupported CTXR format {FORMAT_NAMES.get(h.format, h.format)} "
            f"for DDS conversion"
        )

    mipmap_count = h.num_levels
    logger.info(
        "CTXR -> DDS: %dx%d %s, %d mips",
        h.width, h.height, format_type, mipmap_count,
    )

    dds_header = create_dds_header(h.width, h.height, mipmap_count, format_type)

    with open(dds_file_path, "wb") as f:
        f.write(dds_header)
        for level, mip in enumerate(tex.mips):
            mw, mh = max(1, h.width >> level), max(1, h.height >> level)
            expected = payload_size(mw, mh, h.format)
            data = mip
            if len(data) > expected:
                data = data[:expected]
            elif len(data) < expected:
                data = data + b"\x00" * (expected - len(data))
            f.write(data)
    return True


# ---------------------------------------------------------------------------
# DDS -> CTXR
# ---------------------------------------------------------------------------

def dds_to_ctxr(dds_file_path: str, ctxr_file_path: str,
                ctxr_header_template: bytes,
                original_ctxr_path: Optional[str] = None) -> bool:
    from ctxr_utils import parse_header

    template = parse_header(bytes(ctxr_header_template))

    with open(dds_file_path, "rb") as f:
        dds_data = f.read()

    if len(dds_data) < 128:
        raise DDSError("DDS file too short")

    width, height, mipmap_count, fourcc, is_compressed = parse_dds_header(dds_data)
    logger.info(
        "DDS -> CTXR: %dx%d, %d mips, fourcc=%r, compressed=%s",
        width, height, mipmap_count, fourcc, is_compressed,
    )

    if is_compressed:
        new_format = _dds_fourcc_to_ctxr_format(fourcc)
        if new_format is None:
            raise DDSError(f"unsupported DXT FourCC {fourcc!r}")
    else:
        new_format = FORMAT_A8R8G8B8

    mips: list[bytes] = []
    pos = 128
    rgba_for_stats: list[bytes] = []  # only populated for uncompressed
    for level in range(mipmap_count):
        mw, mh = max(1, width >> level), max(1, height >> level)
        mip_size = payload_size(mw, mh, new_format)
        chunk = dds_data[pos:pos + mip_size]
        if len(chunk) < mip_size:
            # truncated DDS — pad
            chunk = chunk + b"\x00" * (mip_size - len(chunk))
        pos += mip_size
        mips.append(chunk)
        if not is_compressed:
            rgba_for_stats.append(_bgra_to_rgba(chunk))

    new_header = CTXRHeader(
        width=width,
        height=height,
        depth=template.depth or 1,
        format=new_format,
        has_alpha=template.has_alpha,
        additional_flags=template.additional_flags,
        min_rgba=template.min_rgba,
        max_rgba=template.max_rgba,
        filter_hint=template.filter_hint,
        alpha_ref_value=template.alpha_ref_value,
        max_lod_offset=template.max_lod_offset,
        type=template.type,
        num_levels=mipmap_count,
        version=template.version,
    )

    if rgba_for_stats:
        min_rgba, max_rgba, has_alpha = calc_min_max_rgba(rgba_for_stats)
        new_header.min_rgba = min_rgba
        new_header.max_rgba = max_rgba
        new_header.has_alpha = has_alpha

    write_ctxr(ctxr_file_path, CTXRTexture(header=new_header, mips=mips))
    logger.info("Wrote %s (%s, %d mips)", ctxr_file_path,
                FORMAT_NAMES.get(new_format, new_format), mipmap_count)
    return True


def _bgra_to_rgba(buf: bytes) -> bytes:
    try:
        import numpy as np
        a = np.frombuffer(buf, dtype=np.uint8)
        if a.size % 4:
            return buf 
        a = a.reshape(-1, 4).copy()
        a = a[:, [2, 1, 0, 3]]
        return a.tobytes()
    except ImportError: 
        out = bytearray(len(buf))
        for i in range(0, len(buf), 4):
            out[i+0] = buf[i+2]
            out[i+1] = buf[i+1]
            out[i+2] = buf[i+0]
            out[i+3] = buf[i+3]
        return bytes(out)


# ---------------------------------------------------------------------------

def batch_convert_ctxr_to_dds_enhanced(input_folder: str, output_folder: str):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    files = [f for f in os.listdir(input_folder) if f.lower().endswith(".ctxr")]
    success = 0
    errors: list[tuple[str, str]] = []

    for i, name in enumerate(files):
        try:
            in_p = os.path.join(input_folder, name)
            out_p = os.path.join(output_folder, name[:-5] + ".dds")
            ctxr_to_dds(in_p, out_p)
            success += 1
            logger.info("CTXR->DDS %d/%d: %s", i + 1, len(files), name)
        except Exception as e:
            logger.exception("CTXR->DDS failed: %s", name)
            errors.append((name, str(e)))
    return success, errors


def batch_convert_dds_to_ctxr_enhanced(input_folder: str, output_folder: str,
                                        template_folder: str):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    files = [f for f in os.listdir(input_folder) if f.lower().endswith(".dds")]
    success = 0
    errors: list[tuple[str, str]] = []

    for i, name in enumerate(files):
        try:
            in_p = os.path.join(input_folder, name)
            template_p = os.path.join(template_folder, name[:-4] + ".ctxr")
            out_p = os.path.join(output_folder, name[:-4] + ".ctxr")
            if not os.path.exists(template_p):
                logger.warning("no template for %s, skipping", name)
                continue
            with open(template_p, "rb") as f:
                template_header = f.read(128)
            dds_to_ctxr(in_p, out_p, template_header, original_ctxr_path=template_p)
            success += 1
            logger.info("DDS->CTXR %d/%d: %s", i + 1, len(files), name)
        except Exception as e:
            logger.exception("DDS->CTXR failed: %s", name)
            errors.append((name, str(e)))
    return success, errors
