import tkinter as tk
from tkinter import ttk
from tkinter import Label, Button, OptionMenu, StringVar, Frame, filedialog, messagebox
from PIL import Image, ImageTk
import struct
import os
import numpy as np
import ps3_ctxr_module
from ps3_ctxr_module import convert_ps3_ctxr_to_dds, batch_convert_ps3_ctxr_to_dds

# Global variables to store the original header and complete mipmap info
global label, ctxr_header, original_mipmap_info, original_final_padding
ctxr_header = None
original_mipmap_info = []      # List of dicts: for each mipmap level: {"padding": bytes, "size": int, "data": bytes}
original_final_padding = b""  # Final padding after the last mipmap


def read_padding_and_size(file_obj, expected_mip_size, max_pad=32):
    """
    Reads padding bytes from file_obj until the next 4 bytes (when peeked) equal expected_mip_size.
    Returns a tuple (padding, mip_size, mip_data) where:
      - padding: all zero bytes read as padding,
      - mip_size: the 4-byte integer (big-endian) that was read,
      - mip_data: the subsequent mipmap pixel data (of length mip_size).
    max_pad is a safeguard to not read more than max_pad padding bytes.
    """
    padding = b""
    while len(padding) < max_pad:
        pos = file_obj.tell()
        # Peek at the next 4 bytes without advancing the file pointer
        candidate = file_obj.read(4)
        file_obj.seek(pos)
        if len(candidate) < 4:
            raise ValueError("Unexpected end of file when peeking for mipmap size")
        candidate_size = struct.unpack('>I', candidate)[0]
        # If the candidate equals the expected mipmap size, we are at the size field.
        if candidate_size == expected_mip_size:
            break
        else:
            # Consume one padding byte and continue.
            padding += file_obj.read(1)
    # Now read the 4-byte mipmap size field
    size_bytes = file_obj.read(4)
    if len(size_bytes) != 4:
        raise ValueError("Unexpected end of file when reading mipmap size")
    mip_size = struct.unpack('>I', size_bytes)[0]
    # Read the mipmap pixel data.
    mip_data = file_obj.read(mip_size)
    return padding, mip_size, mip_data


def parse_mipmap_info(file_obj, mipmap_count, width, height):
    """
    For each mipmap level (from level 1 to mipmap_count-1), compute the expected mipmap dimensions,
    then dynamically read padding bytes (using read_padding_and_size) until the next 4-byte integer
    equals the expected mipmap size.
    
    Returns a tuple: (list_of_mipmap_info, final_padding)
    Each entry in list_of_mipmap_info is a dict with keys:
      "padding": the bytes read as padding,
      "size": the mipmap size (as an integer),
      "data": the mipmap pixel data.
    The final_padding is the remaining padding after the last mipmap (expected to be 24 bytes).
    """
    mip_info = []
    for level in range(1, mipmap_count):
        mip_w = max(1, width >> level)
        mip_h = max(1, height >> level)
        expected_size = mip_w * mip_h * 4
        print(f"[Level {level}] Expected dimensions: {mip_w}x{mip_h} (expected {expected_size} bytes)")
        pad, mip_size, mip_data = read_padding_and_size(file_obj, expected_size)
        print(f"[Level {level}] Read {len(pad)} padding bytes; size field: {mip_size} bytes; pixel data: {len(mip_data)} bytes")
        mip_info.append({"padding": pad, "size": mip_size, "data": mip_data})
    final_padding = file_obj.read(24)
    print(f"[Final] Read final padding of {len(final_padding)} bytes")
    return mip_info, final_padding


