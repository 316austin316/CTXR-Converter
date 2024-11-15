import tkinter as tk
from tkinter import ttk
from tkinter import Label, Button, OptionMenu, StringVar, Frame, filedialog, messagebox
from PIL import Image, ImageTk
import struct
import os
import numpy as np
import ps3_ctxr_module
from ps3_ctxr_module import convert_ps3_ctxr_to_dds, batch_convert_ps3_ctxr_to_dds

global label


ctxr_header = None

def open_file():
    global ctxr_header
    # List of specific files that require a different DDS header
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
        # ... (include all the specific file names here)
    ]

    file_path = filedialog.askopenfilename(title="Select a CTXR file", filetypes=[("CTXR files", "*.ctxr")])
    if not file_path:
        return

    with open(file_path, 'rb') as file:
        ctxr_header = file.read(132)
        mipmap_count = struct.unpack_from('>B', ctxr_header, 0x26)[0]
        pixel_length_value = ctxr_header[128:132]
        pixel_data_length = struct.unpack_from('>I', ctxr_header, 0x80)[0]
        pixel_data = file.read(pixel_data_length)
        width = struct.unpack_from('>H', ctxr_header, 8)[0]
        height = struct.unpack_from('>H', ctxr_header, 10)[0]
        print(f"Number of mipmaps: {mipmap_count} (found at offset 0x26)")
        print(f"Pixel data length: {pixel_data_length} (found at offset 0x80)")
        print(f"{width} and {height} found at offsets 0x8 and 0xA respectively")
        
        # Load image from pixel data
        image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
        r, g, b, a = image_bgra.split()
        image_rgba = Image.merge("RGBA", (b, g, r, a))
        
    
    output_file_path = file_path.replace('.ctxr', f'.{chosen_format.get()}')
    
    # Generate mipmaps and store them in a list
    mipmaps = [image_rgba]
    mipmap_count = 1
    while mipmaps[-1].width > 1 or mipmaps[-1].height > 1:
        # Reduce the image size by half for each mipmap level
        mip_image = mipmaps[-1].resize(
            (max(1, mipmaps[-1].width // 2), max(1, mipmaps[-1].height // 2)),
            Image.BILINEAR  # Use BILINEAR filter to reduce scaling artifacts
        )
        mipmaps.append(mip_image)
        mipmap_count += 1
        print(f"Generated mipmap level {mipmap_count}: {mip_image.width}x{mip_image.height}")


    
    if chosen_format.get() == "tga":
        # Constructing the TGA header
        tga_header = bytearray(18)
        tga_header[2] = 2  # Uncompressed True-color Image
        tga_header[12] = width & 0xFF  # Width - lower byte
        tga_header[13] = (width >> 8) & 0xFF  # Width - higher byte
        tga_header[14] = height & 0xFF  # Height - lower byte
        tga_header[15] = (height >> 8) & 0xFF  # Height - higher byte
        tga_header[16] = 32  # Bits per pixel
        tga_header[17] = 32  # 32 bits alpha

        # Footer to be added to the end of the TGA files
        tga_footer = bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01")

        with open(output_file_path, 'wb') as f:
            f.write(tga_header)
            f.write(pixel_length_value)
            f.write(pixel_data)
            f.write(tga_footer)
    elif chosen_format.get() == "dds":
        # Determine which DDS header to use
        dds_header_file = "DDS_header.bin"
        if os.path.basename(file_path) in dxt5_files:
            dds_header_file = "DDS_header_DXT5.bin"

        # Read the appropriate DDS header template
        with open(dds_header_file, "rb") as header_file:
            dds_header = bytearray(header_file.read())

        # Update DDS header
        struct.pack_into("<I", dds_header, 12, height)
        struct.pack_into("<I", dds_header, 16, width)
        struct.pack_into("<I", dds_header, 28, mipmap_count)

        # Save as DDS with generated mipmaps
        with open(output_file_path, "wb") as dds_file:
            dds_file.write(dds_header)
            for mip_image in mipmaps:
                # Convert each mipmap level to raw BGRA bytes and write to the file
                mip_data = mip_image.tobytes("raw", "BGRA")
                 # Ensure padding to 4-byte boundary for each mipmap level
                if len(mip_data) % 4 != 0:
                    mip_data += b'\x00' * (4 - (len(mip_data) % 4))
                dds_file.write(mip_data)
    else:
        image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
        r, g, b, a = image_bgra.split()
        image_rgba = Image.merge("RGBA", (b, g, r, a))
        image_rgba.save(output_file_path, chosen_format.get().upper(), compress_level=0)

    label.config(text=f"File saved as {output_file_path}")
    






def save_as_ctxr():
    global ctxr_header
    

    if not ctxr_header:
        label.config(text="Please open a CTXR file first.")
        return

    # Update file dialog to show all supported formats
    file_path = filedialog.askopenfilename(
        title="Select an image file",
        filetypes=[("All Supported Formats", "*.tga;*.dds;*.png;*.TGA;*.DDS;*.PNG"),
                   ("TGA files", "*.tga;*.TGA"),
                   ("DDS files", "*.dds;*.DDS"),
                   ("PNG files", "*.png;*.PNG")]
    )
    if not file_path:
        return

    file_extension = os.path.splitext(file_path)[1].lower() 

    if file_extension == ".tga" or file_extension == ".png":
        if file_extension == ".tga":
            # Handle TGA files
            with open(file_path, 'rb') as f:
                tga_header = f.read(18)
                width = struct.unpack_from('<H', tga_header, 12)[0]
                height = struct.unpack_from('<H', tga_header, 14)[0]
                bits_per_pixel = tga_header[16]
                if bits_per_pixel != 32:
                    label.config(text="Only 32-bit TGA files are supported.")
                    return
                f.seek(18 + 4)
                pixel_data = f.read(width * height * 4)
        else:
            # Handle PNG files
            image = Image.open(file_path)
            if image.mode != "RGBA":
                image = image.convert("RGBA")
            r, g, b, a = image.split()
            image_bgra = Image.merge("RGBA", (b, g, r, a))
            pixel_data = image_bgra.tobytes()
            width, height = image.size

        mipmap_count = 1  # Assuming no mipmaps for PNG/TGA

    elif file_extension == ".dds":
        # Handle DDS files
        with open(file_path, 'rb') as f:
            dds_header = f.read(128)
            height = struct.unpack_from('<I', dds_header, 12)[0]
            width = struct.unpack_from('<I', dds_header, 16)[0]
            mipmap_count = struct.unpack_from('<I', dds_header, 28)[0]
            pixel_data = f.read()  # This includes main pixel data and all mipmaps

    else:
        label.config(text="Unsupported file format.")
        return

    ctxr_header = bytearray(ctxr_header)
    struct.pack_into('>H', ctxr_header, 8, width)
    struct.pack_into('>H', ctxr_header, 10, height)
    total_data_length = len(pixel_data)  # Including 28 bytes padding for all formats
    struct.pack_into('>I', ctxr_header, 0x80, total_data_length)
    struct.pack_into('>B', ctxr_header, 0x26, mipmap_count)

    ctxr_file_path = file_path.rsplit('.', 1)[0] + '.ctxr'
    with open(ctxr_file_path, 'wb') as file:
        file.write(ctxr_header)
        file.write(pixel_data)
        file.write(b'\x00' * 28)  # Padding after the pixel data for all formats

    label.config(text=f"File saved as {ctxr_file_path}")






    
def batch_convert_ctxr_to_png():
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    if not folder_path:
        return

    files_to_convert = [f for f in os.listdir(folder_path) if f.endswith('.ctxr')]
    total_files = len(files_to_convert)
    progress["maximum"] = total_files
    progress["value"] = 0

    failed_files = []  # List to keep track of files that caused errors

    for file in files_to_convert:
        file_path = os.path.join(folder_path, file)
        try:
            with open(file_path, 'rb') as f:
                ctxr_header = f.read(132)
                pixel_data_length = struct.unpack_from('>I', ctxr_header, 0x80)[0]
                pixel_data = f.read(pixel_data_length)

                width = struct.unpack_from('>H', ctxr_header, 8)[0]
                height = struct.unpack_from('>H', ctxr_header, 10)[0]
                mipmap_data = struct.unpack_from('>B', ctxr_header, 0x26)[0]

            image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)

            r, g, b, a = image_bgra.split()
            image_rgba = Image.merge("RGBA", (b, g, r, a))

            png_file_path = file_path.replace('.ctxr', '.png')
            image_rgba.save(png_file_path, 'PNG', compress_level=0)

            progress["value"] += 1
            app.update_idletasks()
            
        except Exception as e:
            failed_files.append((file, str(e)))

    if failed_files:
        error_messages = "\n".join([f"Error with {f[0]}: {f[1]}" for f in failed_files])
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
            continue  # Skip if matching CTXR file doesn't exist

        with open(ctxr_file_path, 'rb') as f:
            ctxr_header = f.read(132)

        image = Image.open(png_file_path)

        if image.mode != "RGBA":
            image = image.convert("RGBA")

        r, g, b, a = image.split()
        image_bgra = Image.merge("RGBA", (b, g, r, a))

        new_ctxr_file_path = os.path.join(ctxr_folder_path, os.path.basename(png_file_path).replace('.png', '.ctxr'))
        with open(new_ctxr_file_path, 'wb') as f:
            ctxr_header = bytearray(ctxr_header)
            struct.pack_into('>H', ctxr_header, 8, image.width)
            struct.pack_into('>H', ctxr_header, 10, image.height)
            struct.pack_into('>I', ctxr_header, 0x80, len(image_bgra.tobytes()))  # Including padding only
            struct.pack_into('>B', ctxr_header, 0x26, 1)
            f.write(ctxr_header)
            f.write(image_bgra.tobytes())
            f.write(b'\x00' * 28)  # Padding

        progress["value"] += 1
        app.update_idletasks()

    label.config(text=f"Conversion Completed for folder {png_folder_path}")

def batch_convert_ctxr_to_dds():
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    output_folder_path = filedialog.askdirectory(title="Select a destination folder for DDS files")
    if not folder_path or not output_folder_path:
        return
    
    # List of specific files that require a different DDS header
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
        # ... (include all the specific file names here)
    ]

    files_to_convert = [f for f in os.listdir(folder_path) if f.endswith('.ctxr')]
    total_files = len(files_to_convert)
    progress["maximum"] = total_files
    progress["value"] = 0

    for file in files_to_convert:
        file_path = os.path.join(folder_path, file)
        try:
            with open(file_path, 'rb') as f:
                ctxr_header = f.read(132)
                width = struct.unpack_from('>H', ctxr_header, 8)[0]
                height = struct.unpack_from('>H', ctxr_header, 10)[0]
                pixel_data = f.read()
                
            # Determine which DDS header to use
            dds_header_file = "DDS_header.bin"
            if file in dxt5_files:
                dds_header_file = "DDS_header_DXT5.bin"

            # Read the appropriate DDS header template
            with open(dds_header_file, "rb") as header_file:
                dds_header = bytearray(header_file.read())

            # Update DDS header
            struct.pack_into("<I", dds_header, 12, height)
            struct.pack_into("<I", dds_header, 16, width)

            # Save as DDS
            dds_file_path = os.path.join(output_folder_path, file.replace('.ctxr', '.dds'))
            with open(dds_file_path, "wb") as dds_file:
                dds_file.write(dds_header)
                dds_file.write(pixel_data)


            progress["value"] += 1
            app.update_idletasks()
        except Exception as e:
            print(f"Failed to convert {file}: {e}")

    label.config(text=f"Conversion Completed for folder {folder_path}")
    
