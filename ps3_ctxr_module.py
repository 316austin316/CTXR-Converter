"""
ps3 header, big-endian
    Offset  Size  Field
    ------  ----  ---------------------------------------------------------
    0x00    4     Version          = 0x02000101  (GTF version/magic)
    0x04    4     Size             = file length - 128 (header)
    0x08    4     NumTexture       = 1
    0x0C    4     Id               = 0
    0x10    4     OffsetToTex      = 128
    0x14    4     TextureSize      = full mip-chain byte count
    0x18    4     mMinRGBA         
    0x1C    4     mMaxRGBA         
    0x20    4     mAdditionalFlags 
    0x24   24     CellGcmTexture:
            0x24  1   format       0x85 A8R8G8B8, 0x88 DXT5, |0x20 = LINEAR
            0x25  1   mipmap levels
            0x26  1   dimension
            0x27  1   cubemap
            0x28  4   remap
            0x2C  2   width
            0x2E  2   height
            0x30  2   depth
            0x32  1   location
            0x33  1   _pad
            0x34  4   pitch        (>0 for linear, 0 for swizzled)
            0x38  4   offset
    0x3C    1     mFilterHint      (int8, -1 = default)
    0x3D    1     mAlphaRefValue   (uint8)
    0x3E    1     mMaxLODOffset    (int8)
    0x3F..        zero pad to 0x80
    [0x80]        texture data (TextureSize bytes) + 64-byte trailing pad

Swizzle:

* Morton swizzle is flagged on/off in CellGcmTexture -> format. 0x20 = linear. POT textures are swizzled, NPOTs/UI are not.
* Each mip level is swizzled independently using its own dimensions.

"""

from __future__ import annotations

import logging
import os
import struct
from datetime import datetime
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# tkinter is imported lazily so headless / CLI use works without a display.
try:
    from tkinter import filedialog, messagebox
    _HAS_TK = True
except Exception:  # pragma: no cover
    filedialog = None
    messagebox = None
    _HAS_TK = False

from dds_module import create_dds_header, parse_dds_header, DDSError


# ---------------------------------------------------------------------------

PS3_MAGIC = b"\x02\x00\x01\x01"   # GTF Version 0x02000101
PS3_HEADER_SIZE = 128
PS3_TAIL_PAD = 64                  # trailing zero pad after texture data

GCM_OFFSET = 0x24                  # CellGcmTexture start

# GCM texture format bytes (base, before the _LN linear flag)
GCM_FMT_LINEAR_FLAG = 0x20
GCM_A8R8G8B8 = 0x85
GCM_DXT1     = 0x86
GCM_DXT3     = 0x87
GCM_DXT5     = 0x88

_GCM_TO_DDS = {
    GCM_A8R8G8B8: "RGBA",
    GCM_DXT1: "DXT1",
    GCM_DXT3: "DXT3",
    GCM_DXT5: "DXT5",
}
_DDS_FOURCC_TO_GCM = {
    b"DXT1": GCM_DXT1,
    b"DXT3": GCM_DXT3,
    b"DXT5": GCM_DXT5,
}


class PS3CTXRError(Exception):
    """Raised for malformed or unsupported PS3 CTXR/GTF data."""


# ---------------------------------------------------------------------------

class PS3Header:
    __slots__ = (
        "version", "size", "num_texture", "tex_id", "offset_to_tex",
        "texture_size", "min_rgba", "max_rgba", "additional_flags",
        "format", "mipmap", "dimension", "cubemap", "remap",
        "width", "height", "depth", "location", "pitch", "gcm_offset",
        "filter_hint", "alpha_ref_value", "max_lod_offset",
    )

    @property
    def base_format(self) -> int:
        return self.format & ~GCM_FMT_LINEAR_FLAG

    @property
    def is_linear(self) -> bool:
        return bool(self.format & GCM_FMT_LINEAR_FLAG)

    @property
    def is_dxt(self) -> bool:
        return self.base_format in (GCM_DXT1, GCM_DXT3, GCM_DXT5)

    @property
    def dds_format(self) -> str:
        f = _GCM_TO_DDS.get(self.base_format)
        if f is None:
            raise PS3CTXRError(f"unsupported GCM format 0x{self.format:02X}")
        return f


