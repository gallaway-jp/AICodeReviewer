#!/usr/bin/env python3
"""
Convert SVG icon to ICO format for PyInstaller
"""
import os
import subprocess
import sys
from pathlib import Path


def convert_svg_to_ico(svg_path, ico_path, size=256):
    """Convert SVG to ICO format using multiple fallback methods"""

    svg_path = Path(svg_path)
    ico_path = Path(ico_path)

    if not svg_path.exists():
        print(f"SVG file not found: {svg_path}")
        return False

    # Method 1: Try cairosvg if available
    try:
        import cairosvg
        import io
        from PIL import Image

        print("Using cairosvg for conversion...")
        png_data = cairosvg.svg2png(url=str(svg_path), output_width=size, output_height=size)

        with Image.open(io.BytesIO(png_data)) as img:  # type: ignore[arg-type]
            ico_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(ico_path), format='ICO', sizes=[(size, size), (128, 128), (64, 64), (32, 32), (16, 16)])

        print(f"Successfully converted {svg_path} to {ico_path}")
        return True

    except ImportError:
        print("cairosvg not available, trying alternative methods...")
    except Exception as e:
        print(f"cairosvg failed: {e}, trying alternative methods...")

    # Method 2: Try using ImageMagick if available
    try:
        print("Trying ImageMagick for conversion...")
        result = subprocess.run([
            'magick', 'convert', str(svg_path),
            '-background', 'transparent',
            '-size', f'{size}x{size}',
            str(ico_path)
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            print(f"Successfully converted {svg_path} to {ico_path} using ImageMagick")
            return True
        else:
            print(f"ImageMagick failed: {result.stderr}")

    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("ImageMagick not available or timed out")

    # Method 3: Try using Inkscape if available
    try:
        print("Trying Inkscape for conversion...")
        result = subprocess.run([
            'inkscape', str(svg_path),
            '--export-width', str(size),
            '--export-height', str(size),
            '--export-type', 'png',
            '--export-filename', str(ico_path.with_suffix('.png'))
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            # Convert PNG to ICO using PIL
            from PIL import Image
            png_path = ico_path.with_suffix('.png')
            with Image.open(png_path) as img:
                ico_path.parent.mkdir(parents=True, exist_ok=True)
                img.save(str(ico_path), format='ICO', sizes=[(size, size), (128, 128), (64, 64), (32, 32), (16, 16)])

            # Clean up temporary PNG
            png_path.unlink(missing_ok=True)
            print(f"Successfully converted {svg_path} to {ico_path} using Inkscape")
            return True
        else:
            print(f"Inkscape failed: {result.stderr}")

    except (subprocess.TimeoutExpired, FileNotFoundError):
        print("Inkscape not available or timed out")

    # Method 4: Fallback - create a simple placeholder icon
    print("All conversion methods failed. Creating a simple placeholder icon...")
    try:
        from PIL import Image, ImageDraw

        # Create a simple 256x256 placeholder icon
        img = Image.new('RGBA', (256, 256), (15, 23, 42, 255))  # Dark background
        draw = ImageDraw.Draw(img)

        # Draw a simple document shape
        draw.rounded_rectangle([56, 40, 200, 216], radius=12, fill=(229, 231, 235, 255))
        draw.rounded_rectangle([72, 72, 184, 82], radius=5, fill=(96, 165, 250, 255))
        draw.rounded_rectangle([72, 96, 168, 106], radius=5, fill=(147, 197, 253, 255))
        draw.rounded_rectangle([72, 120, 176, 130], radius=5, fill=(96, 165, 250, 255))

        # Draw checkmark circle
        draw.ellipse([100, 140, 156, 196], fill=(34, 197, 94, 255))
        draw.line([116, 168, 124, 176, 140, 156], fill=(255, 255, 255, 255), width=6, joint='curve')

        ico_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(ico_path), format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])

        print(f"Created placeholder icon at {ico_path}")
        return True

    except Exception as e:
        print(f"Failed to create placeholder icon: {e}")
        return False


if __name__ == "__main__":
    # Input: SVG from assets folder
    svg_path = "src/aicodereviewer/assets/icon.svg"

    # Output: ICO in build folder
    ico_path = "build/icon.ico"

    success = convert_svg_to_ico(svg_path, ico_path)
    if not success:
        print("ERROR: Could not convert SVG to ICO")
        sys.exit(1)
    else:
        print("Icon conversion completed successfully")