import argparse
import logging
import os
import struct
import sys
import traceback
from typing import Optional
from PIL import Image

# lazy import tkinter and ImageTk with launch_gui(), they're not needed in cli mode.
tk = None
ttk = None
Button = Frame = Label = OptionMenu = StringVar = filedialog = messagebox = None
ImageTk = None


def _import_tk():
    global tk, ttk, Button, Frame, Label, OptionMenu, StringVar
    global filedialog, messagebox, ImageTk
    import tkinter as _tk
    from tkinter import ttk as _ttk
    from tkinter import (
        Button as _Button, Frame as _Frame, Label as _Label,
        OptionMenu as _OptionMenu, StringVar as _StringVar,
        filedialog as _filedialog, messagebox as _messagebox,
    )
    from PIL import ImageTk as _ImageTk
    tk, ttk = _tk, _ttk
    Button, Frame, Label = _Button, _Frame, _Label
    OptionMenu, StringVar = _OptionMenu, _StringVar
    filedialog, messagebox = _filedialog, _messagebox
    ImageTk = _ImageTk

from ctxr_utils import (
    CTXRError,
    CTXRHeader,
    CTXRTexture,
    FORMAT_A8R8G8B8,
    FORMAT_DXT1,
    FORMAT_DXT3,
    FORMAT_DXT5,
    FORMAT_NAMES,
    NoMipPolicy,
    MustBeDxt5Policy,
    calc_min_max_rgba,
    num_mip_maps,
    payload_size,
    read_ctxr,
    write_ctxr,
)
from dds_module import (
    create_dds_header,
    ctxr_to_dds,
    dds_to_ctxr,
)

# Optional module — only used by the PS3 tab if present.
try:
    import ps3_ctxr_module
    from ps3_ctxr_module import (
        convert_ps3_ctxr_to_dds,
        convert_dds_to_ps3_ctxr,
        batch_convert_ps3_ctxr_to_dds,
    )
    _HAS_PS3 = True
except Exception:
    _HAS_PS3 = False

# Optional viewer
try:
    from image_viewer import ImageViewer
    _HAS_VIEWER = True
except Exception:
    _HAS_VIEWER = False


# ---------------------------------------------------------------------------

NO_MIP_FILENAME = "no_mip_regex.txt"
MUST_BE_DXT5_FILENAME = "must_be_dxt5.txt"


def _app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_log_file_handler = logging.FileHandler(os.path.join(_app_dir(), "ctxr_converter.log"))
_log_file_handler.setLevel(logging.WARNING)   # don't spam the log with info, only wanrings.
_log_stream_handler = logging.StreamHandler()
_log_stream_handler.setLevel(logging.INFO)

logging.basicConfig(
    level=logging.INFO,                        # root passes INFO+ to handlers
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[_log_file_handler, _log_stream_handler],
)


# ---------------------------------------------------------------------------

def _no_mip_path() -> str:
    return os.path.join(_app_dir(), NO_MIP_FILENAME)


_no_mip_path_str = _no_mip_path()
_no_mip_policy: NoMipPolicy = NoMipPolicy.from_file(_no_mip_path_str)
_no_mip_file_present: bool = os.path.exists(_no_mip_path_str)
_no_mip_warning_shown: bool = False
logging.info(
    "Loaded %d no-mip pattern(s) from %s (file present: %s)",
    len(_no_mip_policy), _no_mip_path_str, _no_mip_file_present,
)


def _must_be_dxt5_path() -> str:
    return os.path.join(_app_dir(), MUST_BE_DXT5_FILENAME)


# Require precooked dds for DXT5 leaf textures.
_must_be_dxt5_policy: MustBeDxt5Policy = MustBeDxt5Policy.from_file(_must_be_dxt5_path())
logging.info(
    "Loaded %d must-be-dxt5 name(s) from %s",
    len(_must_be_dxt5_policy), _must_be_dxt5_path(),
)


CONFIG_FILENAME = "ctxr3.ini"
_VALID_CLI_OUT_FORMATS = ("dds", "png", "tga")


def _config_path() -> str:
    return os.path.join(_app_dir(), CONFIG_FILENAME)


