#!/usr/bin/env python3
"""
Create a subset of Winter Lights data for end-to-end testing.

Usage:
    python create_subset.py \
        --input winter_lights_transformed.json \
        --output winter_lights_subset.json \
        --count 5
"""

import argparse
import json
import random
import sys
from pathlib import Path
from datetime import datetime


def select_diverse_subset(entries: list, count: int) -> list:
    """
    Select a diverse subset with:
    - Mix of entries with/without images
    - Mix of entry types (architectural, art installation, etc.)
    - Good geographic spread
    """
    # First, prioritize entries with images and descriptions
    with_images = [e for e in entries if e.get('image_count', 0) > 0 and e['metadata'].get('description')]
    without_images = [e for e in entries if e.get('image_count', 0) == 0 and e['metadata'].get('description')]
    
    subset = []
    
    # Take half from with_images, half from without (or adjust based on availability)
    half_count = count // 2
    
    if with_images:
        # Shuffle and select
        random.seed(42)  # For reproducibility
        random.shuffle(with_images)
        subset.extend(with_images[:min(half_count, len(with_images))])
    
    if without_images and len(subset) < count:
        random.shuffle(without_images)
        needed = count - len(subset)
        subset.extend(without_images[:min(needed, len(without_images))])
    
    # If we still need more, fill from remaining entries
    if len(subset) < count:
        remaining = [e for e in entries if e not in subset]
        random.shuffle(remaining)
        subset.extend(remaining[:count - len(subset)])
    
    return subset[:count]


def main():
    parser = argparse.ArgumentParser(description="Create a subset of Winter Lights data")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to transformed JSON")
    parser.add_argument("--output", type=str, default="winter_lights_subset.json",
                        help="Output subset JSON file path")
    parser.add_argument("--count", type=int, default=5,
                        help="Number of entries in subset (default: 5)")
    parser.add_argument("--random", action="store_true",
                        help="Select random entries instead of diverse")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)
    
    print(f"🚀 Creating subset of {args.count} entries")
    print(f"   Input: {input_path}")
    print(f"   Output: {output_path}")
    print()
    
    # Load data
    print("📂 Loading data...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entries = data.get('entries', [])
    print(f"   Found {len(entries)} total entries")
    print()
    
    # Select subset
    if args.random:
        print("🎲 Selecting random entries...")
        random.seed(42)
        subset = random.sample(entries, min(args.count, len(entries)))
    else:
        print("🎯 Selecting diverse subset (mix of images/no-images)...")
        subset = select_diverse_subset(entries, args.count)
    
    # Show selected entries
    print(f"\n📋 Selected {len(subset)} entries:")
    for i, entry in enumerate(subset, 1):
        pi = entry['place_info']
        meta = entry['metadata']
        print(f"   {i}. {pi['place_id']}")
        print(f"      Name: {pi['place_name']}")
        print(f"      Images: {entry.get('image_count', 0)}")
        print(f"      Description: {len(meta.get('description', ''))} chars")
        print(f"      Type: {meta.get('type', 'Unknown')}")
        print()
    
    # Save subset
    subset_data = {
        "created_at": datetime.now().isoformat(),
        "total_entries": len(subset),
        "is_subset": True,
        "original_count": len(entries),
        "entries": subset
    }
    
    print(f"💾 Saving subset to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(subset_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Subset saved: {len(subset)} entries")
    print()
    print("Next steps:")
    print(f"   1. Process images: python stage2_process_images.py --input {output_path} --image-dir /Users/ericstevens/workspace/lights/images")
    print(f"   2. Generate audio: python stage3_generate_audio.py --input winter_lights_subset_with_photos.json")
    print(f"   3. Insert to DB: python stage4_insert_to_dynamodb.py --input winter_lights_subset_with_audio.json")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
