from tkinter import Tk, filedialog, Button, Label, Frame, StringVar, OptionMenu
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
        pixel_data = file.read()
    
        width = struct.unpack_from('>H', ctxr_header, 8)[0]
        height = struct.unpack_from('>H', ctxr_header, 10)[0]
    
    image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
    r, g, b, a = image_bgra.split()
    image_rgba = Image.merge("RGBA", (b, g, r, a))
    
    output_file_path = file_path.replace('.ctxr', f'_rgba.{chosen_format.get()}')
    if chosen_format.get() == "dds":
        imageio.imwrite(output_file_path, image_rgba)
    else:
        image_rgba.save(output_file_path, chosen_format.get().upper(), compress_level=0)


    label.config(text=f"File saved as {output_file_path}")


def save_as_ctxr():
    global ctxr_header

    if not ctxr_header:
        label.config(text="Please open a CTXR file first.")
        return

    file_path = filedialog.askopenfilename(title="Select an image file", filetypes=[("Image files", "*.bmp;*.png;*.dds")])
    if not file_path:
        return

    # Handle DDS separately using imageio
    if file_path.endswith('.dds'):
        image_array = imageio.imread(file_path)
        image = Image.fromarray(image_array)
    else:
        image = Image.open(file_path)

    if image.mode != "RGBA":
        # Add an alpha channel if it doesn't have one
        image = image.convert("RGBA")

    r, g, b, a = image.split()
    image_bgra = Image.merge("RGBA", (b, g, r, a))

    # Adjust ctxr_file_path construction to also replace .dds with .ctxr
    ctxr_file_path = file_path.rsplit('.', 1)[0] + '.ctxr'
    
    with open(ctxr_file_path, 'wb') as file:
        file.write(ctxr_header)
        file.write(image_bgra.tobytes())

    label.config(text=f"File saved as {ctxr_file_path}")

    
def batch_convert_ctxr_to_png():
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    if not folder_path:
        return

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.ctxr'):
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    ctxr_header = f.read(132)
                    pixel_data = f.read()
                
                    width = struct.unpack_from('>H', ctxr_header, 8)[0]
                    height = struct.unpack_from('>H', ctxr_header, 10)[0]
                    
                image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)

                r, g, b, a = image_bgra.split()
                image_rgba = Image.merge("RGBA", (b, g, r, a))

                png_file_path = file_path.replace('.ctxr', '.png')
                image_rgba.save(png_file_path, 'PNG', compress_level=0)

    label.config(text=f"Conversion Completed for folder {folder_path}")
    
def batch_convert_ctxr_to_dds():
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    if not folder_path:
        return

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.ctxr'):
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    ctxr_header = f.read(132)
                    pixel_data = f.read()
                    
                    width = struct.unpack_from('>H', ctxr_header, 8)[0]
                    height = struct.unpack_from('>H', ctxr_header, 10)[0]
                
                image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
                r, g, b, a = image_bgra.split()
                image_rgba = Image.merge("RGBA", (b, g, r, a))
                
                dds_file_path = file_path.replace('.ctxr', '.dds')
                imageio.imwrite(dds_file_path, image_rgba)

    label.config(text=f"Conversion Completed for folder {folder_path}")
    
def batch_convert_dds_to_ctxr():
    dds_folder_path = filedialog.askdirectory(title="Select a folder with DDS files")
    ctxr_folder_path = filedialog.askdirectory(title="Select a folder with original CTXR files for headers")
    
    if not dds_folder_path or not ctxr_folder_path:
        return

    for root, dirs, files in os.walk(dds_folder_path):
        for file in files:
            if file.endswith('.dds'):
                dds_file_path = os.path.join(root, file)
                ctxr_file_path = os.path.join(ctxr_folder_path, file.replace('.dds', '.ctxr'))
                
                if not os.path.exists(ctxr_file_path):
                    continue  # Skip if matching CTXR file doesn't exist

                with open(ctxr_file_path, 'rb') as f:
                    ctxr_header = f.read(132)

                image = Image.open(dds_file_path)

                if image.mode != "RGBA":
                    image = image.convert("RGBA")

                r, g, b, a = image.split()
                image_bgra = Image.merge("RGBA", (b, g, r, a))
                


                new_ctxr_file_path = dds_file_path.replace('.dds', '_new.ctxr')
                with open(new_ctxr_file_path, 'wb') as f:
                    f.write(ctxr_header)
                    f.write(image_bgra.tobytes())

    label.config(text=f"Conversion Completed for folder {dds_folder_path}")
    

    
def batch_convert_png_to_ctxr():
    png_folder_path = filedialog.askdirectory(title="Select a folder with PNG files")
    ctxr_folder_path = filedialog.askdirectory(title="Select a folder with original CTXR files for headers")
    
    if not png_folder_path or not ctxr_folder_path:
        return

    for root, dirs, files in os.walk(png_folder_path):
        for file in files:
            if file.endswith('.png'):
                png_file_path = os.path.join(root, file)
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
                    f.write(ctxr_header)
                    f.write(image_bgra.tobytes())

    label.config(text=f"Conversion Completed for folder {png_folder_path}")
    