def batch_convert_dds_to_ctxr():
    dds_folder_path = filedialog.askdirectory(title="Select a folder with DDS files")
    ctxr_folder_path = filedialog.askdirectory(title="Select a destination folder for CTXR files")

    if not dds_folder_path or not ctxr_folder_path:
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
        # ... (include all the specific file names here)
    ]

    files_to_convert = [f for f in os.listdir(dds_folder_path) if f.lower().endswith('.dds')]
    total_files = len(files_to_convert)
    progress["maximum"] = total_files
    progress["value"] = 0

    for file in files_to_convert:
        dds_file_path = os.path.join(dds_folder_path, file)
        ctxr_file_path = os.path.join(ctxr_folder_path, file.replace('.dds', '.ctxr'))

        try:
            with open(dds_file_path, 'rb') as f:
                # Read DDS header and extract width, height, etc.
                dds_header = f.read(128)
                height = struct.unpack_from('<I', dds_header, 12)[0]
                width = struct.unpack_from('<I', dds_header, 16)[0]
                mipmap_count = struct.unpack_from('<I', dds_header, 28)[0]
                dds_data = f.read()  # Read the rest of the file

            ctxr_header = bytearray(132)
            struct.pack_into('>H', ctxr_header, 8, width)
            struct.pack_into('>H', ctxr_header, 10, height)
            struct.pack_into('>I', ctxr_header, 0x80, len(dds_data) + 28)
            struct.pack_into('>B', ctxr_header, 0x26, mipmap_count)

            # Save CTXR file
            with open(ctxr_file_path, 'wb') as f:
                f.write(ctxr_header)
                f.write(dds_data)
                f.write(b'\x00' * 28)  # Padding

            progress["value"] += 1
            app.update_idletasks()
        except Exception as e:
            print(f"Failed to convert {file}: {e}")

    label.config(text=f"Conversion Completed for folder {ctxr_folder_path}")

    

