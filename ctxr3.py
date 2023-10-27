from tkinter import Tk, filedialog, Button, Label, Frame, StringVar, OptionMenu, ttk
from PIL import Image, ImageTk
import struct
import os
import imageio

ctxr_header = None

def open_file():
    global ctxr_header

    file_path = filedialog.askopenfilename(title="Select a CTXR file", filetypes=[("CTXR files", "*.ctxr")])
    if not file_path:
        return

    with open(file_path, 'rb') as file:
        ctxr_header = file.read(132)
        pixel_length_value = ctxr_header[128:132]  # Extracting the pixel length value from CTXR header
        pixel_data_length = struct.unpack_from('>I', ctxr_header, 0x80)[0]
        pixel_data = file.read(pixel_data_length)
    
        width = struct.unpack_from('>H', ctxr_header, 8)[0]
        height = struct.unpack_from('>H', ctxr_header, 10)[0]
    
    output_file_path = file_path.replace('.ctxr', f'.{chosen_format.get()}')

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

    file_path = filedialog.askopenfilename(title="Select an image file", filetypes=[("TGA files", "*.tga"), ("PNG files", "*.png")])
    if not file_path:
        return

    if file_path.endswith(".tga"):
        with open(file_path, 'rb') as f:
            tga_header = f.read(18)
            width = struct.unpack_from('<H', tga_header, 12)[0]
            height = struct.unpack_from('<H', tga_header, 14)[0]
            bits_per_pixel = tga_header[16]
            
            if bits_per_pixel != 32:
                label.config(text="Only 32-bit TGA files are supported.")
                return
            
            # Skip the pixel length value in TGA
            f.seek(18 + 4)
            pixel_data = f.read(width * height * 4)

    elif file_path.endswith(".png"):
        image = Image.open(file_path)
        if image.mode != "RGBA":
            # Add an alpha channel if it doesn't have one
            image = image.convert("RGBA")

        r, g, b, a = image.split()
        image_bgra = Image.merge("RGBA", (b, g, r, a))
        pixel_data = image_bgra.tobytes()
        width, height = image.size

    else:
        label.config(text="Unsupported file format.")
        return

    ctxr_header = bytearray(ctxr_header)
    struct.pack_into('>H', ctxr_header, 8, width)
    struct.pack_into('>H', ctxr_header, 10, height)
    struct.pack_into('>I', ctxr_header, 0x80, len(pixel_data))  # Accounting for pixel data size
    struct.pack_into('>B', ctxr_header, 0x26, 1)
    
    ctxr_file_path = file_path.rsplit('.', 1)[0] + '.ctxr'
    
    with open(ctxr_file_path, 'wb') as file:
        file.write(ctxr_header)
        file.write(pixel_data)
        file.write(b'\x00' * 28)  # Padding

    label.config(text=f"File saved as {ctxr_file_path}")





    
def batch_convert_ctxr_to_png():
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    if not folder_path:
        return

    files_to_convert = [f for f in os.listdir(folder_path) if f.endswith('.ctxr')]
    total_files = len(files_to_convert)
    progress["maximum"] = total_files
    progress["value"] = 0

    for file in files_to_convert:
        file_path = os.path.join(folder_path, file)
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

    label.config(text=f"Conversion Completed for folder {folder_path}")


    

    
def batch_convert_png_to_ctxr():
    png_folder_path = filedialog.askdirectory(title="Select a folder with PNG files")
    ctxr_folder_path = filedialog.askdirectory(title="Select a folder with original CTXR files for headers")

    if not png_folder_path or not ctxr_folder_path:
        return

    files_to_convert = [f for f in os.listdir(png_folder_path) if f.endswith('.png')]
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

        new_ctxr_file_path = png_file_path.replace('.png', '_new.ctxr')
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


    

def batch_convert():
    input_format = chosen_batch_format.get().split(' to ')[0]
    output_format = chosen_batch_format.get().split(' to ')[1]
    
    # Define function mapping
    func_map = {
        'ctxr to png': batch_convert_ctxr_to_png,
        'png to ctxr': batch_convert_png_to_ctxr,
    }

    # Call the relevant function
    func_map[chosen_batch_format.get()]()

app = Tk()
app.title("CTXR Converter by 316austin316")
app.geometry("700x500")

progress = ttk.Progressbar(app, orient="horizontal", length=300, mode="determinate")
progress.pack(pady=20)

icon_path = "resources/face.png"
image_icon = Image.open(icon_path)
photo_icon = ImageTk.PhotoImage(image_icon)
app.iconphoto(False, photo_icon)

label_image = Label(app, image=photo_icon)
label_image.pack(pady=5)

label = Label(app, text="Kept you waiting huh?")
label.pack(pady=5)


chosen_format = StringVar()
chosen_batch_format = StringVar()

frame = Frame(app)
frame.pack(pady=10, padx=10)

title = Label(frame, text="CTXR <-> PNG Converter", font=("Arial", 16, "bold"))
title.grid(row=0, column=0, columnspan=2, pady=10)

description = Label(frame, text="For MGS3HD PC\nCode by 316austin316", font=("Arial", 10))
description.grid(row=1, column=0, columnspan=2, pady=10)

open_button = Button(frame, text="Open CTXR File", command=open_file, bg='#4CAF50', fg='white', font=("Arial", 10, "bold"))
open_button.grid(row=2, column=0, pady=10, sticky="ew")

save_button = Button(frame, text="Save as CTXR", command=save_as_ctxr, bg='#FF9800', fg='white', font=("Arial", 10, "bold"))
save_button.grid(row=2, column=1, pady=10, sticky="ew")

# Dropdown for PNG choice for individual conversion
format_options = ["png", "tga"] 
chosen_format.set(format_options[0])  # set default value
format_dropdown = OptionMenu(frame, chosen_format, *format_options)
format_dropdown.grid(row=3, column=0, pady=10)

# Dropdown for batch conversion format choice
batch_format_options = ["ctxr to png", "png to ctxr"]
chosen_batch_format.set(batch_format_options[0])
batch_format_dropdown = OptionMenu(frame, chosen_batch_format, *batch_format_options)
batch_format_dropdown.grid(row=4, column=0, pady=10)

# Button for batch conversion
batch_convert_button = Button(frame, text="Batch Convert", command=batch_convert, bg='#2196F3', fg='white', font=("Arial", 10, "bold"))
batch_convert_button.grid(row=4, column=1, pady=10, sticky="ew")


app.mainloop()