def _load_cli_output_format() -> str:
    import configparser
    path = _config_path()
    if not os.path.exists(path):
        return "dds"
    try:
        cp = configparser.ConfigParser()
        cp.read(path)
        val = cp.get("cli", "output_format", fallback="dds").strip().lower()
        if val not in _VALID_CLI_OUT_FORMATS:
            logging.warning(
                "ctxr3.ini: invalid output_format %r (want one of %s); using dds",
                val, ", ".join(_VALID_CLI_OUT_FORMATS),
            )
            return "dds"
        return val
    except Exception as e:
        logging.warning("ctxr3.ini: could not read config (%s); using dds", e)
        return "dds"


_cli_output_format: str = _load_cli_output_format()
logging.info("CLI default ctxr->image output format: %s", _cli_output_format)


def reload_no_mip_policy():
    global _no_mip_policy, _no_mip_file_present, _no_mip_warning_shown
    path = _no_mip_path()
    _no_mip_policy = NoMipPolicy.from_file(path)
    _no_mip_file_present = os.path.exists(path)
    _no_mip_warning_shown = False  # let user re-warn after a reload
    msg = (f"Reloaded {len(_no_mip_policy)} no-mip rule(s) "
           f"from {os.path.basename(path)}")
    logging.info(msg)
    label.config(text=msg)


def _maybe_warn_missing_no_mip_rules():
    global _no_mip_warning_shown
    if _no_mip_file_present and len(_no_mip_policy) > 0:
        return
    if _no_mip_warning_shown:
        return
    _no_mip_warning_shown = True
    if not _no_mip_file_present:
        msg = (
            f"{NO_MIP_FILENAME} not found next to ctxr3.py.\n\n"
            "Auto-mip mode will generate mipmaps for every texture. UI/HUD "
            "textures that should NOT have mipmaps may be incorrectly "
            "regenerated with mipmaps. Place the rules file next to "
            "ctxr3.py and click 'Reload no-mip rules', or use the explicit "
            "'no (single level)' option for those textures."
        )
    else:
        msg = (
            f"{NO_MIP_FILENAME} is empty.\n\n"
            "Auto-mip mode will generate mipmaps for every texture. UI/HUD "
            "textures that should NOT have mipmaps may be incorrectly "
            "regenerated with mipmaps."
        )
    try:
        messagebox.showwarning("No-mip rules missing", msg)
    except Exception:
        logging.warning(msg)


# ---------------------------------------------------------------------------

def _bgra_to_pil_rgba(bgra: bytes, width: int, height: int) -> Image.Image:
    img = Image.frombytes("RGBA", (width, height), bgra)
    b, g, r, a = img.split()
    return Image.merge("RGBA", (r, g, b, a))


def _pil_rgba_to_bgra(img: Image.Image) -> bytes:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.tobytes("raw", "BGRA")


def save_as_tga(image: Image.Image, file_path: str) -> None:
    width, height = image.size

    header = bytearray(18)
    header[2] = 2                           # uncompressed RGB
    struct.pack_into("<H", header, 12, width)
    struct.pack_into("<H", header, 14, height)
    header[16] = 32                         # bpp
    header[17] = 0x20                       # top-left origin

    if image.mode != "RGBA":
        image = image.convert("RGBA")
    r, g, b, a = image.split()
    bgra = Image.merge("RGBA", (b, g, r, a))

    with open(file_path, "wb") as f:
        f.write(header)
        f.write(bgra.tobytes())


# ---------------------------------------------------------------------------
# Generate PNG/TGA mips with Lanczos.
# Vanilla files are generated with nvtt's higher quality kaiser filter, but PIL doesn't offer it.
# ergo, dds -> ctxr will always offer the highest quality textures.
# ---------------------------------------------------------------------------