def batch_convert():
    input_format = chosen_batch_format.get().split(' to ')[0]
    output_format = chosen_batch_format.get().split(' to ')[1]
    
    # Define function mapping
    func_map = {
        'ctxr to png': batch_convert_ctxr_to_png,
        'png to ctxr': batch_convert_png_to_ctxr,
        'ctxr to dds': batch_convert_ctxr_to_dds,
        'dds to ctxr': batch_convert_dds_to_ctxr,
    }

    # Call the relevant function
    func_map[chosen_batch_format.get()]()

# Initialize the main application window
app = tk.Tk()
app.title("CTXR Converter 1.6 by 316austin316")
app.geometry("700x600")

# Set the application icon
#icon_path = "resources/face.PNG"
#image_icon = Image.open(icon_path)
#photo_icon = ImageTk.PhotoImage(image_icon)
#app.iconphoto(False, photo_icon)

# Create and pack the main image label
#label_image = Label(app, image=photo_icon)
#label_image.pack(pady=5)

# Create and pack the waiting label
label = Label(app, text="Kept you waiting huh?")
label.pack(pady=5)

# Initialize progress bar
progress = ttk.Progressbar(app, orient="horizontal", length=300, mode="determinate")
progress.pack(pady=20)

# Create the main frame
main_frame = Frame(app)
main_frame.pack(pady=10, padx=10, fill='both', expand=True)

