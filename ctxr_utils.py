import struct
import logging


class CTXRError(Exception):
    """Custom exception for CTXR-related errors"""
    pass


def read_padding_and_size(file_obj, expected_mip_size, max_pad=64, is_compressed=False, compression_format=None):
    """
    Smart reader that handles padding alignment and size fields.
    For DXT5: Scans for data but aligns down to nearest block (16 bytes) to capture leading zeros.
    """
    start_pos = file_obj.tell()
    
    # --- DXT5 SPECIAL HANDLING ---
    if is_compressed and compression_format == 'DXT5':
        # 1. Scan forward to find where the actual non-zero data starts
        peek_limit = max_pad + 32  # Look a bit ahead
        current_pad_len = 0
        found_data = False
        
        while current_pad_len < peek_limit:
            byte = file_obj.read(1)
            if not byte: break
            if byte != b'\x00':
                found_data = True
                break
            current_pad_len += 1
            
        # 2. Logic to find the true start
        if found_data:
            # We found a non-zero byte at (start_pos + current_pad_len)
            # DXT5 blocks are 16 bytes. Valid data often starts with 00 00 (Alpha).
            # So the "True Start" is the nearest 16-byte boundary <= where we found data.
            
            # Go back to start to calculate absolute positions
            file_obj.seek(start_pos)
            
            # Calculate absolute offset of the non-zero byte
            non_zero_abs_offset = start_pos + current_pad_len
            
            # Align DOWN to 16 bytes (0x10)
            # Example: Found at 0x40A2 -> Aligns down to 0x40A0
            aligned_start = (non_zero_abs_offset // 16) * 16
            
            # Ensure we didn't go backward past our original start
            if aligned_start < start_pos:
                aligned_start = start_pos
                
            # Seek to this aligned start
            file_obj.seek(aligned_start)
            logging.info(f"  DXT5 Align: Start {hex(start_pos)} | Found Data {hex(non_zero_abs_offset)} | Snapped to {hex(aligned_start)}")
            
            # Verify we have enough data left? (Optional, handled by read)
        else:
            # Found only zeros? Just reset and read (likely a blank mipmap)
            file_obj.seek(start_pos)

        # 3. Check for Size Field (Just in case, though rare in your files)
        # Some variants might still have it.
        peek_pos = file_obj.tell()
        peek_bytes = file_obj.read(4)
        file_obj.seek(peek_pos)
        
        mip_size = expected_mip_size
        
        if len(peek_bytes) == 4:
            size_be = struct.unpack('>I', peek_bytes)[0]
            # Check if this looks like a size field (within 10% of expected)
            tolerance = expected_mip_size * 0.1
            if (expected_mip_size - tolerance) <= size_be <= (expected_mip_size + tolerance):
                logging.info(f"  Found valid DXT5 size field: {size_be}")
                file_obj.read(4) # Consume size
                mip_size = size_be

        # 4. Read Data
        mip_data = file_obj.read(mip_size)
        return b"", mip_size, mip_data

    # --- STANDARD UNCOMPRESSED HANDLING (Original Logic) ---
    else:
        padding = b""
        while len(padding) < max_pad:
            pos = file_obj.tell()
            byte = file_obj.read(1)
            if not byte: raise CTXRError("Unexpected end of file")
            if byte == b'\x00':
                padding += byte
            else:
                file_obj.seek(pos)
                break
                
        # Read size field
        size_bytes = file_obj.read(4)
        if len(size_bytes) != 4: raise CTXRError("End of file reading size")
        size_field = struct.unpack('>I', size_bytes)[0]
        
        # Verify size
        tolerance = expected_mip_size * 0.1
        if (expected_mip_size - tolerance) <= size_field <= (expected_mip_size + tolerance):
            mip_size = size_field
        else:
            # Fallback if size field is missing/invalid
            file_obj.seek(file_obj.tell() - 4)
            mip_size = expected_mip_size
            
        mip_data = file_obj.read(mip_size)
        return padding, mip_size, mip_data


def parse_mipmap_info(file_obj, mipmap_count, width, height, is_compressed=False, compression_format=None):
    """
    For each mipmap level (from level 1 to mipmap_count-1), compute the expected mipmap dimensions,
    then dynamically read padding bytes (using read_padding_and_size) until the next 4-byte integer
    equals the expected mipmap size.
    
    If is_compressed is True, the sizes in the file will be compressed sizes (much smaller than width*height*4).
    
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
        
        if is_compressed and compression_format == 'DXT5':
            # DXT5: 16 bytes per 4x4 block
            # Round up dimensions to multiple of 4
            blocks_w = max(1, (mip_w + 3) // 4)
            blocks_h = max(1, (mip_h + 3) // 4)
            expected_size = blocks_w * blocks_h * 16
        else:
            # Uncompressed RGBA: 4 bytes per pixel
            expected_size = mip_w * mip_h * 4
            
        logging.info(f"[Level {level}] Expected dimensions: {mip_w}x{mip_h} (expected {expected_size} bytes)")
        
        try:
            pad, mip_size, mip_data = read_padding_and_size(
                file_obj, 
                expected_size, 
                is_compressed=is_compressed, 
                compression_format=compression_format
            )
            logging.info(f"[Level {level}] Read {len(pad)} padding bytes; size field: {mip_size} bytes; pixel data: {len(mip_data)} bytes")
            mip_info.append({"padding": pad, "size": mip_size, "data": mip_data})
        except CTXRError as e:
            logging.error(f"Error parsing mipmap level {level}: {e}")
            raise
            
    final_padding = file_obj.read(24)
    logging.info(f"[Final] Read final padding of {len(final_padding)} bytes")
    return mip_info, final_padding