def parse_ps3_header(buf: bytes) -> PS3Header:
    if len(buf) < PS3_HEADER_SIZE:
        raise PS3CTXRError(f"header too short: {len(buf)}")
    if buf[0:4] != PS3_MAGIC:
        raise PS3CTXRError(f"bad magic {buf[0:4]!r}, expected {PS3_MAGIC!r}")

    h = PS3Header()
    h.version          = struct.unpack_from(">I", buf, 0x00)[0]
    h.size             = struct.unpack_from(">I", buf, 0x04)[0]
    h.num_texture      = struct.unpack_from(">I", buf, 0x08)[0]
    h.tex_id           = struct.unpack_from(">I", buf, 0x0C)[0]
    h.offset_to_tex    = struct.unpack_from(">I", buf, 0x10)[0]
    h.texture_size     = struct.unpack_from(">I", buf, 0x14)[0]
    h.min_rgba         = struct.unpack_from(">I", buf, 0x18)[0]
    h.max_rgba         = struct.unpack_from(">I", buf, 0x1C)[0]
    h.additional_flags = struct.unpack_from(">I", buf, 0x20)[0]

    g = GCM_OFFSET
    h.format     = buf[g + 0x00]
    h.mipmap     = buf[g + 0x01]
    h.dimension  = buf[g + 0x02]
    h.cubemap    = buf[g + 0x03]
    h.remap      = struct.unpack_from(">I", buf, g + 0x04)[0]
    h.width      = struct.unpack_from(">H", buf, g + 0x08)[0]
    h.height     = struct.unpack_from(">H", buf, g + 0x0A)[0]
    h.depth      = struct.unpack_from(">H", buf, g + 0x0C)[0]
    h.location   = buf[g + 0x0E]
    h.pitch      = struct.unpack_from(">I", buf, g + 0x10)[0]
    h.gcm_offset = struct.unpack_from(">I", buf, g + 0x14)[0]

    h.filter_hint     = struct.unpack_from(">b", buf, 0x3C)[0]
    h.alpha_ref_value = buf[0x3D]
    h.max_lod_offset  = struct.unpack_from(">b", buf, 0x3E)[0]
    return h


# ---------------------------------------------------------------------------

def _mip_byte_size(width: int, height: int, base_format: int) -> int:
    if base_format == GCM_A8R8G8B8:
        return width * height * 4
    if base_format == GCM_DXT1:
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 8
    if base_format in (GCM_DXT3, GCM_DXT5):
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * 16
    raise PS3CTXRError(f"unsupported format for size: 0x{base_format:02X}")


def _num_mip_maps(width: int, height: int) -> int:
    size = max(width, height)
    if size <= 1:
        return 1
    return 1 + (size.bit_length() - 1)


# ---------------------------------------------------------------------------
# Swizzle (RSX Morton / Z-order)
# ---------------------------------------------------------------------------

def _morton_unswizzle_indices(width: int, height: int) -> np.ndarray:
    if width & (width - 1) or height & (height - 1):
        raise PS3CTXRError(
            f"cannot swizzle non-power-of-two {width}x{height}"
        )
    lw = width.bit_length() - 1
    lh = height.bit_length() - 1
    common = min(lw, lh)

    ys, xs = np.meshgrid(
        np.arange(height, dtype=np.uint64),
        np.arange(width, dtype=np.uint64),
        indexing="ij",
    )
    z = np.zeros((height, width), dtype=np.uint64)
    bit = 0
    for i in range(common):
        z |= ((xs >> np.uint64(i)) & np.uint64(1)) << np.uint64(bit); bit += 1
        z |= ((ys >> np.uint64(i)) & np.uint64(1)) << np.uint64(bit); bit += 1
    if lw > lh:
        z |= (xs >> np.uint64(common)) << np.uint64(bit)
    elif lh > lw:
        z |= (ys >> np.uint64(common)) << np.uint64(bit)
    # z[y, x] = swizzled source index for destination (x, y).
    # Flattened in row-major (dst) order, this is exactly src[dst].
    return z.reshape(-1).astype(np.int64)