def _generate_rgba_mip_chain(top_image: Image.Image,
                             num_levels: int) -> list[Image.Image]:
    if top_image.mode != "RGBA":
        top_image = top_image.convert("RGBA")
    out = [top_image]
    w, h = top_image.size
    for _ in range(1, num_levels):
        w = max(1, w // 2)
        h = max(1, h // 2)
        out.append(top_image.resize((w, h), Image.LANCZOS))
    return out


# ---------------------------------------------------------------------------

def _build_uncompressed_ctxr_from_pil(
    image: Image.Image,
    generate_mipmaps: Optional[bool] = None,
    name_for_policy: Optional[str] = None,
) -> CTXRTexture:
    defaults = CTXRHeader()
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    width, height = image.size

    if generate_mipmaps is None:
        _maybe_warn_missing_no_mip_rules()
        name_for_lookup = name_for_policy or ""
        rule = _no_mip_policy.matching_rule(name_for_lookup)
        want_mips = rule is None
        if rule:
            logging.info(
                "no-mip rule %r matched %s -> single level",
                rule, os.path.basename(name_for_lookup) or "(unnamed)",
            )
    else:
        want_mips = bool(generate_mipmaps)

    levels = num_mip_maps(width, height) if want_mips else 1
    pil_mips = _generate_rgba_mip_chain(image, levels)

    rgba_mips: list[bytes] = [m.tobytes("raw", "RGBA") for m in pil_mips]
    bgra_mips: list[bytes] = [m.tobytes("raw", "BGRA") for m in pil_mips]

    min_rgba, max_rgba, has_alpha = calc_min_max_rgba(rgba_mips)

    new_header = CTXRHeader(
        width=width,
        height=height,
        depth=1,
        format=FORMAT_A8R8G8B8,
        has_alpha=has_alpha,
        additional_flags=defaults.additional_flags,
        min_rgba=min_rgba,
        max_rgba=max_rgba,
        filter_hint=defaults.filter_hint,
        alpha_ref_value=defaults.alpha_ref_value,
        max_lod_offset=defaults.max_lod_offset,
        type=defaults.type,
        num_levels=levels,
        version=defaults.version,
    )
    return CTXRTexture(header=new_header, mips=bgra_mips)


# ---------------------------------------------------------------------------
# CLI & drag-and-drop support
# ---------------------------------------------------------------------------

IMAGE_INPUT_EXTS = (".png", ".tga", ".dds")


def convert_image_to_ctxr(
    input_path: str,
    output_path: Optional[str] = None,
    generate_mipmaps: Optional[bool] = None,
) -> str:

    # DDS copy mips over 1:1 / ignore no_mip_regex. 

    ext = os.path.splitext(input_path)[1].lower()
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + ".ctxr"


    if _must_be_dxt5_policy.requires_dxt5(input_path):
        if ext == ".dds":
            from dds_module import parse_dds_header
            with open(input_path, "rb") as _f:
                _hdr = _f.read(128)
            _w, _h, _mc, _fourcc, _comp = parse_dds_header(_hdr)
            if _fourcc != b"DXT5":
                raise CTXRError(
                    f"{os.path.basename(input_path)} must be DXT5, but this "
                    f"DDS is {_fourcc.decode('ascii', 'replace').strip() or 'uncompressed'}. "
                    f"Re-export it as a DXT5 .dds."
                )
        else:
            raise CTXRError(
                f"{os.path.basename(input_path)} must be DXT5. This tool only "
                f"cooks {ext.lstrip('.').upper()} as uncompressed A8R8G8B8 — "
                f"convert it to a DXT5 .dds first."
            )

    if ext == ".dds":
        from ctxr_utils import serialize_header
        template_bytes = serialize_header(CTXRHeader())
        dds_to_ctxr(input_path, output_path, template_bytes)
    elif ext in (".png", ".tga"):
        image = Image.open(input_path)
        tex = _build_uncompressed_ctxr_from_pil(
            image,
            generate_mipmaps=generate_mipmaps,
            name_for_policy=output_path,
        )
        write_ctxr(output_path, tex)
    else:
        raise CTXRError(f"unsupported input extension {ext!r} for ->CTXR")

    return output_path


def convert_ctxr_to_dds(input_path: str,
                        output_path: Optional[str] = None) -> str:
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + ".dds"
    ctxr_to_dds(input_path, output_path)
    return output_path


def convert_ctxr_to_image(input_path: str,
                          output_path: Optional[str] = None,
                          out_format: str = "dds") -> str:
    out_format = out_format.lower()
    if out_format not in _VALID_CLI_OUT_FORMATS:
        raise CTXRError(f"unsupported output format {out_format!r}")
    if output_path is None:
        output_path = os.path.splitext(input_path)[0] + "." + out_format

    if out_format == "dds":
        ctxr_to_dds(input_path, output_path)
        return output_path

    tex = read_ctxr(input_path)
    h = tex.header
    if h.format != FORMAT_A8R8G8B8:
        raise CTXRError(
            f"{os.path.basename(input_path)} is "
            f"{FORMAT_NAMES.get(h.format, h.format)}-compressed; only dds can "
            f"hold it. Set output_format = dds for this texture."
        )
    image_rgba = _bgra_to_pil_rgba(tex.mips[0], h.width, h.height)
    if out_format == "tga":
        save_as_tga(image_rgba, output_path)
    else:
        image_rgba.save(output_path, out_format.upper(), optimize=False)
    return output_path


def convert_path(input_path: str,
                 output_path: Optional[str] = None,
                 generate_mipmaps: Optional[bool] = None) -> str:
    ext = os.path.splitext(input_path)[1].lower()
    if ext == ".ctxr":
        out_format = _cli_output_format
        if output_path:
            o_ext = os.path.splitext(output_path)[1].lower().lstrip(".")
            if o_ext in _VALID_CLI_OUT_FORMATS:
                out_format = o_ext
        return convert_ctxr_to_image(input_path, output_path, out_format)
    if ext in IMAGE_INPUT_EXTS:
        return convert_image_to_ctxr(input_path, output_path, generate_mipmaps)
    raise CTXRError(
        f"don't know how to convert {os.path.basename(input_path)} "
        f"(extension {ext!r})"
    )


# ---------------------------------------------------------------------------

def open_file():
    try:
        file_path = filedialog.askopenfilename(
            title="Select a CTXR file",
            filetypes=[("CTXR files", "*.ctxr")],
        )
        if not file_path:
            return

        tex = read_ctxr(file_path)
        h = tex.header

        logging.info(
            "Loaded %s: %dx%d %s, %d mips, hasAlpha=%s",
            os.path.basename(file_path), h.width, h.height,
            FORMAT_NAMES.get(h.format, h.format), h.num_levels, h.has_alpha,
        )

        out_format = chosen_format.get().split()[-1]
        output_file_path = file_path[:-5] + "." + out_format

        if out_format == "dds":
            ctxr_to_dds(file_path, output_file_path)
            label.config(text=f"Saved {os.path.basename(output_file_path)} "
                              f"({FORMAT_NAMES.get(h.format, h.format)})")
            return

        if h.format != FORMAT_A8R8G8B8:
            messagebox.showinfo(
                "Compressed CTXR",
                f"This file is {FORMAT_NAMES.get(h.format, h.format)}-compressed. "
                "Only DDS preserves the compressed payload — please choose "
                "'dds' to convert it.",
            )
            label.config(text=f"{FORMAT_NAMES.get(h.format, h.format)} "
                              "files require DDS output")
            return

        image_rgba = _bgra_to_pil_rgba(tex.mips[0], h.width, h.height)

        if out_format == "tga":
            save_as_tga(image_rgba, output_file_path)
        else:
            image_rgba.save(output_file_path, out_format.upper(), optimize=False)

        label.config(text=f"Saved {os.path.basename(output_file_path)}")

    except Exception as e:
        logging.error("Error processing file: %s", e)
        logging.error(traceback.format_exc())
        messagebox.showerror("Error", str(e))
        label.config(text="Error opening file")


# ---------------------------------------------------------------------------

def _resolve_mip_choice() -> Optional[bool]:
    #don't forget to update mip_mode_options if you change these.
    v = chosen_mip_mode.get()
    if v == "auto (use no_mip_regex.txt)":
        return None
    if v == "force mip generation (EXPERT MODE)":
        return True
    if v == "dont generate mips":
        return False
    return None

def save_as_ctxr():
    try:
        file_path = filedialog.askopenfilename(
            title="Select an image file",
            filetypes=[
                ("All Supported Formats", "*.tga;*.dds;*.png"),
                ("TGA files", "*.tga"),
                ("DDS files", "*.dds"),
                ("PNG files", "*.png"),
            ],
        )
        if not file_path:
            return

        ctxr_out = convert_image_to_ctxr(
            file_path,
            generate_mipmaps=_resolve_mip_choice(),
        )

        label.config(text=f"File saved as {os.path.basename(ctxr_out)}")
        logging.info("Successfully saved CTXR: %s", ctxr_out)

    except Exception as e:
        logging.error("Error saving CTXR file: %s", e)
        logging.error(traceback.format_exc())
        messagebox.showerror("Error", str(e))
        label.config(text="Error occurred during save")


# ---------------------------------------------------------------------------
# Batch stuff
# ---------------------------------------------------------------------------

def _ctxr_files_in(folder: str) -> list[str]:
    return [f for f in os.listdir(folder) if f.lower().endswith(".ctxr")]


def batch_convert_ctxr_to_image(out_ext: str):
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    if not folder_path:
        return
    out_folder = folder_path
    if out_ext == "dds":
        chosen = filedialog.askdirectory(title="Select a destination folder for DDS files")
        if chosen:
            out_folder = chosen

    files = _ctxr_files_in(folder_path)
    progress["maximum"] = len(files)
    progress["value"] = 0

    failures: list[tuple[str, str]] = []
    for name in files:
        in_p = os.path.join(folder_path, name)
        out_p = os.path.join(out_folder, name[:-5] + "." + out_ext)
        try:
            if out_ext == "dds":
                ctxr_to_dds(in_p, out_p)
            else:
                tex = read_ctxr(in_p)
                if tex.header.format != FORMAT_A8R8G8B8:
                    failures.append((name,
                        f"{FORMAT_NAMES.get(tex.header.format, tex.header.format)} "
                        "is compressed; export as DDS instead"))
                    continue
                img = _bgra_to_pil_rgba(tex.mips[0], tex.header.width, tex.header.height)
                if out_ext == "png":
                    img.save(out_p, "PNG", optimize=False)
                elif out_ext == "tga":
                    save_as_tga(img, out_p)
            progress["value"] += 1
            app.update_idletasks()
        except Exception as e:
            logging.exception("batch %s failed: %s", out_ext, name)
            failures.append((name, str(e)))

    if failures:
        msgs = "\n".join(f"{n}: {e}" for n, e in failures)
        label.config(text=f"Conversion completed with {len(failures)} errors")
        messagebox.showwarning("Conversion Errors",
                               f"Some files failed:\n{msgs[:500]}")
    else:
        label.config(text=f"Conversion Completed ({len(files)} files)")


def batch_convert_ctxr_to_png():
    batch_convert_ctxr_to_image("png")


def batch_convert_ctxr_to_tga():
    batch_convert_ctxr_to_image("tga")


def batch_convert_ctxr_to_dds():
    batch_convert_ctxr_to_image("dds")


def batch_convert_png_to_ctxr():
    png_folder = filedialog.askdirectory(title="Select a folder with PNG files")
    if not png_folder:
        return
    out_folder = filedialog.askdirectory(
        title="Select a destination folder for CTXR files")
    if not out_folder:
        return

    files = [f for f in os.listdir(png_folder) if f.lower().endswith(".png")]
    progress["maximum"] = len(files)
    progress["value"] = 0
    failures: list[tuple[str, str]] = []

    for name in files:
        try:
            png_path = os.path.join(png_folder, name)
            out_path = os.path.join(out_folder, name[:-4] + ".ctxr")

            # dxt5 textures required precooked dds, don't allow pngs.
            if _must_be_dxt5_policy.requires_dxt5(out_path):
                failures.append((name,
                    "must be DXT5; convert to a DXT5 .dds instead of PNG"))
                continue

            image = Image.open(png_path)
            tex = _build_uncompressed_ctxr_from_pil(
                image,
                generate_mipmaps=_resolve_mip_choice(),
                name_for_policy=out_path,
            )
            write_ctxr(out_path, tex)
            progress["value"] += 1
            app.update_idletasks()
        except Exception as e:
            logging.exception("PNG->CTXR failed: %s", name)
            failures.append((name, str(e)))

    if failures:
        msgs = "\n".join(f"{n}: {e}" for n, e in failures)
        messagebox.showwarning("Conversion Errors",
                               f"Some files failed:\n{msgs[:500]}")
        label.config(text=f"PNG->CTXR completed with {len(failures)} errors")
    else:
        label.config(text=f"PNG->CTXR completed ({len(files)} files)")

    if failures:
        msgs = "\n".join(f"{n}: {e}" for n, e in failures)
        messagebox.showwarning("Conversion Errors",
                               f"Some files failed:\n{msgs[:500]}")
        label.config(text=f"PNG->CTXR completed with {len(failures)} errors")
    else:
        label.config(text=f"PNG->CTXR completed ({len(files)} files)")


def batch_convert_dds_to_ctxr():
    dds_folder = filedialog.askdirectory(title="Select a folder with DDS files")
    if not dds_folder:
        return
    out_folder = filedialog.askdirectory(
        title="Select a destination folder for CTXR files")
    if not out_folder:
        return

    files = [f for f in os.listdir(dds_folder) if f.lower().endswith(".dds")]
    progress["maximum"] = len(files)
    progress["value"] = 0
    failures: list[tuple[str, str]] = []
    success = 0

    for name in files:
        try:
            in_path = os.path.join(dds_folder, name)
            out_path = os.path.join(out_folder, name[:-4] + ".ctxr")
            convert_image_to_ctxr(in_path, out_path)
            success += 1
            progress["value"] += 1
            app.update_idletasks()
        except Exception as e:
            logging.exception("DDS->CTXR failed: %s", name)
            failures.append((name, str(e)))

    if failures:
        msgs = "\n".join(f"{n}: {e}" for n, e in failures)
        label.config(text=f"DDS->CTXR completed with {len(failures)} errors")
        messagebox.showwarning("Conversion Errors",
                               f"Some files failed:\n{msgs[:500]}")
    else:
        label.config(text=f"DDS->CTXR completed ({success} files)")
        messagebox.showinfo("Success", f"Successfully converted {success} files")


def batch_convert():
    func_map = {
        "ctxr to png": batch_convert_ctxr_to_png,
        "ctxr to tga": batch_convert_ctxr_to_tga,
        "png to ctxr": batch_convert_png_to_ctxr,
        "ctxr to dds": batch_convert_ctxr_to_dds,
        "dds to ctxr": batch_convert_dds_to_ctxr,
    }
    try:
        func_map[chosen_batch_format.get()]()
    except KeyError:
        messagebox.showerror("Error", "Selected batch format not implemented yet")
    except Exception as e:
        logging.exception("Batch conversion failed")
        messagebox.showerror("Error", str(e))


# ---------------------------------------------------------------------------

def _gui_dds_to_ps3():
    dds_path = filedialog.askopenfilename(
        title="Select a DDS file",
        filetypes=[("DDS files", "*.dds")],
    )
    if not dds_path:
        return
    template = None
    if messagebox.askyesno(
        "Template",
        "Inherit metadata (min/max RGBA, flags, filter hint) from an "
        "original PS3 .ctxr?\n\nYes -> pick a template\nNo -> use defaults",
    ):
        template = filedialog.askopenfilename(
            title="Select a template PS3 CTXR file",
            filetypes=[("CTXR files", "*.ctxr")],
        ) or None
    try:
        out = convert_dds_to_ps3_ctxr(dds_path, template_ctxr=template)
        label.config(text=f"Saved {os.path.basename(out)}")
    except Exception as e:
        logging.exception("DDS->PS3 failed")
        messagebox.showerror("Error", str(e))


def launch_gui():
    global app, label, progress, main_frame, notebook, general_frame
    global chosen_format, chosen_batch_format, chosen_mip_mode
    global photo_icon, image_icon, ps3_frame

    _import_tk()

    app = tk.Tk()
    app.title("CTXR Converter 3.1 by 316austin316 and Afevis")
    app.geometry("700x600")

    res_base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(res_base, "resources", "face.PNG")
    if os.path.exists(icon_path):
        image_icon = Image.open(icon_path)
        photo_icon = ImageTk.PhotoImage(image_icon)
        app.iconphoto(False, photo_icon)
        Label(app, image=photo_icon).pack(pady=5)

    label = Label(app, text="Kept you waiting huh?")
    label.pack(pady=5)

    progress = ttk.Progressbar(app, orient="horizontal", length=300, mode="determinate")
    progress.pack(pady=20)

    main_frame = Frame(app)
    main_frame.pack(pady=10, padx=10, fill="both", expand=True)

    notebook = ttk.Notebook(main_frame)
    notebook.pack(fill="both", expand=True)

    general_frame = Frame(notebook)
    notebook.add(general_frame, text="PC")

    Label(general_frame, text="CTXR Converter",
          font=("Arial", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=10)
    Label(general_frame, text="For MGS2 & MGS3 HD / Master Collection\nCode by 316austin316 and Afevis",
          font=("Arial", 10)).grid(row=1, column=0, columnspan=2, pady=10)

    Button(general_frame, text="Open CTXR File", command=open_file,
           bg="#4CAF50", fg="white", font=("Arial", 10, "bold")
           ).grid(row=2, column=0, pady=10, padx=5, sticky="ew")

    Button(general_frame, text="Save as CTXR", command=save_as_ctxr,
           bg="#FF9800", fg="white", font=("Arial", 10, "bold")
           ).grid(row=2, column=1, pady=10, padx=5, sticky="ew")

    format_options = ["output png", "output tga", "output dds"]
    chosen_format = StringVar(value=format_options[0])
    OptionMenu(general_frame, chosen_format, *format_options
               ).grid(row=3, column=0, pady=10, padx=5, sticky="ew")

    Label(general_frame,
          text="Compressed (DXT1/3/5) CTXRs need DDS",
          font=("Arial", 8), fg="#FF5722"
          ).grid(row=3, column=1, pady=10, padx=5, sticky="w")

    batch_format_options = ["ctxr to png", "ctxr to tga", "png to ctxr",
                            "ctxr to dds", "dds to ctxr"]
    chosen_batch_format = StringVar(value=batch_format_options[0])
    OptionMenu(general_frame, chosen_batch_format, *batch_format_options
               ).grid(row=4, column=0, pady=10, padx=5, sticky="ew")

    Button(general_frame, text="Batch Convert", command=batch_convert,
           bg="#2196F3", fg="white", font=("Arial", 10, "bold")
           ).grid(row=4, column=1, pady=10, padx=5, sticky="ew")

    Label(general_frame, text="Mipmap Generation (for PNG/TGA -> CTXR):\nUI, speculars (sub_ovl), atlas textures should NOT use mips.\n",
          font=("Arial", 9)).grid(row=5, column=0, pady=(10, 0), padx=5, sticky="e")

    #don't forget to update _resolve_mip_choice if you change these
    mip_mode_options = ["auto (use no_mip_regex.txt)",
                        "force mip generation (EXPERT MODE)",
                        "dont generate mips"]
    chosen_mip_mode = StringVar(value=mip_mode_options[0])
    OptionMenu(general_frame, chosen_mip_mode, *mip_mode_options
               ).grid(row=5, column=1, pady=(10, 0), padx=5, sticky="ew")

    Button(general_frame, text="Reload no-mip rules",
           command=reload_no_mip_policy,
           bg="#607D8B", fg="white", font=("Arial", 9)
           ).grid(row=6, column=0, columnspan=2, pady=(0, 5), padx=5, sticky="ew")

    if _HAS_VIEWER:
        Button(general_frame, text="Open Image Viewer",
               command=lambda: ImageViewer(app),
               bg="#FF5722", fg="white", font=("Arial", 10, "bold")
               ).grid(row=7, column=0, columnspan=2, pady=10, padx=5, sticky="ew")

    for i in range(8):
        general_frame.grid_rowconfigure(i, weight=1)
    for i in range(2):
        general_frame.grid_columnconfigure(i, weight=1)

    ps3_frame = Frame(notebook)
    notebook.add(ps3_frame, text="PS3")
    if _HAS_PS3:
        Button(ps3_frame, text="Convert PS3 CTXR to DDS",
               command=convert_ps3_ctxr_to_dds,
               bg="#9C27B0", fg="white", font=("Arial", 10, "bold")
               ).pack(pady=20, padx=20, fill="x")
        Button(ps3_frame, text="Batch Convert PS3 CTXR to DDS",
               command=batch_convert_ps3_ctxr_to_dds,
               bg="#673AB7", fg="white", font=("Arial", 10, "bold")
               ).pack(pady=10, padx=20, fill="x")
        Button(ps3_frame, text="Convert DDS to PS3 CTXR",
               command=_gui_dds_to_ps3,
               bg="#3F51B5", fg="white", font=("Arial", 10, "bold")
               ).pack(pady=10, padx=20, fill="x")
    else:
        Label(ps3_frame, text="PS3 module unavailable",
              font=("Arial", 10), fg="#666").pack(pady=20)

    if not _no_mip_file_present or len(_no_mip_policy) == 0:
        app.after(100, _maybe_warn_missing_no_mip_rules)
    app.mainloop()


# ---------------------------------------------------------------------------

def _cli_mip_choice(args) -> Optional[bool]:
     #   --no-mips           -> False
     #   --mips              -> True 
     #   --ignore-no-mip-regex -> True 
     #   no arg = auto / use no_mip_regex.txt
    if args.no_mips:
        return False
    if args.mips:
        return True
    if args.ignore_no_mip_regex:
        return True
    return None  # auto: use no_mip_regex.txt


def run_cli(argv) -> int:
    parser = argparse.ArgumentParser(
        prog="ctxr3",
        description="Convert between .ctxr and image/DDS formats. "
                    "With no arguments, launches the GUI.",
    )
    parser.add_argument(
        "inputs", nargs="*",
        help="Input file(s). .ctxr -> DDS; .png/.tga/.dds -> .ctxr",
    )
    parser.add_argument(
        "-o", "--output",
        help="Explicit output path (only valid with a single input).",
    )
    mip_group = parser.add_mutually_exclusive_group()
    mip_group.add_argument(
        "--mips", action="store_true",
        help="Force full mip chain for image->ctxr (overrides regex policy).",
    )
    mip_group.add_argument(
        "--no-mips", action="store_true",
        help="Force single level for image->ctxr (overrides regex policy).",
    )
    parser.add_argument(
        "--ignore-no-mip-regex", "--ignore-regex", action="store_true",
        dest="ignore_no_mip_regex",
        help="Do not consult no_mip_regex.txt. On its own this generates a "
             "full mip chain for every image->ctxr (and suppresses the "
             "missing-rules warning). Can be combined with --no-mips to skip "
             "the regex but still force single level.",
    )
    args = parser.parse_args(argv)

    if not args.inputs:
        # No files: fall through to GUI.
        return -1

    if args.output and len(args.inputs) > 1:
        parser.error("-o/--output cannot be used with multiple inputs")

    mip_choice = _cli_mip_choice(args)

    if mip_choice is None and (not _no_mip_file_present or len(_no_mip_policy) == 0):
        print(
            f"WARNING: {NO_MIP_FILENAME} not found or empty next to "
            f"ctxr3.py; image->ctxr conversions will generate mipmaps "
            f"for every texture. UI/HUD textures that should be mipless "
            f"may be wrong. Use --no-mips for those, or add the rules "
            f"file.",
            file=sys.stderr,
        )

    failures = 0
    for inp in args.inputs:
        try:
            if not os.path.isfile(inp):
                print(f"ERROR: not a file: {inp}", file=sys.stderr)
                logging.error("CLI conversion failed: not a file: %s", inp)
                failures += 1
                continue
            out = convert_path(inp, args.output, generate_mipmaps=mip_choice)
            print(f"OK: {inp} -> {out}")
        except CTXRError as e:
            print(f"ERROR: {inp}: {e}", file=sys.stderr)
            logging.error("CLI conversion failed: %s: %s", inp, e)
            failures += 1
        except Exception as e:
            print(f"ERROR: {inp}: {e}", file=sys.stderr)
            logging.exception("CLI conversion failed unexpectedly: %s", inp)
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    # args passed = CLI mode, otherwise, open the gui
    if len(sys.argv) > 1:
        rc = run_cli(sys.argv[1:])
        if rc != -1:
            sys.exit(rc)
    launch_gui()
