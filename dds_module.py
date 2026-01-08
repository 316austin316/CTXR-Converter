# dds_module.py
import struct
import numpy as np
from PIL import Image
import logging
import os


class DDSError(Exception):
    """Custom exception for DDS-related errors"""
    pass


def is_power_of_two(n):
    """Check if a number is a power of 2"""
    return n > 0 and (n & (n - 1)) == 0


def next_power_of_two(n):
    """Get the next power of 2 greater than or equal to n"""
    if n <= 0:
        return 1
    power = 1
    while power < n:
        power <<= 1
    return power


def calculate_mipmap_sizes(width, height, mipmap_count):
    """Calculate the sizes of all mipmap levels"""
    sizes = []
    curr_w, curr_h = width, height
    
    for i in range(mipmap_count):
        sizes.append((curr_w, curr_h))
        curr_w = max(1, curr_w // 2)
        curr_h = max(1, curr_h // 2)
    
    return sizes


def create_dds_header(width, height, mipmap_count, format_type="DXT1"):
    """Create a DDS header with proper format support"""
    header = bytearray(128)
    
    # Magic number
    header[0:4] = b'DDS '
    
    # Header size
    struct.pack_into('<I', header, 4, 124)
    
    # Flags
    flags = 0x1007  # DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT
    if mipmap_count > 1:
        flags |= 0x20000  # DDSD_MIPMAPCOUNT
    struct.pack_into('<I', header, 8, flags)
    
    # Height and width
    struct.pack_into('<I', header, 12, height)
    struct.pack_into('<I', header, 16, width)
    
    # Pitch/Linear size (for uncompressed)
    if format_type in ["DXT1", "DXT3", "DXT5"]:
        # Compressed format
        pitch = max(1, ((width + 3) // 4)) * 8  # DXT1
        if format_type in ["DXT3", "DXT5"]:
            pitch = max(1, ((width + 3) // 4)) * 16
        struct.pack_into('<I', header, 20, pitch)
    else:
        # Uncompressed format
        struct.pack_into('<I', header, 20, width * 4)  # 32-bit RGBA
    
    # Depth (unused for 2D textures)
    struct.pack_into('<I', header, 24, 0)
    
    # Mipmap count
    struct.pack_into('<I', header, 28, mipmap_count)
    
    # Reserved
    struct.pack_into('<I', header, 32, 0)
    struct.pack_into('<I', header, 36, 0)
    struct.pack_into('<I', header, 40, 0)
    struct.pack_into('<I', header, 44, 0)
    struct.pack_into('<I', header, 48, 0)
    struct.pack_into('<I', header, 52, 0)
    struct.pack_into('<I', header, 56, 0)
    struct.pack_into('<I', header, 60, 0)
    struct.pack_into('<I', header, 64, 0)
    struct.pack_into('<I', header, 68, 0)
    struct.pack_into('<I', header, 72, 0)
    struct.pack_into('<I', header, 76, 0)
    
    # Pixel format
    pixel_format_size = 32
    struct.pack_into('<I', header, 80, pixel_format_size)
    
    if format_type in ["DXT1", "DXT3", "DXT5"]:
        # Compressed format flags
        struct.pack_into('<I', header, 84, 0x4)  # DDPF_FOURCC
        
        # FourCC code
        if format_type == "DXT1":
            fourcc = b'DXT1'
        elif format_type == "DXT3":
            fourcc = b'DXT3'
        elif format_type == "DXT5":
            fourcc = b'DXT5'
        header[88:92] = fourcc
        
        # RGB bit counts (unused for compressed)
        struct.pack_into('<I', header, 92, 0)
        struct.pack_into('<I', header, 96, 0)
        struct.pack_into('<I', header, 100, 0)
        struct.pack_into('<I', header, 104, 0)
    else:
        # Uncompressed RGBA format
        struct.pack_into('<I', header, 84, 0x41)  # DDPF_RGB | DDPF_ALPHAPIXELS
        
        # RGB bit counts
        struct.pack_into('<I', header, 92, 32)  # 32 bits per pixel
        
        # RGB masks
        struct.pack_into('<I', header, 96, 0x000000FF)  # R mask
        struct.pack_into('<I', header, 100, 0x0000FF00)  # G mask
        struct.pack_into('<I', header, 104, 0x00FF0000)  # B mask
        struct.pack_into('<I', header, 108, 0xFF000000)  # A mask
    
    # Caps
    caps = 0x1000  # DDSCAPS_TEXTURE
    if mipmap_count > 1:
        caps |= 0x400000  # DDSCAPS_MIPMAP
    struct.pack_into('<I', header, 112, caps)
    
    # Caps2 (unused for 2D textures)
    struct.pack_into('<I', header, 116, 0)
    
    # Caps3 and Caps4 (unused)
    struct.pack_into('<I', header, 120, 0)
    struct.pack_into('<I', header, 124, 0)
    
    return header


def ctxr_to_dds(ctxr_file_path, dds_file_path, ctxr_header):
    """Convert CTXR to DDS with enhanced NPOT support"""
    try:
        # Extract width, height, and mipmap count from the CTXR header
        width = struct.unpack_from('>H', ctxr_header, 8)[0]
        height = struct.unpack_from('>H', ctxr_header, 10)[0]
        mipmap_count = struct.unpack_from('>B', ctxr_header, 0x26)[0]
        
        logging.info(f"Converting CTXR: {width}x{height}, {mipmap_count} mipmaps")
        
        # Check if dimensions are power of 2
        is_pot_width = is_power_of_two(width)
        is_pot_height = is_power_of_two(height)
        
        if not (is_pot_width and is_pot_height):
            logging.warning(f"NPOT texture detected: {width}x{height}")
            # For NPOT textures, we'll use uncompressed format
            format_type = "RGBA"
        else:
            # Use DXT1 for power-of-2 textures
            format_type = "DXT1"
        
        # Read the pixel data
        with open(ctxr_file_path, 'rb') as file:
            file.seek(132)  # Skip the CTXR header
            pixel_data = file.read()
        
        # Convert pixel data to image
        image = Image.frombytes('RGBA', (width, height), pixel_data)
        
        # Generate mipmaps if needed
        mipmaps = [image]
        if mipmap_count > 1:
            curr_w, curr_h = width, height
            for i in range(1, mipmap_count):
                curr_w = max(1, curr_w // 2)
                curr_h = max(1, curr_h // 2)
                mip_image = image.resize((curr_w, curr_h), Image.LANCZOS)
                mipmaps.append(mip_image)
                logging.info(f"Generated mipmap {i}: {curr_w}x{curr_h}")
        
        # Create DDS header
        dds_header = create_dds_header(width, height, mipmap_count, format_type)
        
        # Write DDS file
        with open(dds_file_path, 'wb') as f:
            f.write(dds_header)
            
            for mip_image in mipmaps:
                if format_type == "RGBA":
                    # Uncompressed RGBA
                    mip_data = mip_image.tobytes("raw", "BGRA")
                else:
                    # For compressed formats, we'd need a compression library
                    # For now, use uncompressed
                    mip_data = mip_image.tobytes("raw", "BGRA")
                
                # Ensure 4-byte alignment
                if len(mip_data) % 4 != 0:
                    mip_data += b'\x00' * (4 - (len(mip_data) % 4))
                
                f.write(mip_data)
        
        logging.info(f"Successfully converted to DDS: {dds_file_path}")
        return True
        
    except Exception as e:
        error_msg = f"Error converting CTXR to DDS: {str(e)}"
        logging.error(error_msg)
        raise DDSError(error_msg)


def dds_to_ctxr(dds_file_path, ctxr_file_path, ctxr_header_template, original_ctxr_path=None):
    """Convert DDS to CTXR with DXT5 compression support"""
    try:
        with open(dds_file_path, 'rb') as f:
            # Read DDS header
            magic = f.read(4)
            if magic != b'DDS ':
                raise DDSError("Invalid DDS file: missing magic number")
            
            header_size = struct.unpack('<I', f.read(4))[0]
            if header_size != 124:
                raise DDSError("Invalid DDS header size")
            
            flags = struct.unpack('<I', f.read(4))[0]
            height = struct.unpack('<I', f.read(4))[0]
            width = struct.unpack('<I', f.read(4))[0]
            pitch = struct.unpack('<I', f.read(4))[0]
            depth = struct.unpack('<I', f.read(4))[0]
            mipmap_count = struct.unpack('<I', f.read(4))[0]
            
            # Skip reserved fields
            f.read(44)
            
            # Read pixel format
            pixel_format_size = struct.unpack('<I', f.read(4))[0]
            pixel_format_flags = struct.unpack('<I', f.read(4))[0]
            fourcc = f.read(4)
            rgb_bit_count = struct.unpack('<I', f.read(4))[0]
            r_mask = struct.unpack('<I', f.read(4))[0]
            g_mask = struct.unpack('<I', f.read(4))[0]
            b_mask = struct.unpack('<I', f.read(4))[0]
            a_mask = struct.unpack('<I', f.read(4))[0]
            
            # Skip caps (4 DWORDs = 16 bytes)
            f.read(16)
            
            # Skip reserved2 (1 DWORD = 4 bytes) - THIS WAS MISSING!
            f.read(4)
            
            # Now we're at byte 128, start of pixel data
            
            # Check if this is a DXT5 compressed file
            is_dxt5 = (fourcc == b'DXT5')
            
            logging.info(f"Converting DDS: {width}x{height}, {mipmap_count} mipmaps, DXT5: {is_dxt5}")
            
            if is_dxt5:
                # DXT5 compressed - read compressed data directly
                # Calculate main texture compressed size
                width_blocks = max(1, (width + 3) // 4)
                height_blocks = max(1, (height + 3) // 4)
                main_compressed_size = width_blocks * height_blocks * 16
                
                # Read main level compressed data
                pixel_data = f.read(main_compressed_size)
                
                # Read mipmaps if present
                mipmap_data = []
                if mipmap_count > 1:
                    for level in range(1, mipmap_count):
                        mip_w = max(1, width >> level)
                        mip_h = max(1, height >> level)
                        mip_blocks_w = max(1, (mip_w + 3) // 4)
                        mip_blocks_h = max(1, (mip_h + 3) // 4)
                        mip_compressed_size = mip_blocks_w * mip_blocks_h * 16
                        mip_data = f.read(mip_compressed_size)
                        mipmap_data.append(mip_data)
                
                # If we have the original CTXR file, read its exact padding structure
                # This is critical for DXT5 files to maintain proper alignment
                if original_ctxr_path and os.path.exists(original_ctxr_path):
                    try:
                        from ctxr_utils import parse_mipmap_info
                        with open(original_ctxr_path, 'rb') as orig_f:
                            orig_header = orig_f.read(132)
                            orig_mipmap_count = struct.unpack_from('>B', orig_header, 0x26)[0]
                            orig_pixel_length = struct.unpack_from('>I', orig_header, 0x80)[0]
                            orig_width = struct.unpack_from('>H', orig_header, 8)[0]
                            orig_height = struct.unpack_from('>H', orig_header, 10)[0]
                            
                            # Skip original pixel data
                            orig_f.read(orig_pixel_length)
                            
                            # Parse original mipmap structure to get padding
                            if orig_mipmap_count > 1:
                                orig_mipmap_info, orig_final_padding = parse_mipmap_info(
                                    orig_f, orig_mipmap_count, orig_width, orig_height,
                                    is_compressed=True, compression_format='DXT5'
                                )
                            else:
                                orig_mipmap_info = []
                                orig_final_padding = b'\x00' * 24
                                
                        logging.info(f"Using original CTXR padding structure")
                    except Exception as e:
                        logging.warning(f"Could not read original padding structure: {e}, using defaults")
                        orig_mipmap_info = None
                        orig_final_padding = b'\x00' * 24
                else:
                    orig_mipmap_info = None
                    orig_final_padding = b'\x00' * 24
                
                # Prepare CTXR header
                ctxr_header = bytearray(ctxr_header_template)
                struct.pack_into('>H', ctxr_header, 8, width)
                struct.pack_into('>H', ctxr_header, 10, height)
                struct.pack_into('>B', ctxr_header, 0x26, mipmap_count)
                struct.pack_into('>I', ctxr_header, 0x80, len(pixel_data))
                
                # Write CTXR file with compressed data
                with open(ctxr_file_path, 'wb') as out_f:
                    out_f.write(ctxr_header)
                    out_f.write(pixel_data)
                    
                    # Write mipmaps with original padding if available
                    if mipmap_count > 1:
                        for idx, mip_data in enumerate(mipmap_data):
                            # Use original padding if available
                            if orig_mipmap_info and idx < len(orig_mipmap_info):
                                padding = orig_mipmap_info[idx]["padding"]
                            else:
                                # Default: no padding between DXT5 mipmaps
                                padding = b''
                            
                            out_f.write(padding)
                            out_f.write(mip_data)
                        
                        # Final padding
                        out_f.write(orig_final_padding)
                    else:
                        # No mipmaps
                        out_f.write(orig_final_padding)
                
                logging.info(f"Successfully converted DXT5 DDS to CTXR: {ctxr_file_path}")
                return True
            else:
                # Uncompressed - read all image data
                image_data = f.read()
                
                # Simple conversion: RGBA to BGRA for CTXR
                image = Image.frombytes('RGBA', (width, height), image_data[:width * height * 4])
                pixel_data = image.tobytes("raw", "BGRA")
                
                # Prepare CTXR header
                ctxr_header = bytearray(ctxr_header_template)
                struct.pack_into('>H', ctxr_header, 8, width)
                struct.pack_into('>H', ctxr_header, 10, height)
                struct.pack_into('>B', ctxr_header, 0x26, mipmap_count)
                struct.pack_into('>I', ctxr_header, 0x80, len(pixel_data))
                
                # Write CTXR file
                with open(ctxr_file_path, 'wb') as out_f:
                    out_f.write(ctxr_header)
                    out_f.write(pixel_data)
                    # Add padding
                    out_f.write(b'\x00' * 32)
                
                logging.info(f"Successfully converted uncompressed DDS to CTXR: {ctxr_file_path}")
                return True
        
    except Exception as e:
        error_msg = f"Error converting DDS to CTXR: {str(e)}"
        logging.error(error_msg)
        raise DDSError(error_msg)


def batch_convert_ctxr_to_dds_enhanced(input_folder, output_folder):
    """Enhanced batch conversion with better error handling"""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    ctxr_files = [f for f in os.listdir(input_folder) if f.endswith('.ctxr')]
    total_files = len(ctxr_files)
    success_count = 0
    error_files = []
    
    logging.info(f"Starting batch conversion: {total_files} files")
    
    for i, filename in enumerate(ctxr_files):
        try:
            ctxr_path = os.path.join(input_folder, filename)
            dds_path = os.path.join(output_folder, filename.replace('.ctxr', '.dds'))
            
            # Read CTXR header
            with open(ctxr_path, 'rb') as f:
                ctxr_header = f.read(132)
            
            # Convert file
            ctxr_to_dds(ctxr_path, dds_path, ctxr_header)
            success_count += 1
            
            logging.info(f"Progress: {i+1}/{total_files} - {filename}")
            
        except Exception as e:
            error_msg = f"Failed to convert {filename}: {str(e)}"
            logging.error(error_msg)
            error_files.append((filename, str(e)))
    
    logging.info(f"Batch conversion complete: {success_count}/{total_files} successful")
    if error_files:
        logging.warning(f"Failed files: {len(error_files)}")
        for filename, error in error_files:
            logging.error(f"  {filename}: {error}")
    
    return success_count, error_files


def batch_convert_dds_to_ctxr_enhanced(input_folder, output_folder, template_folder):
    """Enhanced batch conversion from DDS to CTXR"""
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    dds_files = [f for f in os.listdir(input_folder) if f.endswith('.dds')]
    total_files = len(dds_files)
    success_count = 0
    error_files = []
    
    logging.info(f"Starting batch conversion: {total_files} files")
    
    for i, filename in enumerate(dds_files):
        try:
            dds_path = os.path.join(input_folder, filename)
            ctxr_path = os.path.join(output_folder, filename.replace('.dds', '.ctxr'))
            
            # Find corresponding template CTXR file
            template_name = filename.replace('.dds', '.ctxr')
            template_path = os.path.join(template_folder, template_name)
            
            if not os.path.exists(template_path):
                logging.warning(f"No template found for {filename}, skipping")
                continue
            
            # Read template header
            with open(template_path, 'rb') as f:
                template_header = f.read(132)
            
            # Convert file, passing template path for padding preservation
            dds_to_ctxr(dds_path, ctxr_path, template_header, original_ctxr_path=template_path)
            success_count += 1
            
            logging.info(f"Progress: {i+1}/{total_files} - {filename}")
            
        except Exception as e:
            error_msg = f"Failed to convert {filename}: {str(e)}"
            logging.error(error_msg)
            error_files.append((filename, str(e)))
    
    logging.info(f"Batch conversion complete: {success_count}/{total_files} successful")
    if error_files:
        logging.warning(f"Failed files: {len(error_files)}")
        for filename, error in error_files:
            logging.error(f"  {filename}: {error}")
    
    return success_count, error_files