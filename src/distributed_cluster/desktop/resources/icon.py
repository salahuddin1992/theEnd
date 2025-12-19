"""
Icon Generator for NebulaCompute Desktop
مولد الأيقونة لتطبيق سطح المكتب

This script generates an application icon in multiple formats.
"""

from pathlib import Path


def create_svg_icon():
    """Create SVG icon"""
    svg_content = '''<?xml version="1.0" encoding="UTF-8"?>
<svg width="256" height="256" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
    </linearGradient>
    <linearGradient id="cloudGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#ffffff;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#e0e0e0;stop-opacity:1" />
    </linearGradient>
  </defs>

  <!-- Background circle -->
  <circle cx="128" cy="128" r="120" fill="url(#bgGrad)"/>

  <!-- Cloud shape -->
  <g transform="translate(40, 70)">
    <!-- Main cloud body -->
    <ellipse cx="88" cy="60" rx="70" ry="45" fill="url(#cloudGrad)"/>
    <ellipse cx="45" cy="70" rx="40" ry="35" fill="url(#cloudGrad)"/>
    <ellipse cx="130" cy="70" rx="35" ry="30" fill="url(#cloudGrad)"/>

    <!-- Connection dots -->
    <circle cx="60" cy="55" r="8" fill="#667eea"/>
    <circle cx="90" cy="45" r="8" fill="#764ba2"/>
    <circle cx="120" cy="55" r="8" fill="#667eea"/>
    <circle cx="75" cy="75" r="6" fill="#667eea"/>
    <circle cx="105" cy="75" r="6" fill="#764ba2"/>

    <!-- Connection lines -->
    <line x1="60" y1="55" x2="90" y2="45" stroke="#667eea" stroke-width="2"/>
    <line x1="90" y1="45" x2="120" y2="55" stroke="#764ba2" stroke-width="2"/>
    <line x1="60" y1="55" x2="75" y2="75" stroke="#667eea" stroke-width="2"/>
    <line x1="120" y1="55" x2="105" y2="75" stroke="#764ba2" stroke-width="2"/>
    <line x1="75" y1="75" x2="105" y2="75" stroke="#667eea" stroke-width="2"/>
  </g>

  <!-- Glow effect -->
  <circle cx="128" cy="128" r="115" fill="none" stroke="white" stroke-width="2" opacity="0.3"/>
</svg>
'''
    return svg_content


def create_ico_from_svg():
    """Instructions for creating ICO from SVG"""
    instructions = '''
To create an ICO file for Windows:

Option 1: Using online converter
1. Go to https://cloudconvert.com/svg-to-ico
2. Upload icon.svg
3. Download icon.ico

Option 2: Using ImageMagick (if installed)
Run: magick convert icon.svg -define icon:auto-resize=256,128,64,48,32,16 icon.ico

Option 3: Using Python with Pillow and cairosvg
pip install pillow cairosvg
Then run:
    from PIL import Image
    import cairosvg
    import io

    # Convert SVG to PNG
    png_data = cairosvg.svg2png(url='icon.svg', output_width=256, output_height=256)
    img = Image.open(io.BytesIO(png_data))

    # Save as ICO with multiple sizes
    img.save('icon.ico', format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
'''
    return instructions


def main():
    """Generate icon files"""
    resources_dir = Path(__file__).parent

    # Create SVG
    svg_path = resources_dir / 'icon.svg'
    with open(svg_path, 'w') as f:
        f.write(create_svg_icon())
    print(f"Created: {svg_path}")

    # Create instructions
    instructions_path = resources_dir / 'CREATE_ICO.txt'
    with open(instructions_path, 'w') as f:
        f.write(create_ico_from_svg())
    print(f"Created: {instructions_path}")

    # Try to create ICO if dependencies available
    try:
        import io

        import cairosvg
        from PIL import Image

        png_data = cairosvg.svg2png(url=str(svg_path), output_width=256, output_height=256)
        img = Image.open(io.BytesIO(png_data))

        ico_path = resources_dir / 'icon.ico'
        img.save(str(ico_path), format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        print(f"Created: {ico_path}")
    except ImportError:
        print("Note: Install 'cairosvg' and 'pillow' to auto-generate icon.ico")


if __name__ == '__main__':
    main()