def open_file():
    global ctxr_header, original_mipmap_info, original_final_padding
    # List of files that require a different DDS header (unchanged)
    dxt5_files = [
        "jngl_happa04_alp_ovl.bmp.ctxr",
        "jngl_happa04_alp_ovl_mip16000.bmp.ctxr",
        "jngl_happa04_alp_ovl_mip16000.bmp_c82c791b86086ed52d483520273e9b5b.ctxr",
        "jngl_happa04_alp_ovl_mip8000.bmp.ctxr",
        "jngl_happa05_alp_ovl_mip4000.bmp.ctxr",
        "jngl_taki_eda_12_alp_ovl_mip8000.bmp.ctxr",
        "jngl_taki_eda_17_alp_ovl_mip4000.bmp.ctxr",
        "s001a_enkeil_rep.bmp.ctxr",
        "s001a_happa05_alp_ovl_mip8000.bmp.ctxr",
        "s001a_soil01_rep_mip8000.bmp.ctxr",
        "v000a_kinokatamari_a01_alp_ovl_rep.bmp.ctxr",
        "v000a_kinokatamari_a01_alp_ovl_rep.bmp_86187137555744c273e17dd4a431d1a2.ctxr",
        "v000a_kinokatamari_a03_alp_ovl_rep.bmp.ctxr",
        "v000a_kinokatamari_a03_alp_ovl_rep.bmp_d9ec09aa2448dfac3e0b72eca57e0034.ctxr",
    ]

    file_path = filedialog.askopenfilename(title="Select a CTXR file", filetypes=[("CTXR files", "*.ctxr")])
    if not file_path:
        return

    with open(file_path, 'rb') as file_obj:
        ctxr_header = file_obj.read(132)
        mipmap_count = struct.unpack_from('>B', ctxr_header, 0x26)[0]
        pixel_data_length = struct.unpack_from('>I', ctxr_header, 0x80)[0]
        width = struct.unpack_from('>H', ctxr_header, 8)[0]
        height = struct.unpack_from('>H', ctxr_header, 10)[0]
        pixel_data = file_obj.read(pixel_data_length)
        print(f"Header: {width}x{height} main level, pixel data length: {pixel_data_length}")
        print(f"Mipmap count from header: {mipmap_count}")

        if mipmap_count > 1:
            original_mipmap_info, original_final_padding = parse_mipmap_info(file_obj, mipmap_count, width, height)
        else:
            original_mipmap_info = []
            original_final_padding = b""

    # Convert main pixel data from BGRA to RGBA for display or further processing.
    image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
    r, g, b, a = image_bgra.split()
    image_rgba = Image.merge("RGBA", (b, g, r, a))
    output_file_path = file_path.replace('.ctxr', f'.{chosen_format.get()}')

    if chosen_format.get() == "dds":
        # Generate DDS mipmaps using high-quality Lanczos filtering.
        mipmaps = [image_rgba]
        curr_w, curr_h = width, height
        for i in range(1, mipmap_count):
            curr_w = max(1, curr_w // 2)
            curr_h = max(1, curr_h // 2)
            mip_image = image_rgba.resize((curr_w, curr_h), Image.LANCZOS)
            mipmaps.append(mip_image)
            print(f"Generated mipmap level {i+1}: {mip_image.width}x{mip_image.height}")
        dds_header_file = "DDS_header.bin"
        if os.path.basename(file_path) in dxt5_files:
            dds_header_file = "DDS_header_DXT5.bin"
        with open(dds_header_file, "rb") as header_file:
            dds_header = bytearray(header_file.read())
        struct.pack_into("<I", dds_header, 12, height)
        struct.pack_into("<I", dds_header, 16, width)
        struct.pack_into("<I", dds_header, 28, mipmap_count)
        with open(output_file_path, "wb") as dds_file:
            dds_file.write(dds_header)
            for mip_image in mipmaps:
                mip_data = mip_image.tobytes("raw", "BGRA")
                if len(mip_data) % 4 != 0:
                    mip_data += b'\x00' * (4 - (len(mip_data) % 4))
                dds_file.write(mip_data)
    else:
        image_rgba.save(output_file_path, chosen_format.get().upper(), compress_level=0)

    label.config(text=f"File saved as {output_file_path}")



def save_as_ctxr():
    global ctxr_header, original_mipmap_info, original_final_padding

    if not ctxr_header:
        label.config(text="Please open a CTXR file first.")
        return

    file_path = filedialog.askopenfilename(
        title="Select an image file",
        filetypes=[("All Supported Formats", "*.tga;*.dds;*.png;*.TGA;*.DDS;*.PNG"),
                   ("TGA files", "*.tga;*.TGA"),
                   ("DDS files", "*.dds;*.DDS"),
                   ("PNG files", "*.png;*.PNG")]
    )
    if not file_path:
        return

    # Retrieve the mipmap count from the original header.
    mipmap_count = struct.unpack_from('>B', ctxr_header, 0x26)[0]

    # Open the new image.
    image = Image.open(file_path)
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    r, g, b, a = image.split()
    # CTXR files store data as BGRA.
    image_bgra = Image.merge("RGBA", (b, g, r, a))
    width, height = image.size
    main_pixel_data = image_bgra.tobytes("raw", "BGRA")
    total_data_length = len(main_pixel_data)

    # Generate new mipmap data from the new image.
    new_mipmap_data = []
    if mipmap_count > 1 and original_mipmap_info:
        mipmaps = [image_bgra]
        curr_w, curr_h = width, height
        for i in range(1, mipmap_count):
            curr_w = max(1, curr_w // 2)
            curr_h = max(1, curr_h // 2)
            mip_image = image_bgra.resize((curr_w, curr_h), Image.LANCZOS)
            mipmaps.append(mip_image)
        for i, mip_image in enumerate(mipmaps[1:]):
            new_data = mip_image.tobytes("raw", "BGRA")
            # Even if new_data is a different length, we preserve the original padding length.
            new_mipmap_data.append(new_data)
    else:
        mipmap_count = 1  # No mipmaps beyond main level

    # Update header with new dimensions and main data length.
    ctxr_header = bytearray(ctxr_header)
    struct.pack_into('>H', ctxr_header, 8, width)
    struct.pack_into('>H', ctxr_header, 10, height)
    struct.pack_into('>I', ctxr_header, 0x80, total_data_length)
    struct.pack_into('>B', ctxr_header, 0x26, mipmap_count)

    # Write out the new CTXR file.
    ctxr_file_path = file_path.rsplit('.', 1)[0] + '.ctxr'
    with open(ctxr_file_path, 'wb') as f:
        f.write(ctxr_header)
        f.write(main_pixel_data)
        if mipmap_count > 1:
            for i, new_data in enumerate(new_mipmap_data):
                # Retrieve the original padding length for this mipmap level.
                orig_pad = original_mipmap_info[i]["padding"]
                # Write the original padding exactly.
                f.write(orig_pad)
                # Write a new size field based on the new mipmap data length.
                new_size = len(new_data)
                f.write(struct.pack('>I', new_size))
                # Write the new mipmap pixel data.
                f.write(new_data)
            # Write the final padding as originally read.
            f.write(original_final_padding)
        else:
            f.write(original_final_padding)

    label.config(text=f"File saved as {ctxr_file_path}")


def batch_convert_ctxr_to_png():
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    if not folder_path:
        return

    files_to_convert = [f for f in os.listdir(folder_path) if f.endswith('.ctxr')]
    total_files = len(files_to_convert)
    progress["maximum"] = total_files
    progress["value"] = 0
    failed_files = []

    for file in files_to_convert:
        file_path = os.path.join(folder_path, file)
        try:
            with open(file_path, 'rb') as f:
                ctxr_header_local = f.read(132)
                mipmap_count = struct.unpack_from('>B', ctxr_header_local, 0x26)[0]
                pixel_data_length = struct.unpack_from('>I', ctxr_header_local, 0x80)[0]
                width = struct.unpack_from('>H', ctxr_header_local, 8)[0]
                height = struct.unpack_from('>H', ctxr_header_local, 10)[0]
                pixel_data = f.read(pixel_data_length)
                if mipmap_count > 1:
                    _ , _ = parse_mipmap_info(f, mipmap_count, width, height)
            image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
            r, g, b, a = image_bgra.split()
            image_rgba = Image.merge("RGBA", (b, g, r, a))
            png_file_path = os.path.join(folder_path, file.replace('.ctxr', '.png'))
            image_rgba.save(png_file_path, 'PNG', compress_level=0)
            progress["value"] += 1
            app.update_idletasks()
        except Exception as e:
            failed_files.append((file, str(e)))
    if failed_files:
        error_messages = "\n".join([f"Error with {name}: {err}" for name, err in failed_files])
        label.config(text=f"Conversion Completed with errors:\n{error_messages}")
    else:
        label.config(text=f"Conversion Completed for folder {folder_path}")


def batch_convert_png_to_ctxr():
    png_folder_path = filedialog.askdirectory(title="Select a folder with PNG files")
    ctxr_folder_path = filedialog.askdirectory(title="Select a folder with original CTXR files for headers")
    if not png_folder_path or not ctxr_folder_path:
        return

    files_to_convert = [f for f in os.listdir(png_folder_path) if f.lower().endswith('.png')]
    total_files = len(files_to_convert)
    progress["maximum"] = total_files
    progress["value"] = 0

    for file in files_to_convert:
        png_file_path = os.path.join(png_folder_path, file)
        ctxr_file_path = os.path.join(ctxr_folder_path, file.replace('.png', '.ctxr'))
        if not os.path.exists(ctxr_file_path):
            continue

        with open(ctxr_file_path, 'rb') as f:
            ctxr_header_local = f.read(132)
            mipmap_count = struct.unpack_from('>B', ctxr_header_local, 0x26)[0]
            # Parse and store the original padding lengths (we ignore the stored size values).
            original_mipmap_info_local, original_final_padding_local = parse_mipmap_info(
                f, mipmap_count, *struct.unpack_from('>HH', ctxr_header_local, 8)
            )
        image = Image.open(png_file_path)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        r, g, b, a = image.split()
        image_bgra = Image.merge("RGBA", (b, g, r, a))
        main_pixel_data = image_bgra.tobytes("raw", "BGRA")
        width, height = image.size

        ctxr_header_local = bytearray(ctxr_header_local)
        struct.pack_into('>H', ctxr_header_local, 8, width)
        struct.pack_into('>H', ctxr_header_local, 10, height)
        struct.pack_into('>I', ctxr_header_local, 0x80, len(main_pixel_data))
        struct.pack_into('>B', ctxr_header_local, 0x26, mipmap_count)

        new_ctxr_file_path = os.path.join(ctxr_folder_path, file.replace('.png', '.ctxr'))

        new_mipmaps = []
        if mipmap_count > 1 and original_mipmap_info_local:
            mipmaps = [image_bgra]
            curr_w, curr_h = width, height
            for i in range(1, mipmap_count):
                curr_w = max(1, curr_w // 2)
                curr_h = max(1, curr_h // 2)
                mip_image = image_bgra.resize((curr_w, curr_h), Image.LANCZOS)
                mipmaps.append(mip_image)
            for i, mip_image in enumerate(mipmaps[1:]):
                new_data = mip_image.tobytes("raw", "BGRA")
                new_mipmaps.append(new_data)
        else:
            mipmap_count = 1

        with open(new_ctxr_file_path, 'wb') as f:
            f.write(ctxr_header_local)
            f.write(main_pixel_data)
            if mipmap_count > 1:
                for i, new_data in enumerate(new_mipmaps):
                    # Write the original padding exactly.
                    pad = original_mipmap_info_local[i]["padding"]
                    f.write(pad)
                    # Write new size field from new_data length.
                    new_size = len(new_data)
                    f.write(struct.pack('>I', new_size))
                    f.write(new_data)
                f.write(original_final_padding_local)
            else:
                f.write(original_final_padding_local)
        progress["value"] += 1
        app.update_idletasks()

    label.config(text=f"Conversion Completed for folder {png_folder_path}")


def batch_convert_ctxr_to_dds():
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    output_folder_path = filedialog.askdirectory(title="Select a destination folder for DDS files")
    if not folder_path or not output_folder_path:
        return

    dxt5_files = [
        "jngl_happa04_alp_ovl.bmp.ctxr",
        "jngl_happa04_alp_ovl_mip16000.bmp.ctxr",
        "jngl_happa04_alp_ovl_mip16000.bmp_c82c791b86086ed52d483520273e9b5b.ctxr",
        "jngl_happa04_alp_ovl_mip8000.bmp.ctxr",
        "jngl_happa05_alp_ovl_mip4000.bmp.ctxr",
        "jngl_taki_eda_12_alp_ovl_mip8000.bmp.ctxr",
        "jngl_taki_eda_17_alp_ovl_mip4000.bmp.ctxr",
        "s001a_enkeil_rep.bmp.ctxr",
        "s001a_happa05_alp_ovl_mip8000.bmp.ctxr",
        "s001a_soil01_rep_mip8000.bmp.ctxr",
        "v000a_kinokatamari_a01_alp_ovl_rep.bmp.ctxr",
        "v000a_kinokatamari_a01_alp_ovl_rep.bmp_86187137555744c273e17dd4a431d1a2.ctxr",
        "v000a_kinokatamari_a03_alp_ovl_rep.bmp.ctxr",
        "v000a_kinokatamari_a03_alp_ovl_rep.bmp_d9ec09aa2448dfac3e0b72eca57e0034.ctxr",
    ]

    files_to_convert = [f for f in os.listdir(folder_path) if f.endswith('.ctxr')]
    total_files = len(files_to_convert)
    progress["maximum"] = total_files
    progress["value"] = 0

    for file in files_to_convert:
        file_path = os.path.join(folder_path, file)
        try:
            with open(file_path, 'rb') as f:
                ctxr_header_local = f.read(132)
                mipmap_count = struct.unpack_from('>B', ctxr_header_local, 0x26)[0]
                pixel_data_length = struct.unpack_from('>I', ctxr_header_local, 0x80)[0]
                width = struct.unpack_from('>H', ctxr_header_local, 8)[0]
                height = struct.unpack_from('>H', ctxr_header_local, 10)[0]
                pixel_data = f.read(pixel_data_length)
                mipmaps_data = []
                if mipmap_count > 1:
                    mipmaps_data, final_pad = parse_mipmap_info(f, mipmap_count, width, height)
                else:
                    print("No mipmaps present; single level CTXR.")
            image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
            r, g, b, a = image_bgra.split()
            image_rgba = Image.merge("RGBA", (b, g, r, a))
            mipmaps = [image_rgba]
            curr_w, curr_h = width, height
            for i in range(1, mipmap_count):
                curr_w = max(1, curr_w // 2)
                curr_h = max(1, curr_h // 2)
                mip_image = image_rgba.resize((curr_w, curr_h), Image.LANCZOS)
                mipmaps.append(mip_image)

            dds_header_file = "DDS_header.bin"
            if file in dxt5_files:
                dds_header_file = "DDS_header_DXT5.bin"

            with open(dds_header_file, "rb") as header_file:
                dds_header = bytearray(header_file.read())

            struct.pack_into("<I", dds_header, 12, height)
            struct.pack_into("<I", dds_header, 16, width)
            struct.pack_into("<I", dds_header, 28, mipmap_count)

            dds_file_path = os.path.join(output_folder_path, file.replace('.ctxr', '.dds'))
            with open(dds_file_path, "wb") as dds_file:
                dds_file.write(dds_header)
                for mip_image in mipmaps:
                    mip_data = mip_image.tobytes("raw", "BGRA")
                    if len(mip_data) % 4 != 0:
                        mip_data += b'\x00' * (4 - (len(mip_data) % 4))
                    dds_file.write(mip_data)
            progress["value"] += 1
            app.update_idletasks()
        except Exception as e:
            print(f"Failed to convert {file}: {e}")
    label.config(text=f"Conversion Completed for folder {folder_path}")


def batch_convert():
    func_map = {
        'ctxr to png': batch_convert_ctxr_to_png,
        'png to ctxr': batch_convert_png_to_ctxr,
        'ctxr to dds': batch_convert_ctxr_to_dds,
        'dds to ctxr': batch_convert_dds_to_ctxr,
    }
    func_map[chosen_batch_format.get()]()


# Initialize main application window
app = tk.Tk()
app.title("CTXR Converter 1.6 by 316austin316")
app.geometry("700x600")

icon_path = "resources/face.PNG"
image_icon = Image.open(icon_path)
photo_icon = ImageTk.PhotoImage(image_icon)
app.iconphoto(False, photo_icon)

label_image = Label(app, image=photo_icon)
label_image.pack(pady=5)

label = Label(app, text="Kept you waiting huh?")
label.pack(pady=5)

progress = ttk.Progressbar(app, orient="horizontal", length=300, mode="determinate")
progress.pack(pady=20)

main_frame = Frame(app)
main_frame.pack(pady=10, padx=10, fill='both', expand=True)

notebook = ttk.Notebook(main_frame)
notebook.pack(fill='both', expand=True)

general_frame = Frame(notebook)
notebook.add(general_frame, text='PC')

title = Label(general_frame, text="CTXR Converter", font=("Arial", 16, "bold"))
title.grid(row=0, column=0, columnspan=2, pady=10)

description = Label(general_frame, text="For MGS2/3HD \nCode by 316austin316", font=("Arial", 10))
description.grid(row=1, column=0, columnspan=2, pady=10)

open_button = Button(general_frame, text="Open CTXR File", command=open_file, bg='#4CAF50', fg='white', font=("Arial", 10, "bold"))
open_button.grid(row=2, column=0, pady=10, padx=5, sticky="ew")

save_button = Button(general_frame, text="Save as CTXR", command=save_as_ctxr, bg='#FF9800', fg='white', font=("Arial", 10, "bold"))
save_button.grid(row=2, column=1, pady=10, padx=5, sticky="ew")

format_options = ["png", "tga", "dds"]
chosen_format = StringVar(value=format_options[0])
format_dropdown = OptionMenu(general_frame, chosen_format, *format_options)
format_dropdown.grid(row=3, column=0, pady=10, padx=5, sticky="ew")

batch_format_options = ["ctxr to png", "png to ctxr", "ctxr to dds", "dds to ctxr"]
chosen_batch_format = StringVar(value=batch_format_options[0])
batch_format_dropdown = OptionMenu(general_frame, chosen_batch_format, *batch_format_options)
batch_format_dropdown.grid(row=4, column=0, pady=10, padx=5, sticky="ew")

batch_convert_button = Button(general_frame, text="Batch Convert", command=batch_convert, bg='#2196F3', fg='white', font=("Arial", 10, "bold"))
batch_convert_button.grid(row=4, column=1, pady=10, padx=5, sticky="ew")

for i in range(5):
    general_frame.grid_rowconfigure(i, weight=1)
for i in range(2):
    general_frame.grid_columnconfigure(i, weight=1)

ps3_frame = Frame(notebook)
notebook.add(ps3_frame, text='PS3')

ps3_button = Button(ps3_frame, text="Convert PS3 CTXR to DDS", command=convert_ps3_ctxr_to_dds, bg='#9C27B0', fg='white', font=("Arial", 10, "bold"))
ps3_button.pack(pady=20, padx=20, fill='x')

ps3_batch_button = Button(ps3_frame, text="Batch Convert PS3 CTXR to DDS", command=batch_convert_ps3_ctxr_to_dds, bg='#673AB7', fg='white', font=("Arial", 10, "bold"))
ps3_batch_button.pack(pady=10, padx=20, fill='x')

app.mainloop()
