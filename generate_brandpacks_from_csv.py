#!/usr/bin/env python3
# generate_brandpacks_from_csv.py
# Create assets/brands/<key>/{brand.json, logo.png} for 537+ councils.
# Source: a CSV with columns: name[,key,primary,secondary,accent,state]
#
# - If key missing -> auto slugify from name.
# - If colors missing -> derive stable, readable colors from name.
# - Wyndham gets your exact palette.
# - Creates a simple 512x512 logo.png with initials if it's missing.

from __future__ import annotations
import os
import csv
import json
import re
import hashlib
from pathlib import Path
from typing import Dict, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    raise SystemExit("Please install Pillow:  pip install Pillow")

BRANDS_ROOT = Path("assets/brands")
BRANDS_ROOT.mkdir(parents=True, exist_ok=True)

# --- Your explicit override for Wyndham ---
WYNDHAM_NAME = "Wyndham City Council"
WYNDHAM_PALETTE = {
    "primary":   "#0051A5",
    "secondary": "#012B55",
    "accent":    "#00B3A4",
}

# -----------------------------------------
# Helpers
# -----------------------------------------

def slugify(name: str) -> str:
    s = name.lower()
    # Remove common words to keep slugs short & distinct
    s = s.replace("city council", "").replace("shire council", "").replace("rural city council", "")
    s = s.replace("borough of", "").replace("council", "").replace("city of", "")
    s = re.sub(r"[^a-z0-9]+", "", s)
    s = s.strip()
    return s[:32] or "council"

def hex_from_hash(name: str, salt: str = "") -> str:
    # Stable, not too-dark, not neon
    h = hashlib.sha256((salt + name).encode("utf-8")).hexdigest()
    def ch(i):
        v = int(h[i:i+2], 16)
        v = 40 + (v % 160)  # 40..199
        return v
    r, g, b = ch(0), ch(2), ch(4)
    return f"#{r:02x}{g:02x}{b:02x}"

def derive_palette(name: str) -> Tuple[str, str, str]:
    p = hex_from_hash(name, "p")
    s = hex_from_hash(name, "s")
    a = hex_from_hash(name, "a")
    # ensure distinctness
    if s.lower() == p.lower():
        s = hex_from_hash(name, "s2")
    if a.lower() in (p.lower(), s.lower()):
        a = hex_from_hash(name, "a2")
    return p, s, a

def initials_from_name(name: str) -> str:
    # “City”, “Shire”, “Rural”, “Council”, “of”, “Borough” are dropped
    words = [w for w in re.split(r"\s+", name.strip())
             if w.lower() not in {"city", "shire", "rural", "council", "of", "borough"}]
    if not words:
        return "LC"
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[-1][0]).upper()

def ensure_logo(path: Path, color_hex: str, initials: str):
    size = 512
    img = Image.new("RGB", (size, size), color_hex)
    draw = ImageDraw.Draw(img)
    # Font
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 180)
    except Exception:
        font = ImageFont.load_default()
    # Center initials
    bbox = draw.textbbox((0, 0), initials, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) // 2, (size - h) // 2), initials, fill="#FFFFFF", font=font)
    img.save(path)

def write_brand(key: str, name: str, primary: str, secondary: str, accent: str):
    folder = BRANDS_ROOT / key
    folder.mkdir(parents=True, exist_ok=True)

    data: Dict[str, str] = {
        "name": name,
        "primary": primary,
        "secondary": secondary,
        "accent": accent,
        "text_on_primary": "#FFFFFF",
        "logo_alt": name,
    }
    with open(folder / "brand.json", "w") as f:
        json.dump(data, f, indent=2)

    logo_path = folder / "logo.png"
    if not logo_path.exists():
        ensure_logo(logo_path, primary, initials_from_name(name))

def normalize_hex(h: str | None) -> str | None:
    if not h:
        return None
    h = h.strip()
    if not h:
        return None
    if not h.startswith("#"):
        if re.fullmatch(r"[0-9A-Fa-f]{6}", h):
            h = "#" + h
        else:
            return None
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", h):
        return h.upper()
    return None

# -----------------------------------------
# Main
# -----------------------------------------

def main(csv_path: str):
    # Always ensure a neutral default brand exists
    write_brand("default", "PolicySimplify", "#1555C0", "#0B2A5C", "#00B3A4")

    created, updated = 0, 0
    seen_keys = set()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"name"}
        if not required.issubset({c.lower() for c in reader.fieldnames or []}):
            raise SystemExit("CSV must have at least a 'name' column. Optional: key,primary,secondary,accent,state")

        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue

            # Key
            key = (row.get("key") or "").strip().lower()
            if not key:
                key = slugify(name)

            if key in seen_keys:
                # Deduplicate silently; in real script you might warn
                continue
            seen_keys.add(key)

            # Colors
            if name == WYNDHAM_NAME:
                primary, secondary, accent = WYNDHAM_PALETTE["primary"], WYNDHAM_PALETTE["secondary"], WYNDHAM_PALETTE["accent"]
            else:
                p = normalize_hex(row.get("primary"))
                s = normalize_hex(row.get("secondary"))
                a = normalize_hex(row.get("accent"))
                if not (p and s and a):
                    p, s, a = derive_palette(name)

                primary, secondary, accent = p, s, a

            # Write files
            folder = BRANDS_ROOT / key
            existed = folder.exists()
            write_brand(key, name, primary, secondary, accent)
            created += (0 if existed else 1)
            updated += (1 if existed else 0)

    print(f"✅ Done. Created {created} new brand packs, updated {updated}. Output → {BRANDS_ROOT}/")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python generate_brandpacks_from_csv.py councils_master.csv")
        print("CSV columns: name[,key,primary,secondary,accent,state]")
        sys.exit(1)
    main(sys.argv[1])
