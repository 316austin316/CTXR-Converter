import struct
import numpy as np
import os
from tkinter import filedialog, messagebox
from datetime import datetime



# Get the directory where this script is located.
module_dir = os.path.dirname(os.path.abspath(__file__))
log_file_path = os.path.join(module_dir, 'no_swizzle.log')



# Load the no-swizzle set from the log file
no_swizzle_set = set()
with open('no_swizzle.log', 'r') as log_file:
    for line in log_file:
        file_name = line.strip()
        if file_name.endswith('.ctxr'):
            no_swizzle_set.add(file_name)

print("No-Swizzle Set:", no_swizzle_set)

def convert_ps3_ctxr_to_dds(file_path=None):
    if file_path is None:
        file_path = filedialog.askopenfilename(
            title="Select PS3 CTXR File",
            filetypes=[("CTXR Files", "*.ctxr")]
        )
        if not file_path:
            return  # User cancelled the file selection
            
    output_file_path = file_path.replace('.ctxr', '.dds')
    dds_header_file = "DDS_header.bin"
    
    file_name = os.path.basename(file_path)
    should_swizzle = file_name not in no_swizzle_set  # Check if the file needs swizzling

    with open(file_path, 'rb') as f:
        header = f.read(128)
        magic = header[0:4]
        if magic != b'\x02\x00\x01\x01':
            print(f"Invalid PS3 CTXR file: {file_path}")
            return

        total_data_length = struct.unpack('>I', header[4:8])[0]  # Pixel data + padding
        pixel_data_offset = struct.unpack('>I', header[16:20])[0]
        pixel_data_length = struct.unpack('>I', header[20:24])[0]  # Actual pixel data length
        width = struct.unpack('>H', header[44:46])[0]
        height = struct.unpack('>H', header[46:48])[0]
        mipmap_count = struct.unpack('>B', header[37:38])[0]

        f.seek(pixel_data_offset)
        pixel_data = f.read(pixel_data_length)  # Read only the actual pixel data

    if should_swizzle:
        # Swizzled images require the Morton order rearrangement
        pixel_data_array = np.frombuffer(pixel_data, dtype=np.uint8)

        def calculate_z_index(x, y, log2_width, log2_height):
            offset = 0
            shift_count = 0
            while x or y:
                if log2_width > 0:
                    offset |= (x & 1) << shift_count
                    x >>= 1
                    shift_count += 1
                    log2_width -= 1
                if log2_height > 0:
                    offset |= (y & 1) << shift_count
                    y >>= 1
                    shift_count += 1
                    log2_height -= 1
            return offset

        def image_from_morton_order_rectangular(data, width, height):
            bits_x = int(np.ceil(np.log2(width)))
            bits_y = int(np.ceil(np.log2(height)))
            unswizzled = np.zeros(width * height * 4, dtype=np.uint8)

            for y in range(height):
                for x in range(width):
                    z_index = calculate_z_index(x, y, bits_x, bits_y)
                    src_idx = z_index * 4
                    dst_idx = (y * width + x) * 4
                    unswizzled[dst_idx:dst_idx + 4] = data[src_idx:src_idx + 4]

            return unswizzled

        # Apply Morton order rearrangement
        unswizzled_data = image_from_morton_order_rectangular(pixel_data_array, width, height)

        # Reshape and swap color channels for DDS format
        unswizzled_array = unswizzled_data.reshape((height, width, 4))
        unswizzled_array = unswizzled_array[..., [3, 2, 1, 0]]  # Convert RGBA to BGRA
        swapped_pixel_data = unswizzled_array.tobytes()
    else:
        # Non-swizzled images: swap RGBA to BGRA
        pixel_data_array = np.frombuffer(pixel_data, dtype=np.uint8)
        pixel_data_array = pixel_data_array.reshape((-1, 4))
        # Swap R and B channels (RGBA to BGRA)
        swapped_pixel_data = pixel_data_array[:, [3, 1, 2, 0]].flatten().tobytes()

    with open(dds_header_file, 'rb') as f:
        dds_header = bytearray(f.read())

    struct.pack_into("<I", dds_header, 12, height)
    struct.pack_into("<I", dds_header, 16, width)
    struct.pack_into("<I", dds_header, 28, mipmap_count)

    with open(output_file_path, 'wb') as f:
        f.write(dds_header)
        f.write(swapped_pixel_data)

    print(f"File saved as {output_file_path}")


def batch_convert_ps3_ctxr_to_dds():
    directory_path = filedialog.askdirectory(title="Select Folder with PS3 CTXR Files")
    if not directory_path:
        return

    error_files = []  # List to collect files that encounter errors

    for file_name in os.listdir(directory_path):
        if file_name.endswith('.ctxr'):
            file_path = os.path.join(directory_path, file_name)
            print(f"Converting: {file_path}")
            try:
                convert_ps3_ctxr_to_dds(file_path)
            except Exception as e:
                print(f"Error converting {file_path}: {e}")
                error_files.append(f"{file_name}: {e}")  # Collect the file name and error for logging

    # If there were errors, save them to a log file and show a message box
    if error_files:
        log_file_path = os.path.join(directory_path, f"conversion_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        with open(log_file_path, 'w') as log_file:
            log_file.write("Conversion Errors:\n")
            log_file.write("\n".join(error_files))
        
        # Display a message box with the path to the log file
        messagebox.showwarning("Conversion Errors", f"Errors occurred in some files. See log:\n{log_file_path}")
    else:
        messagebox.showinfo("Batch Conversion Complete", "All files converted successfully.")

    print("Batch conversion complete.")