# Create the Notebook (tabbed interface)
notebook = ttk.Notebook(main_frame)
notebook.pack(fill='both', expand=True)

# ----- General Conversion Tab -----
general_frame = Frame(notebook)
notebook.add(general_frame, text='PC')

# Title and Description
title = Label(general_frame, text="CTXR Converter", font=("Arial", 16, "bold"))
title.grid(row=0, column=0, columnspan=2, pady=10)

description = Label(general_frame, text="For MGS2/3HD \nCode by 316austin316", font=("Arial", 10))
description.grid(row=1, column=0, columnspan=2, pady=10)

# Open and Save Buttons
open_button = Button(general_frame, text="Open CTXR File", command=open_file, bg='#4CAF50', fg='white', font=("Arial", 10, "bold"))
open_button.grid(row=2, column=0, pady=10, padx=5, sticky="ew")

save_button = Button(general_frame, text="Save as CTXR", command=save_as_ctxr, bg='#FF9800', fg='white', font=("Arial", 10, "bold"))
save_button.grid(row=2, column=1, pady=10, padx=5, sticky="ew")

# Dropdown for individual conversion format choice
format_options = ["png", "tga", "dds"] 
chosen_format = StringVar(value=format_options[0])  # set default value
format_dropdown = OptionMenu(general_frame, chosen_format, *format_options)
format_dropdown.grid(row=3, column=0, pady=10, padx=5, sticky="ew")

# Dropdown for batch conversion format choice
batch_format_options = ["ctxr to png", "png to ctxr", "ctxr to dds", "dds to ctxr"]
chosen_batch_format = StringVar(value=batch_format_options[0])
batch_format_dropdown = OptionMenu(general_frame, chosen_batch_format, *batch_format_options)
batch_format_dropdown.grid(row=4, column=0, pady=10, padx=5, sticky="ew")

# Button for batch conversion
batch_convert_button = Button(general_frame, text="Batch Convert", command=batch_convert, bg='#2196F3', fg='white', font=("Arial", 10, "bold"))
batch_convert_button.grid(row=4, column=1, pady=10, padx=5, sticky="ew")

# Configure grid weights for responsiveness
for i in range(5):
    general_frame.grid_rowconfigure(i, weight=1)
for i in range(2):
    general_frame.grid_columnconfigure(i, weight=1)

# ----- PS3 Conversion Tab -----
ps3_frame = Frame(notebook)
notebook.add(ps3_frame, text='PS3')

# PS3 Specific Conversion Button
ps3_button = Button(ps3_frame, text="Convert PS3 CTXR to DDS", command=convert_ps3_ctxr_to_dds, bg='#9C27B0', fg='white', font=("Arial", 10, "bold"))
ps3_button.pack(pady=20, padx=20, fill='x')

# PS3 Batch Conversion Button
ps3_batch_button = Button(ps3_frame, text="Batch Convert PS3 CTXR to DDS", command=batch_convert_ps3_ctxr_to_dds, bg='#673AB7', fg='white', font=("Arial", 10, "bold"))

ps3_batch_button.pack(pady=10, padx=20, fill='x')

# Add more PS3-specific widgets here if needed

# Start the main event loop
app.mainloop()