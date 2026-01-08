import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import struct
import os
import logging
from ctxr_utils import parse_mipmap_info, CTXRError


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
        
    def open_ctxr_file(self):
        """Open and display a CTXR file"""
        file_path = filedialog.askopenfilename(
            title="Select a CTXR file",
            filetypes=[("CTXR files", "*.ctxr")]
        )
        if not file_path:
            return
        
        # List of DXT5 compressed files
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
            
        try:
            # Check if this is a DXT5 file
            filename = os.path.basename(file_path)
            is_dxt5 = filename in dxt5_files
            
            with open(file_path, 'rb') as f:
                self.ctxr_header = f.read(132)
                mipmap_count = struct.unpack_from('>B', self.ctxr_header, 0x26)[0]
                pixel_data_length = struct.unpack_from('>I', self.ctxr_header, 0x80)[0]
                width = struct.unpack_from('>H', self.ctxr_header, 8)[0]
                height = struct.unpack_from('>H', self.ctxr_header, 10)[0]
                pixel_data = f.read(pixel_data_length)
                
                # Parse mipmaps if present
                mipmap_info_list = []
                if mipmap_count > 1:
                    is_compressed = is_dxt5
                    compression_format = 'DXT5' if is_compressed else 'UNCOMPRESSED'
                    mipmap_info_list, _ = parse_mipmap_info(f, mipmap_count, width, height, 
                                                       is_compressed=is_compressed,
                                                       compression_format=compression_format)
                
                if is_dxt5:
                    # DXT5 - decompress via temporary DDS file
                    import tempfile
                    
                    with tempfile.NamedTemporaryFile(suffix='.dds', delete=False) as temp_dds:
                        # Write DDS header
                        dds_header_file = "DDS_header_DXT5.bin"
                        try:
                            with open(dds_header_file, "rb") as header_file:
                                dds_header = bytearray(header_file.read())
                        except FileNotFoundError:
                            messagebox.showerror("Error", 
                                               "DDS_header_DXT5.bin not found.\n"
                                               "Please ensure it's in the same directory as the script.")
                            return
                        
                        struct.pack_into("<I", dds_header, 12, height)
                        struct.pack_into("<I", dds_header, 16, width)
                        struct.pack_into("<I", dds_header, 28, mipmap_count)
                        
                        temp_dds.write(dds_header)
                        temp_dds.write(pixel_data)
                        
                        # Write mipmaps
                        for mip_info in mipmap_info_list:
                            temp_dds.write(mip_info["data"])
                        
                        temp_dds_path = temp_dds.name
                    
                    # Try to open the DDS file with PIL
                    try:
                        dds_image = Image.open(temp_dds_path)
                        main_image = dds_image.convert('RGBA')
                        
                        # Try to extract mipmaps from DDS
                        self.mipmaps = []
                        # PIL doesn't easily expose DDS mipmaps, so we'll just show the main level
                        
                    except Exception as e:
                        logging.error(f"Failed to open DDS file: {e}")
                        messagebox.showerror("Error", 
                                           "Could not decompress DXT5 data.\n"
                                           "You may need to install 'pillow-dds' plugin:\n"
                                           "pip install pillow-dds\n\n"
                                           "Or convert to DDS manually first.")
                        return
                    finally:
                        # Clean up temp file
                        try:
                            os.unlink(temp_dds_path)
                        except:
                            pass
                else:
                    # Uncompressed - process normally
                    self.mipmaps = []
                    for idx, mip_info in enumerate(mipmap_info_list):
                        mip_data = mip_info["data"]
                        mip_level = idx + 1  # Level 1, 2, 3, etc.
                        mip_w = max(1, width >> mip_level)
                        mip_h = max(1, height >> mip_level)
                        expected_bytes = mip_w * mip_h * 4
                        
                        logging.info(f"Processing mipmap level {mip_level}: {mip_w}x{mip_h}, expected {expected_bytes} bytes, got {len(mip_data)} bytes")
                        
                        if len(mip_data) != expected_bytes:
                            logging.error(f"Mipmap {mip_level} data size mismatch! Expected {expected_bytes}, got {len(mip_data)}. Skipping this mipmap.")
                            continue  # Skip this mipmap instead of trying to load it with wrong size
                        
                        try:
                            # Load the raw data
                            mip_image = Image.frombytes('RGBA', (mip_w, mip_h), mip_data)
                            r, g, b, a = mip_image.split()
                            
                            # TEST ALL POSSIBLE ARRANGEMENTS
                            # We'll try ARGB format (common in some texture formats)
                            # If stored as ARGB but read as RGBA:
                            # File bytes: A R G B A R G B ...
                            # PIL reads as: R G B A R G B A ...
                            # So PIL's R = file's A, G = file's R, B = file's G, A = file's B
                            # To correct: R=G (file's R), G=B (file's G), B=A (file's B), A=R (file's A)
                            
                            mip_rgba = Image.merge("RGBA", (g, r, a, b))  # GRAB interpretation
                            
                            self.mipmaps.append(mip_rgba)
                            
                            logging.info(f"Loaded mipmap {mip_level} using ARGB byte order")
                        except Exception as e:
                            logging.error(f"Failed to create mipmap {mip_level}: {e}")
                            continue
                    
                    # Convert main image
                    image_bgra = Image.frombytes('RGBA', (width, height), pixel_data)
                    r, g, b, a = image_bgra.split()
                    main_image = Image.merge("RGBA", (b, g, r, a))
                
                # Store all mipmap levels
                self.all_images = [main_image] + self.mipmaps
                
                # Update mipmap selector
                mipmap_values = [str(i) for i in range(len(self.all_images))]
                self.mipmap_combo['values'] = mipmap_values
                self.mipmap_var.set("0")
                
                self.current_image_path = file_path
                self.display_image(main_image)
                
                format_str = "DXT5 compressed" if is_dxt5 else "uncompressed"
                self.status_var.set(f"Loaded: {os.path.basename(file_path)} ({width}x{height}, {format_str}, {len(self.all_images)} levels)")
                
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
        self.zoom_factor /= 1.25
        self.apply_zoom()
    
    def apply_zoom(self):
        """Apply current zoom factor to the image"""
        if not self.current_image:
            return
            
        # Resize image
        new_width = int(self.current_image.width * self.zoom_factor)
        new_height = int(self.current_image.height * self.zoom_factor)
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