def _unswizzle_surface(data: np.ndarray, width: int, height: int,
                       element_size: int) -> np.ndarray:
    """Unswizzle one surface.

    ``data`` is a flat uint8 array of ``width*height*element_size`` bytes in
    swizzled order. ``element_size`` is 4 for A8R8G8B8 (per pixel) or the DXT
    block size (8/16) with ``width``/``height`` given as the **block grid**
    dimensions. Returns the linear (unswizzled) surface, flat uint8.
    """
    src = _morton_unswizzle_indices(width, height)  # src index per dst slot
    elems = data.reshape(-1, element_size)
    out = elems[src]
    return out.reshape(-1)


def _swizzle_surface(data: np.ndarray, width: int, height: int,
                     element_size: int) -> np.ndarray:
    """Inverse of :func:`_unswizzle_surface` — linear -> swizzled."""
    src = _morton_unswizzle_indices(width, height)  # src[dst]
    # Invert: dst[src] tells where each linear element goes.
    inv = np.empty_like(src)
    inv[src] = np.arange(src.size, dtype=np.int64)
    elems = data.reshape(-1, element_size)
    out = elems[inv]
    return out.reshape(-1)


# ---------------------------------------------------------------------------

def _read_ps3(file_path: str) -> Tuple[PS3Header, list]:
    with open(file_path, "rb") as f:
        data = f.read()
    h = parse_ps3_header(data)
    base = h.base_format

    pos = h.offset_to_tex
    mips = []
    for level in range(max(1, h.mipmap)):
        mw = max(1, h.width >> level)
        mh = max(1, h.height >> level)
        msize = _mip_byte_size(mw, mh, base)
        chunk = data[pos:pos + msize]
        if len(chunk) < msize:
            raise PS3CTXRError(
                f"{os.path.basename(file_path)}: mip {level} truncated "
                f"({len(chunk)}/{msize})"
            )
        pos += msize
        arr = np.frombuffer(chunk, dtype=np.uint8)

        if h.is_linear:
            linear = arr
        elif base == GCM_A8R8G8B8:
            linear = _unswizzle_surface(arr, mw, mh, 4)
        else:  # DXT: swizzle over block grid
            block = 8 if base == GCM_DXT1 else 16
            bw = max(1, (mw + 3) // 4)
            bh = max(1, (mh + 3) // 4)
            if bw & (bw - 1) or bh & (bh - 1):
                # Non-POT block grid can't be Morton-swizzled; treat linear.
                linear = arr
            else:
                linear = _unswizzle_surface(arr, bw, bh, block)

        if base == GCM_A8R8G8B8:
            # GTF stores ARGB8 as RGBA byte order on disk; DDS wants BGRA.
            px = linear.reshape(-1, 4)
            # RGBA -> BGRA: swap channel 0 and 2
            linear = px[:, [2, 1, 0, 3]].reshape(-1)
        mips.append(linear.tobytes())

    return h, mips


# ---------------------------------------------------------------------------

def convert_ps3_ctxr_to_dds(file_path: Optional[str] = None,
                            output_path: Optional[str] = None) -> Optional[str]:
    if file_path is None:
        if not _HAS_TK:
            raise PS3CTXRError("no file_path given and tkinter unavailable")
        file_path = filedialog.askopenfilename(
            title="Select PS3 CTXR File",
            filetypes=[("CTXR Files", "*.ctxr")],
        )
        if not file_path:
            return None

    if output_path is None:
        output_path = os.path.splitext(file_path)[0] + ".dds"

    h, mips = _read_ps3(file_path)
    fmt = h.dds_format
    mip_count = max(1, h.mipmap)

    header = create_dds_header(h.width, h.height, mip_count, fmt)
    with open(output_path, "wb") as f:
        f.write(header)
        for m in mips:
            f.write(m)

    logger.info(
        "PS3->DDS %s: %dx%d %s %s %d mips -> %s",
        os.path.basename(file_path), h.width, h.height, fmt,
        "linear" if h.is_linear else "swizzled", mip_count,
        os.path.basename(output_path),
    )
    return output_path


# ---------------------------------------------------------------------------

def convert_dds_to_ps3_ctxr(dds_path: str,
                            output_path: Optional[str] = None,
                            template_ctxr: Optional[str] = None) -> str:
    if output_path is None:
        output_path = os.path.splitext(dds_path)[0] + ".ctxr"

    with open(dds_path, "rb") as f:
        dds = f.read()
    width, height, mip_count, fourcc, is_compressed = parse_dds_header(dds)

    if is_compressed:
        base = _DDS_FOURCC_TO_GCM.get(fourcc)
        if base is None:
            raise PS3CTXRError(f"unsupported DXT fourcc {fourcc!r}")
    else:
        base = GCM_A8R8G8B8

    def _pot(n): return n > 0 and not (n & (n - 1))
    swizzle = _pot(width) and _pot(height)

    # Inherit metadata from a template if provided.
    tpl: Optional[PS3Header] = None
    if template_ctxr and os.path.exists(template_ctxr):
        with open(template_ctxr, "rb") as f:
            tpl = parse_ps3_header(f.read(PS3_HEADER_SIZE))

    min_rgba   = tpl.min_rgba if tpl else 0x00000000
    max_rgba   = tpl.max_rgba if tpl else 0xFFFFFFFF
    add_flags  = tpl.additional_flags if tpl else 0
    filt_hint  = tpl.filter_hint if tpl else -1
    alpha_ref  = tpl.alpha_ref_value if tpl else 255
    max_lod    = tpl.max_lod_offset if tpl else 0
    remap      = tpl.remap if tpl else 0x0000AAE4 
    
    # Slice DDS mips
    pos = 128
    out_surfaces = []
    for level in range(mip_count):
        mw = max(1, width >> level)
        mh = max(1, height >> level)
        msize = _mip_byte_size(mw, mh, base)
        chunk = dds[pos:pos + msize]
        if len(chunk) < msize:
            chunk = chunk + b"\x00" * (msize - len(chunk))
        pos += msize
        arr = np.frombuffer(chunk, dtype=np.uint8)

        if base == GCM_A8R8G8B8:
            # DDS BGRA on disk -> GTF wants RGBA byte order.
            px = arr.reshape(-1, 4)
            arr = px[:, [2, 1, 0, 3]].reshape(-1)

        if swizzle:
            if base == GCM_A8R8G8B8:
                arr = _swizzle_surface(arr, mw, mh, 4)
            else:
                block = 8 if base == GCM_DXT1 else 16
                bw, bh = max(1, (mw + 3) // 4), max(1, (mh + 3) // 4)
                if not (bw & (bw - 1)) and not (bh & (bh - 1)):
                    arr = _swizzle_surface(arr, bw, bh, block)
        out_surfaces.append(arr.tobytes())

    tex_data = b"".join(out_surfaces)
    texture_size = len(tex_data)

    total_len = ((PS3_HEADER_SIZE + texture_size + 127) // 128) * 128
    tail_pad = total_len - PS3_HEADER_SIZE - texture_size

    # GCM format byte: set linear flag when not swizzling.
    gcm_format = base | (0 if swizzle else GCM_FMT_LINEAR_FLAG)
    if not swizzle:
        if base == GCM_A8R8G8B8:
            pitch = width * 4
        else:
            block = 8 if base == GCM_DXT1 else 16
            pitch = max(1, (width + 3) // 4) * block
    else:
        pitch = 0

    header = bytearray(PS3_HEADER_SIZE)
    struct.pack_into(">I", header, 0x00, 0x02000101)
    # Size (0x04) = file length minus the 128-byte header.
    struct.pack_into(">I", header, 0x04, total_len - PS3_HEADER_SIZE)
    struct.pack_into(">I", header, 0x08, 1)
    struct.pack_into(">I", header, 0x0C, 0)
    struct.pack_into(">I", header, 0x10, PS3_HEADER_SIZE)
    struct.pack_into(">I", header, 0x14, texture_size)
    struct.pack_into(">I", header, 0x18, min_rgba & 0xFFFFFFFF)
    struct.pack_into(">I", header, 0x1C, max_rgba & 0xFFFFFFFF)
    struct.pack_into(">I", header, 0x20, add_flags & 0xFFFFFFFF)

    g = GCM_OFFSET
    header[g + 0x00] = gcm_format & 0xFF
    header[g + 0x01] = mip_count & 0xFF
    header[g + 0x02] = 2          # dimension (2D)
    header[g + 0x03] = 0          # cubemap
    struct.pack_into(">I", header, g + 0x04, remap & 0xFFFFFFFF)
    struct.pack_into(">H", header, g + 0x08, width & 0xFFFF)
    struct.pack_into(">H", header, g + 0x0A, height & 0xFFFF)
    struct.pack_into(">H", header, g + 0x0C, 1)   # depth
    header[g + 0x0E] = 0          # location
    header[g + 0x0F] = 0          # pad
    struct.pack_into(">I", header, g + 0x10, pitch & 0xFFFFFFFF)
    struct.pack_into(">I", header, g + 0x14, 0)   # gcm offset

    struct.pack_into(">b", header, 0x3C, max(-128, min(127, filt_hint)))
    header[0x3D] = alpha_ref & 0xFF
    struct.pack_into(">b", header, 0x3E, max(-128, min(127, max_lod)))

    with open(output_path, "wb") as f:
        f.write(header)
        f.write(tex_data)
        f.write(b"\x00" * tail_pad)

    logger.info(
        "DDS->PS3 %s: %dx%d %s %s %d mips -> %s",
        os.path.basename(dds_path), width, height, fourcc if is_compressed else "RGBA",
        "swizzled" if swizzle else "linear", mip_count,
        os.path.basename(output_path),
    )
    return output_path


# ---------------------------------------------------------------------------

def batch_convert_ps3_ctxr_to_dds():
    directory_path = filedialog.askdirectory(title="Select Folder with PS3 CTXR Files")
    if not directory_path:
        return

    error_files = []
    converted = 0
    for file_name in os.listdir(directory_path):
        if file_name.lower().endswith(".ctxr"):
            file_path = os.path.join(directory_path, file_name)
            try:
                convert_ps3_ctxr_to_dds(file_path)
                converted += 1
            except Exception as e:
                logger.exception("PS3->DDS failed: %s", file_name)
                error_files.append(f"{file_name}: {e}")

    if error_files:
        log_path = os.path.join(
            directory_path,
            f"conversion_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        )
        with open(log_path, "w") as log_file:
            log_file.write("Conversion Errors:\n")
            log_file.write("\n".join(error_files))
        if _HAS_TK:
            messagebox.showwarning(
                "Conversion Errors",
                f"{len(error_files)} file(s) failed; converted {converted}. "
                f"See log:\n{log_path}",
            )
    elif _HAS_TK:
        messagebox.showinfo(
            "Batch Conversion Complete",
            f"All {converted} files converted successfully.",
        )
