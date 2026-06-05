[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/U7U8EQSU2)

# CTXR-Converter
Convert CTXR files for MGS3HD/MGS2HD to PNG/TGA/DDS and vice versa.

Drag & Drop conversion is supported.

You can also associate .ctxr files with CTXR3 for double-click -> extract support. ♥


# Guide:

## GUI Mode
Open ctxr3.exe to open the GUI.

Click either the "Open CTXR File"  or "Save as CTXR" button.


## Command Line mode:
ctxr3.exe <input...> [-o OUTPUT] [--mips | --no-mips] [--ignore-no-mip-regex] [--help]

### ARGUMENTS:
	<input...> | one or more files. .ctxr → .dds; .png/.tga/.dds → .ctxr.
	-o, --output | output path; single input only. If not specified, will default to beside the input.

### MIPMAP ARGUMENTS:
If not specified, ctxr3 will operating in "auto" mode, utilizing the filename patterns in "no_mip_regex.txt" to decide.
	--mips | force mipmap generation (image→ctxr).
	--no-mips | force no mipmaps (for UI, speculars, atlas textures, ect)
	--ignore-no-mip-regex (alias --ignore-regex) — skip the regex file entirely.


### Example:
ctxr3.exe loading_jp.dds -o "C:\Users\snake\OneDrive\Desktop"

This will convert loading_jp.dds to CTXR format, utilizing "no_mip_regex.txt"'s regex patterns to decide , and output it to the desktop.


### Return codes:
0	-	All inputs converted successfully
1	-	At least one input failed (missing file, bad extension, malformed/unsupported file)
2	-	argparse usage error — e.g. -o with multiple inputs, or an unknown flag.


# Mipmaps:
Mipmap generation is fully supported.

The game's vanilla textures utilize "Kaiser" filter mipmaps.

For the highest quality mipmaps, and to match the unmodified game's texture quality, it's recommended to generate your own .DDS files using [Nvidia Texture Tool](https://developer.nvidia.com/gpu-accelerated-texture-compression), with mipmaps set to "Kaiser".

DDS files will always convert their mipmaps over 1:1, so make sure to properly select if they should be generated or not in NVTT's texture settings.
	- Suggested NVTT settings: Format: 8.8.8.8 BGRA, Mipmap Options -> Gamma Correct Enabled & Filter Type Kaiser, Compression Effort: Highest

Mipmaps will otherwise be automatically generated for .TGA & .PNG -> CTXR files using "Lanczos" filtering, which is generally lower quality/blurrier than "Kaiser".


*Note: UI, specular maps (textures with "_sub" in their name), and atlas textures generally should NOT use mipmaps (unless you know exactly what you are doing), as they are either wasted space, or mipmaps cause misalignment / incorrect parts of the texture to be visible at a distance.
	- This is automatically handled by "no_mip_regex.txt", which contains regex patterns for all UI textures, speculars, and most atlas textures for both MGS2 & MGS3.
	- Textures which match the patterns in this txt will (correctly) be generated without mipmaps.
	- If you are creating custom / completely new UI textures with filenames that don't appear in the unmodified game, it is HIGHLY advised to remember adding your texture to your "no_mip_regex.txt" so mipmaps.




## Features

- Convert CTXR to multiple image formats.
- Batch conversion support.
- Image Viewer with Mipmap support.

## Known Bugs:

- Progress bar hangs during large batches sometimes. (don't worry if you see this, the program is functioning fine)
- If you get an error about image data, try to convert to .tga or .dds.

# To Do:
- Add better error handling.
- Switch Support (WIP: Switch swizzle is complex, I'm working on it... yes still stuck :/)
- VITA, PS5 support? (Need more samples to work with if you have any, send some.. PS4 is the same as PC so it should work, let me know)
