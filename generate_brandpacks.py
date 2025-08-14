#!/usr/bin/env python3
# generate_brandpacks.py
# Creates assets/brands/<key>/{brand.json, logo.png} for many councils at once.
# - Uses specific brand for Wyndham (from your request).
# - Provides sensible, distinct colors for the rest (hash-based but readable).
# - Includes 79 VIC councils + 8 placeholders to reach 87 (edit as you like).

from __future__ import annotations
import os, json, hashlib, re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BRANDS_ROOT = Path("assets/brands")
BRANDS_ROOT.mkdir(parents=True, exist_ok=True)

# --- Helpers --------------------------------------------------------------

def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "", s.replace("city council","").replace("shire council","").replace("rural city council","").replace("borough of","").replace("council",""))
    s = s.strip()
    return s[:24] or "council"

def hex_from_hash(name: str, salt: str = "") -> str:
    # Stable color from hash of name (and salt to vary channels)
    h = hashlib.sha256((salt + name).encode("utf-8")).hexdigest()
    # Keep it vivid but not neon: clamp channels to [32..200]
    def ch(i): 
        v = int(h[i:i+2], 16)
        v = 32 + (v % 169)  # 32..200
        return v
    r, g, b = ch(0), ch(2), ch(4)
    return f"#{r:02x}{g:02x}{b:02x}"

def derive_palette(name: str) -> tuple[str,str,str]:
    # Make primary/secondary/accent distinct (shift hash seeds)
    primary   = hex_from_hash(name, "p")
    secondary = hex_from_hash(name, "s")
    accent    = hex_from_hash(name, "a")
    # Avoid too-similar pairs: if secondary≈primary, tweak
    if secondary.lower() == primary.lower():
        secondary = hex_from_hash(name, "s2")
    if accent.lower() == primary.lower() or accent.lower() == secondary.lower():
        accent = hex_from_hash(name, "a2")
    return primary, secondary, accent

def ensure_logo(path: Path, color_hex: str, initials: str):
    # Create simple 512x512 square logo with initials (fallback if you don’t have real logos)
    size = 512
    img = Image.new("RGB", (size, size), color_hex)
    draw = ImageDraw.Draw(img)
    # Try to load a common system font; fallback to default
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 180)
    except:
        font = ImageFont.load_default()
    # Center initials
    bbox = draw.textbbox((0,0), initials, font=font)
    w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
    draw.text(((size-w)//2, (size-h)//2), initials, fill="#FFFFFF", font=font)
    img.save(path)

def initials_from_name(name: str) -> str:
    words = [w for w in re.split(r"\s+", name.strip()) if w.lower() not in {"city","shire","rural","council","of","borough"}]
    if not words:
        return "LC"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()

def write_brand(key: str, name: str, primary: str, secondary: str, accent: str):
    folder = BRANDS_ROOT / key
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "name": name,
        "primary": primary,
        "secondary": secondary,
        "accent": accent,
        "text_on_primary": "#FFFFFF",
        "logo_alt": name
    }
    with open(folder / "brand.json", "w") as f:
        json.dump(data, f, indent=2)
    # Generate a placeholder logo if none exists
    logo_path = folder / "logo.png"
    if not logo_path.exists():
        ensure_logo(logo_path, primary, initials_from_name(name))

# --- Council list (79 VIC + 8 placeholders = 87) -------------------------

VIC_COUNCILS = [
    "Alpine Shire Council",
    "Ararat Rural City Council",
    "Ballarat City Council",
    "Banyule City Council",
    "Bass Coast Shire Council",
    "Baw Baw Shire Council",
    "Bayside City Council",
    "Benalla Rural City Council",
    "City of Greater Bendigo",
    "Boroondara City Council",
    "Brimbank City Council",
    "Buloke Shire Council",
    "Campaspe Shire Council",
    "Cardinia Shire Council",
    "City of Casey",
    "Central Goldfields Shire Council",
    "Colac Otway Shire Council",
    "Corangamite Shire Council",
    "Darebin City Council",
    "East Gippsland Shire Council",
    "Frankston City Council",
    "Gannawarra Shire Council",
    "Glen Eira City Council",
    "Glenelg Shire Council",
    "Golden Plains Shire Council",
    "Greater Dandenong City Council",
    "City of Greater Geelong",
    "Greater Shepparton City Council",
    "Hepburn Shire Council",
    "Hindmarsh Shire Council",
    "Hobsons Bay City Council",
    "Horsham Rural City Council",
    "Hume City Council",
    "Indigo Shire Council",
    "Kingston City Council",
    "Knox City Council",
    "Latrobe City Council",
    "Loddon Shire Council",
    "Macedon Ranges Shire Council",
    "Manningham City Council",
    "Maribyrnong City Council",
    "Maroondah City Council",
    "City of Melbourne",
    "Melton City Council",
    "Mildura Rural City Council",
    "Mitchell Shire Council",
    "Moira Shire Council",
    "Monash City Council",
    "Moonee Valley City Council",
    "Merri-bek City Council",
    "Mornington Peninsula Shire Council",
    "Mount Alexander Shire Council",
    "Moyne Shire Council",
    "Murrindindi Shire Council",
    "Nillumbik Shire Council",
    "Northern Grampians Shire Council",
    "Port Phillip City Council",
    "Pyrenees Shire Council",
    "Borough of Queenscliffe",
    "South Gippsland Shire Council",
    "Stonnington City Council",
    "Strathbogie Shire Council",
    "Surf Coast Shire Council",
    "Swan Hill Rural City Council",
    "Towong Shire Council",
    "Wangaratta Rural City Council",
    "Warrnambool City Council",
    "Wellington Shire Council",
    "West Wimmera Shire Council",
    "City of Whittlesea",
    "Wodonga City Council",
    "Wyndham City Council",
    "Yarra City Council",
    "Yarra Ranges Council",
    "Yarriambiack Shire Council",
]

# Add 8 placeholders—you can replace these with real councils from other states:
EXTRA_8 = [
    "Placeholder Council Alpha",
    "Placeholder Council Bravo",
    "Placeholder Council Charlie",
    "Placeholder Council Delta",
    "Placeholder Council Echo",
    "Placeholder Council Foxtrot",
    "Placeholder Council Golf",
    "Placeholder Council Hotel",
]

ALL_87 = VIC_COUNCILS + EXTRA_8

# --- Generate -------------------------------------------------------------

def main():
    # Specific palette for Wyndham per your request:
    WYNDHAM = {
        "name": "Wyndham City Council",
        "primary": "#0051A5",
        "secondary": "#012B55",
        "accent": "#00B3A4",
    }

    created = 0
    for name in ALL_87:
        if name == WYNDHAM["name"]:
            primary, secondary, accent = WYNDHAM["primary"], WYNDHAM["secondary"], WYNDHAM["accent"]
        else:
            primary, secondary, accent = derive_palette(name)
        key = slugify(name)
        write_brand(key, name, primary, secondary, accent)
        created += 1

    # Always ensure a neutral default as well
    write_brand("default", "PolicySimplify", "#1555C0", "#0B2A5C", "#00B3A4")
    print(f"✅ Generated/updated {created} brand packs (+ default) under {BRANDS_ROOT}/")

if __name__ == "__main__":
    main()