def batch_convert_ctxr_to_bmp():
    folder_path = filedialog.askdirectory(title="Select a folder with CTXR files")
    if not folder_path:
        return

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.ctxr'):
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    ctxr_header = f.read(132)
                    pixel_data = f.read()
                
                    width = struct.unpack_from('>H', ctxr_header, 8)[0]
                    height = struct.unpack_from('>H', ctxr_header, 10)[0]
                    
                image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)

                r, g, b, a = image_bgra.split()
                image_rgba = Image.merge("RGBA", (b, g, r, a))

                bmp_file_path = file_path.replace('.ctxr', '.bmp')
                image_rgba.save(bmp_file_path, 'BMP')

    label.config(text=f"Conversion Completed for folder {folder_path}")


def batch_convert_bmp_to_ctxr():
    bmp_folder_path = filedialog.askdirectory(title="Select a folder with BMP files")
    ctxr_folder_path = filedialog.askdirectory(title="Select a folder with original CTXR files for headers")
    
    if not bmp_folder_path or not ctxr_folder_path:
        return

    for root, dirs, files in os.walk(bmp_folder_path):
        for file in files:
            if file.endswith('.bmp'):
                bmp_file_path = os.path.join(root, file)
                ctxr_file_path = os.path.join(ctxr_folder_path, file.replace('.bmp', '.ctxr'))
                
                if not os.path.exists(ctxr_file_path):
                    continue  # Skip if matching CTXR file doesn't exist

                with open(ctxr_file_path, 'rb') as f:
                    ctxr_header = f.read(132)

                image = Image.open(bmp_file_path)

                if image.mode != "RGBA":
                    image = image.convert("RGBA")

                r, g, b, a = image.split()
                image_bgra = Image.merge("RGBA", (b, g, r, a))
                
                new_ctxr_file_path = bmp_file_path.replace('.bmp', '_new.ctxr')
                with open(new_ctxr_file_path, 'wb') as f:
                    f.write(ctxr_header)
                    f.write(image_bgra.tobytes())

    label.config(text=f"Conversion Completed for folder {bmp_folder_path}")


def batch_convert():
    input_format = chosen_batch_format.get().split(' to ')[0]
    output_format = chosen_batch_format.get().split(' to ')[1]
    
    # Define function mapping
    func_map = {
        'ctxr to png': batch_convert_ctxr_to_png,
        'ctxr to dds': batch_convert_ctxr_to_dds,
        'ctxr to bmp': batch_convert_ctxr_to_bmp,
        'dds to ctxr': batch_convert_dds_to_ctxr,
        'png to ctxr': batch_convert_png_to_ctxr,
        'bmp to ctxr': batch_convert_bmp_to_ctxr,
    }

    # Call the relevant function
    func_map[chosen_batch_format.get()]()

app = Tk()
app.title("CTXR Converter by 316austin316")
app.geometry("700x500")

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

title = Label(frame, text="CTXR <-> BMP/PNG/DDS Converter", font=("Arial", 16, "bold"))
title.grid(row=0, column=0, columnspan=2, pady=10)

description = Label(frame, text="For MGS3HD PC\nCode by 316austin316", font=("Arial", 10))
description.grid(row=1, column=0, columnspan=2, pady=10)

open_button = Button(frame, text="Open CTXR File", command=open_file, bg='#4CAF50', fg='white', font=("Arial", 10, "bold"))
open_button.grid(row=2, column=0, pady=10, sticky="ew")

save_button = Button(frame, text="Save as CTXR", command=save_as_ctxr, bg='#FF9800', fg='white', font=("Arial", 10, "bold"))
save_button.grid(row=2, column=1, pady=10, sticky="ew")

# Dropdown for BMP/PNG/DDS choice for individual conversion
format_options = ["bmp", "png", "dds"]
chosen_format.set(format_options[0])  # set default value
format_dropdown = OptionMenu(frame, chosen_format, *format_options)
format_dropdown.grid(row=3, column=0, pady=10)

# Dropdown for batch conversion format choice
batch_format_options = ["ctxr to png", "ctxr to dds", "ctxr to bmp", "dds to ctxr", "png to ctxr", "bmp to ctxr"]
chosen_batch_format.set(batch_format_options[0])
batch_format_dropdown = OptionMenu(frame, chosen_batch_format, *batch_format_options)
batch_format_dropdown.grid(row=4, column=0, pady=10)

# Button for batch conversion
batch_convert_button = Button(frame, text="Batch Convert", command=batch_convert, bg='#2196F3', fg='white', font=("Arial", 10, "bold"))
batch_convert_button.grid(row=4, column=1, pady=10, sticky="ew")


app.mainloop()
