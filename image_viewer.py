import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import io
import struct
import os
import logging
import numpy as np

from ctxr_utils import (
    read_ctxr, parse_header, CTXRError,
    FORMAT_A8R8G8B8, FORMAT_DXT1, FORMAT_DXT3, FORMAT_DXT5, FORMAT_NAMES,
)
from dds_module import create_dds_header

try:
    from ps3_ctxr_module import _read_ps3, PS3_MAGIC, parse_ps3_header
    _HAS_PS3 = True
except Exception:
    _HAS_PS3 = False


class ImageViewer:
    def __init__(self, parent=None):
        self.parent = parent
        self.current_image = None
        self.current_image_path = None
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.mipmap_level = 0
        self.mipmaps = []
        self.ctxr_header = None
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the image viewer UI"""
        if self.parent:
            self.window = tk.Toplevel(self.parent)
        else:
            self.window = tk.Tk()
            
        self.window.title("CTXR Image Viewer")
        self.window.geometry("800x600")
        
        # Toolbar
        toolbar = ttk.Frame(self.window)
        toolbar.pack(fill='x', padx=5, pady=5)
        
        ttk.Button(toolbar, text="Open CTXR", command=self.open_ctxr_file).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Open Image", command=self.open_image_file).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Fit", command=self.fit_to_window).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Actual", command=self.actual_size).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Zoom +", command=self.zoom_in).pack(side='left', padx=2)
        ttk.Button(toolbar, text="Zoom -", command=self.zoom_out).pack(side='left', padx=2)
        
        # Mipmap level selector
        ttk.Label(toolbar, text="Mipmap:").pack(side='left', padx=(10, 2))
        self.mipmap_var = tk.StringVar(value="0")
        self.mipmap_combo = ttk.Combobox(toolbar, textvariable=self.mipmap_var, 
                                        values=["0"], state="readonly", width=5)
        self.mipmap_combo.pack(side='left', padx=2)
        self.mipmap_combo.bind('<<ComboboxSelected>>', self.on_mipmap_change)
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.window, textvariable=self.status_var, relief='sunken')
        status_bar.pack(side='bottom', fill='x')
        
        # Canvas for image display
        self.canvas_frame = ttk.Frame(self.window)
        self.canvas_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Scrollbars
        self.h_scrollbar = ttk.Scrollbar(self.canvas_frame, orient='horizontal')
        self.v_scrollbar = ttk.Scrollbar(self.canvas_frame, orient='vertical')
        
        # Canvas
        self.canvas = tk.Canvas(self.canvas_frame, 
                               xscrollcommand=self.h_scrollbar.set,
                               yscrollcommand=self.v_scrollbar.set,
                               bg='gray')
        
        self.h_scrollbar.config(command=self.canvas.xview)
        self.v_scrollbar.config(command=self.canvas.yview)
        
        # Grid layout
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.h_scrollbar.grid(row=1, column=0, sticky='ew')
        self.v_scrollbar.grid(row=0, column=1, sticky='ns')
        
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Bind mouse events
        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<MouseWheel>', self.on_mouse_wheel)
        self.canvas.bind('<Button-4>', self.on_mouse_wheel)
        self.canvas.bind('<Button-5>', self.on_mouse_wheel)
        
        # Keyboard shortcuts
        self.window.bind('<Control-plus>', lambda e: self.zoom_in())
        self.window.bind('<Control-minus>', lambda e: self.zoom_out())
        self.window.bind('<Control-0>', lambda e: self.fit_to_window())
        self.window.bind('<Control-1>', lambda e: self.actual_size())
        
    def _decode_mips_to_pil(self, width, height, fmt_name, mips):
        images = []
        for level, data in enumerate(mips):
            mw = max(1, width >> level)
            mh = max(1, height >> level)
            if fmt_name == "A8R8G8B8":
                img = Image.frombytes("RGBA", (mw, mh), data, "raw", "BGRA")
            else:
                # Build a one-level DDS for this mip and let PIL decode it.
                hdr = create_dds_header(mw, mh, 1, fmt_name)
                buf = io.BytesIO(bytes(hdr) + data)
                img = Image.open(buf)
                img.load()
                img = img.convert("RGBA")

            # Alpha is stored ps2 0-> 128 range, scale it up for the viewer.
            alpha = img.getchannel("A")
            alpha = alpha.point(lambda a: min(a * 2, 255))
            img.putalpha(alpha)

            images.append(img)
        return images

    def open_ctxr_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a CTXR file",
            filetypes=[("CTXR files", "*.ctxr")],
        )
        if not file_path:
            return

        try:
            with open(file_path, "rb") as f:
                magic = f.read(4)

            is_ps3 = _HAS_PS3 and magic == PS3_MAGIC

            if is_ps3:
                h = parse_ps3_header(open(file_path, "rb").read(128))
                _, mips = _read_ps3(file_path)
                width, height = h.width, h.height
                fmt_name = h.dds_format
                platform = "PS3"
            else:
                tex = read_ctxr(file_path)
                width = tex.header.width
                height = tex.header.height
                fmt_name = FORMAT_NAMES.get(tex.header.format, "")
                mips = tex.mips
                platform = "PC"

            if fmt_name not in ("A8R8G8B8", "DXT1", "DXT3", "DXT5"):
                messagebox.showerror(
                    "Unsupported format",
                    f"This viewer can't display {fmt_name or 'this'} textures.",
                )
                return

            self.all_images = self._decode_mips_to_pil(width, height, fmt_name, mips)
            if not self.all_images:
                messagebox.showerror("Error", "No image data found.")
                return
            main_image = self.all_images[0]

            mipmap_values = [str(i) for i in range(len(self.all_images))]
            self.mipmap_combo['values'] = mipmap_values
            self.mipmap_var.set("0")

            self.current_image_path = file_path
            self.display_image(main_image)

            self.status_var.set(
                f"Loaded: {os.path.basename(file_path)} "
                f"({width}x{height}, {platform} {fmt_name}, "
                f"{len(self.all_images)} levels)"
            )

        except Exception as e:
            error_msg = f"Error loading CTXR file: {str(e)}"
            logging.error(error_msg)
            import traceback
            logging.error(traceback.format_exc())
            messagebox.showerror("Error", error_msg)
    
    def open_image_file(self):
        """Open and display a regular image file"""
        file_path = filedialog.askopenfilename(
            title="Select an image file",
            filetypes=[
                ("Image files", "*.png;*.jpg;*.jpeg;*.bmp;*.tga;*.dds"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg;*.jpeg"),
                ("BMP files", "*.bmp"),
                ("TGA files", "*.tga"),
                ("DDS files", "*.dds")
            ]
        )
        if not file_path:
            return
            
        try:
            image = Image.open(file_path)
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            self.current_image_path = file_path
            self.all_images = [image]
            self.mipmaps = []
            self.ctxr_header = None
            
            # Update mipmap selector
            self.mipmap_combo['values'] = ["0"]
            self.mipmap_var.set("0")
            
            self.display_image(image)
            self.status_var.set(f"Loaded: {os.path.basename(file_path)} ({image.width}x{image.height})")
            
        except Exception as e:
            error_msg = f"Error loading image file: {str(e)}"
            logging.error(error_msg)
            messagebox.showerror("Error", error_msg)
    
    def display_image(self, image):
        """Display the given image on the canvas"""
        self.current_image = image
        
        # Create PhotoImage for display
        self.photo = ImageTk.PhotoImage(image)
        
        # Clear canvas and display image
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        
        # Update scroll region
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
        
        # Fit to window if this is the first load
        if self.zoom_factor == 1.0:
            self.fit_to_window()
    
    def on_mipmap_change(self, event=None):
        """Handle mipmap level change"""
        try:
            level = int(self.mipmap_var.get())
            if 0 <= level < len(self.all_images):
                self.display_image(self.all_images[level])
                self.status_var.set(f"Mipmap level {level}: {self.current_image.width}x{self.current_image.height}")
        except (ValueError, IndexError):
            pass
    
    def fit_to_window(self):
        """Fit image to window size"""
        if not self.current_image:
            return
            
        # Get canvas size
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        if canvas_width <= 1 or canvas_height <= 1:
            # Canvas not yet sized, schedule for later
            self.window.after(100, self.fit_to_window)
            return
        
        # Calculate zoom factor to fit image
        img_width, img_height = self.current_image.size
        scale_x = canvas_width / img_width
        scale_y = canvas_height / img_height
        self.zoom_factor = min(scale_x, scale_y, 1.0)  # Don't scale up
        
        self.apply_zoom()
    
    def actual_size(self):
        """Display image at actual size"""
        self.zoom_factor = 1.0
        self.apply_zoom()
    
    def zoom_in(self):
        """Zoom in by 25%"""
        self.zoom_factor *= 1.25
        self.apply_zoom()
    
    def zoom_out(self):
        """Zoom out by 25%"""
        if not self.current_image:
            return

        new_zoom_factor = self.zoom_factor / 1.25

        new_width = int(self.current_image.width * new_zoom_factor)
        new_height = int(self.current_image.height * new_zoom_factor)

        if new_width < 1 or new_height < 1:
            return

        self.zoom_factor = new_zoom_factor
        self.apply_zoom()
    
    def apply_zoom(self):
        """Apply current zoom factor to the image"""
        if not self.current_image:
            return

        # Resize image
        new_width = max(1, int(self.current_image.width * self.zoom_factor))
        new_height = max(1, int(self.current_image.height * self.zoom_factor))

        resized_image = self.current_image.resize((new_width, new_height), Image.LANCZOS)

        # Update display
        self.photo = ImageTk.PhotoImage(resized_image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)
        self.canvas.config(scrollregion=self.canvas.bbox("all"))

        # Update status
        self.status_var.set(f"Zoom: {self.zoom_factor:.2f}x ({new_width}x{new_height})")

    def on_mouse_down(self, event):
        """Handle mouse button press for panning"""
        self.canvas.scan_mark(event.x, event.y)
    
    def on_mouse_drag(self, event):
        """Handle mouse drag for panning"""
        self.canvas.scan_dragto(event.x, event.y, gain=1)
    
    def on_mouse_wheel(self, event):
        """Handle mouse wheel for zooming"""
        if event.delta > 0 or event.num == 4:
            self.zoom_in()
        else:
            self.zoom_out()
    
    def run(self):
        """Start the image viewer"""
        self.window.mainloop()


def main():
    """Main function to run the image viewer standalone"""
    viewer = ImageViewer()
    viewer.run()


if __name__ == "__main__":
    main()