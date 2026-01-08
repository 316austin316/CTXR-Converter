import tkinter as tk
from tkinter import ttk
from tkinter import Label, Button, OptionMenu, StringVar, Frame, filedialog, messagebox
from PIL import Image, ImageTk
import struct
import os
import numpy as np
import ps3_ctxr_module
from ps3_ctxr_module import convert_ps3_ctxr_to_dds, batch_convert_ps3_ctxr_to_dds
import logging
import traceback
from datetime import datetime
from image_viewer import ImageViewer
from ctxr_utils import parse_mipmap_info, CTXRError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ctxr_converter.log'),
        logging.StreamHandler()
    ]
)

# Global variables to store the original header and complete mipmap info
global label, ctxr_header, original_mipmap_info, original_final_padding
ctxr_header = None
original_mipmap_info = []      # List of dicts: for each mipmap level: {"padding": bytes, "size": int, "data": bytes}
original_final_padding = b""  # Final padding after the last mipmap





def save_as_tga(image, file_path):
    """Save image as TGA format with proper header"""
    width, height = image.size
    
    # TGA header (18 bytes)
    header = bytearray(18)
    header[0] = 0  # ID length
    header[1] = 0  # Color map type
    header[2] = 2  # Image type (uncompressed RGB)
    header[3:5] = struct.pack('<H', 0)  # Color map offset
    header[5] = 0  # Color map length
    header[7] = 32  # Color map depth
    header[8:10] = struct.pack('<H', 0)  # X origin
    header[10:12] = struct.pack('<H', 0)  # Y origin
    header[12:14] = struct.pack('<H', width)  # Width
    header[14:16] = struct.pack('<H', height)  # Height
    header[16] = 32  # Bits per pixel
    header[17] = 0x20  # Image descriptor (top-left origin)
    
    # TGA format expects BGRA data
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    # Convert RGBA to BGRA for TGA format
    r, g, b, a = image.split()
    image_bgra = Image.merge("RGBA", (b, g, r, a))
    
    with open(file_path, 'wb') as f:
        f.write(header)
        f.write(image_bgra.tobytes())


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
        "s001a_enkei1_rep.bmp.ctxr",
        "v000a_kinokatamari_a01_alp_ovl_rep.bmp.ctxr",
        "v000a_kinokatamari_a01_alp_ovl_rep.bmp_86187137555744c273e17dd4a431d1a2.ctxr",
        "v000a_kinokatamari_a02_rep.bmp.ctxr",
        "v000a_kinokatamari_a03_alp_ovl_rep.bmp.ctxr",
        "v000a_kinokatamari_a03_alp_ovl_rep.bmp_d9ec09aa2448dfac3e0b72eca57e0034.ctxr",
    ]

    try:
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
            logging.info(f"Header: {width}x{height} main level, pixel data length: {pixel_data_length}")
            logging.info(f"Mipmap count from header: {mipmap_count}")

            if mipmap_count > 1:
                # Check if this file is DXT5 compressed based on filename
                filename = os.path.basename(file_path)
                is_compressed = filename in dxt5_files
                compression_format = 'DXT5' if is_compressed else 'UNCOMPRESSED'
                logging.info(f"File format: {compression_format}")
                
                original_mipmap_info, original_final_padding = parse_mipmap_info(
                    file_obj, mipmap_count, width, height, 
                    is_compressed=is_compressed, 
                    compression_format=compression_format
                )
            else:
                original_mipmap_info = []
                original_final_padding = b""

        # Check if this is a DXT5 file
        filename = os.path.basename(file_path)
        is_dxt5 = filename in dxt5_files
        
        if is_dxt5 and chosen_format.get() != "dds":
            messagebox.showinfo("DXT5 File", "This is a DXT5 compressed file. Only DDS output is supported.\nPlease select DDS format and try again.")
            label.config(text="DXT5 files can only be converted to DDS")
            return
        
        # Simple conversion: BGRA to RGBA for display/export
        # For DXT5 files, pixel_data is compressed, so we handle it differently
        if is_dxt5:
            # Don't try to create an image from compressed data
            # We'll write directly to DDS below
            image_rgba = None
            logging.info("DXT5 compressed file - will write directly to DDS")
        else:
            # PIL interprets BGRA bytes as RGBA, so we need to swap R and B
            image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
            r, g, b, a = image_bgra.split()
            image_rgba = Image.merge("RGBA", (b, g, r, a))
        output_file_path = file_path.replace('.ctxr', f'.{chosen_format.get()}')

        if chosen_format.get() == "dds":
            # For DXT5 files, write compressed data directly
            # For uncompressed files, generate mipmaps
            if is_dxt5:
                # DXT5 - write compressed data directly
                dds_header_file = "DDS_header_DXT5.bin"
                with open(dds_header_file, "rb") as header_file:
                    dds_header = bytearray(header_file.read())
                
                # --- FIX: Calculate accurate Linear Size for Photoshop ---
                # DXT5 uses 16 bytes per 4x4 block
                width_blocks = max(1, (width + 3) // 4)
                height_blocks = max(1, (height + 3) // 4)
                linear_size = width_blocks * height_blocks * 16
                # ---------------------------------------------------------

                # --- FIX: PAD MAIN PIXEL DATA ---
                # Ensure main data matches linear_size exactly
                if len(pixel_data) < linear_size:
                    padding_needed = linear_size - len(pixel_data)
                    logging.info(f"Padding main image with {padding_needed} bytes")
                    pixel_data += b'\x00' * padding_needed
                # --------------------------------

                # Write Dimensions and Size
                struct.pack_into("<I", dds_header, 12, height)
                struct.pack_into("<I", dds_header, 16, width)
                struct.pack_into("<I", dds_header, 20, linear_size)  # Offset 20 is Pitch/LinearSize
                struct.pack_into("<I", dds_header, 28, mipmap_count)
                
                # --- FIX: STRICT FLAGS FOR PHOTOSHOP ---
                # Standard Flags: CAPS (1) | HEIGHT (2) | WIDTH (4) | PIXELFORMAT (0x1000) | LINEARSIZE (0x80000)
                required_flags = 0x81007 
                
                # Standard Caps: TEXTURE (0x1000)
                required_caps = 0x1000

                if mipmap_count > 1:
                    required_flags |= 0x20000   # Add MIPMAPCOUNT flag
                    required_caps |= 0x400008   # Add COMPLEX (8) and MIPMAP (0x400000) caps

                # Force write the flags (Do not use OR | with existing, overwrite them to be safe)
                struct.pack_into("<I", dds_header, 8, required_flags)
                struct.pack_into("<I", dds_header, 104, required_caps)
                # ----------------------------------------
                
                with open(output_file_path, "wb") as dds_file:
                    dds_file.write(dds_header)
                    # Write main level compressed data
                    dds_file.write(pixel_data)
                    # Write mipmap compressed data with validation
                    if original_mipmap_info:
                        for idx, mip_info in enumerate(original_mipmap_info):
                            mip_level = idx + 1
                            mip_w = max(1, width >> mip_level)
                            mip_h = max(1, height >> mip_level)
                            mip_blocks_w = max(1, (mip_w + 3) // 4)
                            mip_blocks_h = max(1, (mip_h + 3) // 4)
                            expected_mip_size = mip_blocks_w * mip_blocks_h * 16
                            
                            mip_data = mip_info["data"]
                            
                            # Pad mipmap if needed
                            if len(mip_data) < expected_mip_size:
                                padding_needed = expected_mip_size - len(mip_data)
                                logging.warning(f"Mipmap {mip_level} undersized: {len(mip_data)} < {expected_mip_size}, padding {padding_needed} bytes")
                                mip_data += b'\x00' * padding_needed
                            elif len(mip_data) > expected_mip_size:
                                logging.warning(f"Mipmap {mip_level} oversized: {len(mip_data)} > {expected_mip_size}, truncating")
                                mip_data = mip_data[:expected_mip_size]
                            
                            dds_file.write(mip_data)
                logging.info(f"Wrote DXT5 compressed DDS with {mipmap_count} levels")
            else:
                # Uncompressed - generate mipmaps using high-quality Lanczos filtering
                mipmaps = [image_rgba]
                curr_w, curr_h = width, height
                for i in range(1, mipmap_count):
                    curr_w = max(1, curr_w // 2)
                    curr_h = max(1, curr_h // 2)
                    mip_image = image_rgba.resize((curr_w, curr_h), Image.LANCZOS)
                    mipmaps.append(mip_image)
                    logging.info(f"Generated mipmap level {i+1}: {mip_image.width}x{mip_image.height}")
                
                dds_header_file = "DDS_header.bin"
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
        elif chosen_format.get() == "tga":
            save_as_tga(image_rgba, output_file_path)
        else:
            image_rgba.save(output_file_path, chosen_format.get().upper(), compress_level=0)

        if is_dxt5:
            label.config(text=f"DXT5 file saved as {output_file_path} - Use DDS format for DXT5 files")
        else:
            label.config(text=f"File saved as {output_file_path}")
        logging.info(f"Successfully converted {file_path} to {output_file_path}")
        
    except Exception as e:
        error_msg = f"Error processing file: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        messagebox.showerror("Error", error_msg)
        label.config(text="Error occurred during conversion")


def save_as_ctxr():
    global ctxr_header, original_mipmap_info, original_final_padding

    if not ctxr_header:
        label.config(text="Please open a CTXR file first.")
        return

    try:
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
        
        # Check if the original CTXR was DXT5
        original_pixel_data_length = struct.unpack_from('>I', ctxr_header, 0x80)[0]
        
        # If loading a DDS file and original was DXT5, handle specially
        if file_path.lower().endswith('.dds'):
            # Read the DDS file directly to preserve compression
            with open(file_path, 'rb') as dds_file:
                dds_header = dds_file.read(128)  # DDS header is 128 bytes
                
                # Check if it's a DXT5 DDS
                # DXT5 fourCC is at offset 84 in DDS header
                fourcc = dds_header[84:88]
                is_dxt5_dds = (fourcc == b'DXT5')
                
                if is_dxt5_dds:
                    # Read all the compressed data
                    main_pixel_data = dds_file.read(original_pixel_data_length)
                    
                    # Read mipmap data if present
                    new_mipmap_data = []
                    if mipmap_count > 1 and original_mipmap_info:
                        for mip_info in original_mipmap_info:
                            expected_size = len(mip_info["data"])
                            mip_data = dds_file.read(expected_size)
                            new_mipmap_data.append(mip_data)
                    
                    # Get dimensions from DDS header
                    height = struct.unpack_from('<I', dds_header, 12)[0]
                    width = struct.unpack_from('<I', dds_header, 16)[0]
                    
                    total_data_length = len(main_pixel_data)
                    
                    # Update header with dimensions and data length
                    ctxr_header = bytearray(ctxr_header)
                    struct.pack_into('>H', ctxr_header, 8, width)
                    struct.pack_into('>H', ctxr_header, 10, height)
                    struct.pack_into('>I', ctxr_header, 0x80, total_data_length)
                    struct.pack_into('>B', ctxr_header, 0x26, mipmap_count)
                    
                    # Write out the new CTXR file with compressed data
                    ctxr_file_path = file_path.rsplit('.', 1)[0] + '.ctxr'
                    with open(ctxr_file_path, 'wb') as f:
                        f.write(ctxr_header)
                        f.write(main_pixel_data)
                        if mipmap_count > 1:
                            for i, new_data in enumerate(new_mipmap_data):
                                # Write the original padding exactly
                                orig_pad = original_mipmap_info[i]["padding"]
                                f.write(orig_pad)
                                # For DXT5, don't write size field - data is back-to-back
                                # Just write the compressed mipmap data
                                f.write(new_data)
                            # Write the final padding as originally read
                            f.write(original_final_padding)
                        else:
                            f.write(original_final_padding)
                    
                    label.config(text=f"File saved as {ctxr_file_path}")
                    logging.info(f"Successfully saved DXT5 CTXR file: {ctxr_file_path}")
                    return

        # For non-DXT5 or non-DDS files, use the original uncompressed method
        # Open the new image.
        image = Image.open(file_path)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        
        # Simple conversion: RGBA to BGRA for CTXR format
        width, height = image.size
        main_pixel_data = image.tobytes("raw", "BGRA")
        total_data_length = len(main_pixel_data)

        # Generate new mipmap data from the new image.
        new_mipmap_data = []
        if mipmap_count > 1 and original_mipmap_info:
            mipmaps = [image]
            curr_w, curr_h = width, height
            for i in range(1, mipmap_count):
                curr_w = max(1, curr_w // 2)
                curr_h = max(1, curr_h // 2)
                mip_image = image.resize((curr_w, curr_h), Image.LANCZOS)
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
        logging.info(f"Successfully saved CTXR file: {ctxr_file_path}")
        
    except Exception as e:
        error_msg = f"Error saving CTXR file: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        messagebox.showerror("Error", error_msg)
        label.config(text="Error occurred during save")


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
            # Simple conversion: BGRA to RGBA for export
            # PIL interprets BGRA bytes as RGBA, so we need to swap R and B
            image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
            r, g, b, a = image_bgra.split()
            image_rgba = Image.merge("RGBA", (b, g, r, a))
            png_file_path = os.path.join(folder_path, file.replace('.ctxr', '.png'))
            image_rgba.save(png_file_path, 'PNG', compress_level=0)
            progress["value"] += 1
            app.update_idletasks()
        except Exception as e:
            failed_files.append((file, str(e)))
            logging.error(f"Failed to convert {file}: {e}")
    if failed_files:
        error_messages = "\n".join([f"Error with {name}: {err}" for name, err in failed_files])
        label.config(text=f"Conversion Completed with errors:\n{error_messages}")
        messagebox.showwarning("Conversion Errors", f"Some files failed to convert. Check log for details.")
    else:
        label.config(text=f"Conversion Completed for folder {folder_path}")


def batch_convert_ctxr_to_tga():
    """New function for batch converting CTXR to TGA format"""
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
            
            # Simple conversion: BGRA to RGBA for export
            # PIL interprets BGRA bytes as RGBA, so we need to swap R and B
            image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
            r, g, b, a = image_bgra.split()
            image_rgba = Image.merge("RGBA", (b, g, r, a))
            tga_file_path = os.path.join(folder_path, file.replace('.ctxr', '.tga'))
            save_as_tga(image_rgba, tga_file_path)
            progress["value"] += 1
            app.update_idletasks()
            logging.info(f"Converted {file} to TGA")
        except Exception as e:
            failed_files.append((file, str(e)))
            logging.error(f"Failed to convert {file}: {e}")
    
    if failed_files:
        error_messages = "\n".join([f"Error with {name}: {err}" for name, err in failed_files])
        label.config(text=f"TGA Conversion Completed with errors:\n{error_messages}")
        messagebox.showwarning("Conversion Errors", f"Some files failed to convert. Check log for details.")
    else:
        label.config(text=f"TGA Conversion Completed for folder {folder_path}")


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
        # Simple conversion: RGBA to BGRA for CTXR
        image = Image.open(png_file_path)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        main_pixel_data = image.tobytes("raw", "BGRA")
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
        "s001a_enkei1_rep.bmp.ctxr",
        "v000a_kinokatamari_a01_alp_ovl_rep.bmp.ctxr",
        "v000a_kinokatamari_a01_alp_ovl_rep.bmp_86187137555744c273e17dd4a431d1a2.ctxr",
        "v000a_kinokatamari_a02_rep.bmp.ctxr",
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
            # Check if this file is DXT5 compressed based on filename
            is_dxt5 = file in dxt5_files
            
            with open(file_path, 'rb') as f:
                ctxr_header_local = f.read(132)
                mipmap_count = struct.unpack_from('>B', ctxr_header_local, 0x26)[0]
                pixel_data_length = struct.unpack_from('>I', ctxr_header_local, 0x80)[0]
                width = struct.unpack_from('>H', ctxr_header_local, 8)[0]
                height = struct.unpack_from('>H', ctxr_header_local, 10)[0]
                pixel_data = f.read(pixel_data_length)
                mipmaps_data = []
                if mipmap_count > 1:
                    # Check if this file is DXT5 compressed based on filename
                    is_compressed = is_dxt5
                    compression_format = 'DXT5' if is_compressed else 'UNCOMPRESSED'
                    
                    mipmaps_data, final_pad = parse_mipmap_info(
                        f, mipmap_count, width, height,
                        is_compressed=is_compressed,
                        compression_format=compression_format
                    )
                else:
                    logging.info("No mipmaps present; single level CTXR.")
            
            
            
            # Handle DXT5 and uncompressed files differently
            if is_dxt5:
                # DXT5 - write compressed data directly to DDS
                dds_header_file = "DDS_header_DXT5.bin"
                with open(dds_header_file, "rb") as header_file:
                    dds_header = bytearray(header_file.read())
                
                # Calculate Linear Size
                width_blocks = max(1, (width + 3) // 4)
                height_blocks = max(1, (height + 3) // 4)
                linear_size = width_blocks * height_blocks * 16
                
                struct.pack_into("<I", dds_header, 12, height)
                struct.pack_into("<I", dds_header, 16, width)
                struct.pack_into("<I", dds_header, 20, linear_size)
                struct.pack_into("<I", dds_header, 28, mipmap_count)
                
                # FLAGS
                required_flags = 0x81007 
                required_caps = 0x1000

                if mipmap_count > 1:
                    required_flags |= 0x20000
                    required_caps |= 0x400008

                struct.pack_into("<I", dds_header, 8, required_flags)
                struct.pack_into("<I", dds_header, 104, required_caps)
                
                
                # Define the path variable specifically for this function
                dds_file_path = os.path.join(output_folder_path, file.replace('.ctxr', '.dds'))
                
                # USE dds_file_path HERE (Not output_file_path)
                with open(dds_file_path, "wb") as dds_file:
                    dds_file.write(dds_header)
                    
                    # Pad main pixel data if needed
                    if len(pixel_data) < linear_size:
                        padding_needed = linear_size - len(pixel_data)
                        logging.info(f"Padding main image with {padding_needed} bytes")
                        pixel_data += b'\x00' * padding_needed
                    
                    dds_file.write(pixel_data)
                    
                    # Write mipmaps with validation
                    if mipmaps_data:
                        for idx, mip_info in enumerate(mipmaps_data):
                            mip_level = idx + 1
                            mip_w = max(1, width >> mip_level)
                            mip_h = max(1, height >> mip_level)
                            mip_blocks_w = max(1, (mip_w + 3) // 4)
                            mip_blocks_h = max(1, (mip_h + 3) // 4)
                            expected_mip_size = mip_blocks_w * mip_blocks_h * 16
                            
                            mip_data = mip_info["data"]
                            
                            # Pad mipmap if needed
                            if len(mip_data) < expected_mip_size:
                                padding_needed = expected_mip_size - len(mip_data)
                                logging.warning(f"Mipmap {mip_level} undersized: {len(mip_data)} < {expected_mip_size}, padding {padding_needed} bytes")
                                mip_data += b'\x00' * padding_needed
                            elif len(mip_data) > expected_mip_size:
                                logging.warning(f"Mipmap {mip_level} oversized: {len(mip_data)} > {expected_mip_size}, truncating")
                                mip_data = mip_data[:expected_mip_size]
                            
                            dds_file.write(mip_data)
                logging.info(f"Wrote DXT5 compressed DDS: {file}")
            else:
                # Uncompressed - convert BGRA to RGBA and generate mipmaps
                # PIL interprets BGRA bytes as RGBA, so we need to swap R and B
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
            logging.error(f"Failed to convert {file}: {e}")
    label.config(text=f"Conversion Completed for folder {folder_path}")


def batch_convert_dds_to_ctxr():
    """Batch convert DDS files to CTXR format"""
    dds_folder_path = filedialog.askdirectory(title="Select a folder with DDS files")
    template_folder_path = filedialog.askdirectory(title="Select a folder with original CTXR files for headers")
    output_folder_path = filedialog.askdirectory(title="Select a destination folder for CTXR files")
    
    if not dds_folder_path or not template_folder_path or not output_folder_path:
        return
    
    try:
        from dds_module import batch_convert_dds_to_ctxr_enhanced
        success_count, error_files = batch_convert_dds_to_ctxr_enhanced(
            dds_folder_path, output_folder_path, template_folder_path
        )
        
        if error_files:
            error_messages = "\n".join([f"Error with {name}: {err}" for name, err in error_files])
            label.config(text=f"DDS to CTXR conversion completed with {len(error_files)} errors")
            messagebox.showwarning("Conversion Errors", f"Some files failed to convert. Check log for details.")
        else:
            label.config(text=f"DDS to CTXR conversion completed successfully: {success_count} files")
            messagebox.showinfo("Success", f"Successfully converted {success_count} files")
            
    except Exception as e:
        error_msg = f"Batch conversion error: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        messagebox.showerror("Error", error_msg)


def batch_convert():
    func_map = {
        'ctxr to png': batch_convert_ctxr_to_png,
        'ctxr to tga': batch_convert_ctxr_to_tga,
        'png to ctxr': batch_convert_png_to_ctxr,
        'ctxr to dds': batch_convert_ctxr_to_dds,
        'dds to ctxr': batch_convert_dds_to_ctxr,
    }
    try:
        func_map[chosen_batch_format.get()]()
    except KeyError:
        messagebox.showerror("Error", "Selected batch format not implemented yet")
    except Exception as e:
        error_msg = f"Batch conversion error: {str(e)}"
        logging.error(error_msg)
        logging.error(traceback.format_exc())
        messagebox.showerror("Error", error_msg)


# Initialize main application window
app = tk.Tk()
app.title("CTXR Converter 2.0 by 316austin316")
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

# Add info label for DXT5 files
dxt5_info_label = Label(general_frame, text="⚠️ DXT5 files require DDS format", font=("Arial", 8), fg="#FF5722")
dxt5_info_label.grid(row=3, column=1, pady=10, padx=5, sticky="w")

batch_format_options = ["ctxr to png", "ctxr to tga", "png to ctxr", "ctxr to dds", "dds to ctxr"]
chosen_batch_format = StringVar(value=batch_format_options[0])
batch_format_dropdown = OptionMenu(general_frame, chosen_batch_format, *batch_format_options)
batch_format_dropdown.grid(row=4, column=0, pady=10, padx=5, sticky="ew")

batch_convert_button = Button(general_frame, text="Batch Convert", command=batch_convert, bg='#2196F3', fg='white', font=("Arial", 10, "bold"))
batch_convert_button.grid(row=4, column=1, pady=10, padx=5, sticky="ew")

viewer_button = Button(general_frame, text="Open Image Viewer", command=lambda: ImageViewer(app), bg='#FF5722', fg='white', font=("Arial", 10, "bold"))
viewer_button.grid(row=5, column=0, columnspan=2, pady=10, padx=5, sticky="ew")

for i in range(6):
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