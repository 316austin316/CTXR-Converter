from tkinter import Tk, filedialog, Button, Label, Frame
from PIL import Image
import struct

# Global variable to store the CTXR header
ctxr_header = None

def open_file():
    global ctxr_header

    file_path = filedialog.askopenfilename(title="Select a CTXR file", filetypes=[("CTXR files", "*.ctxr")])
    if not file_path:
        return
    
    with open(file_path, 'rb') as file:
        ctxr_header = file.read(132)  # Read and save the first 132 bytes for the header
        pixel_data = file.read()
    
        width = struct.unpack_from('>H', ctxr_header, 8)[0]
        height = struct.unpack_from('>H', ctxr_header, 10)[0]
    
    image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)

    r, g, b, a = image_bgra.split()
    image_rgba = Image.merge("RGBA", (b, g, r, a))
    
    bmp_rgba_file_path = file_path.replace('.ctxr', '_rgba.bmp')
    image_rgba.save(bmp_rgba_file_path, 'BMP')

    label.config(text=f"File saved as {bmp_rgba_file_path}")


def save_as_ctxr():
    global ctxr_header

    if not ctxr_header:
        label.config(text="Please open a CTXR file first.")
        return

    file_path = filedialog.askopenfilename(title="Select a BMP file", filetypes=[("BMP files", "*.bmp")])
    if not file_path:
        return

    image = Image.open(file_path)

    if image.mode != "RGBA":
        # Add an alpha channel if it doesn't have one
        image = image.convert("RGBA")

    r, g, b, a = image.split()
    image_bgra = Image.merge("RGBA", (b, g, r, a))

    ctxr_file_path = file_path.replace('.bmp', '.ctxr')
    with open(ctxr_file_path, 'wb') as file:
        file.write(ctxr_header)
        file.write(image_bgra.tobytes())

    label.config(text=f"File saved as {ctxr_file_path}")


app = Tk()
app.title("CTXR <-> BMP Converter by 316austin316")
app.geometry("500x300")

frame = Frame(app)
frame.pack(pady=50)

title = Label(frame, text="CTXR <-> BMP Converter", font=("Arial", 16, "bold"))
title.pack()

description = Label(frame, text="For MGS3HD PC\nCode by 316austin316", font=("Arial", 10))
description.pack(pady=10)

open_button = Button(frame, text="Open CTXR File", command=open_file, bg='#4CAF50', fg='white', font=("Arial", 10, "bold"))
open_button.pack(pady=10)

save_button = Button(frame, text="Save as CTXR", command=save_as_ctxr, bg='#FF9800', fg='white', font=("Arial", 10, "bold"))
save_button.pack(pady=10)

label = Label(frame, text="")
label.pack(pady=20)

app.mainloop()






