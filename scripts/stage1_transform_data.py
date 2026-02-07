#!/usr/bin/env python3
"""
Stage 1: Data Transformation Script
Transform raw Portland Winter Lights JSON into TTPlaceInfo-compatible format.

Usage:
    python stage1_transform_data.py \
        --input /Users/ericstevens/workspace/lights/all_content.json \
        --output winter_lights_transformed.json \
        --image-dir /Users/ericstevens/workspace/lights/images
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


def slugify_title(title: str) -> str:
    """Convert title to URL-friendly slug."""
    # Remove special characters, convert to lowercase, replace spaces with underscores
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[-\s]+', '_', slug)
    return slug.strip('_')


def generate_place_id(title: str, post_id: int) -> str:
    """Generate unique place_id like pwl_morrison_bridge_lights_6814."""
    slug = slugify_title(title)
    return f"pwl_{slug}_{post_id}"


def validate_images(images: List[str], image_dir: Path, place_id: str) -> List[str]:
    """Validate that referenced images exist in the image directory."""
    valid_images = []
    missing_images = []
    
    for img_path in images:
        # Extract filename from path (e.g., "images/Electric-Dandelions-Liquid-PXL-01.jpg")
        filename = Path(img_path).name
        full_path = image_dir / filename
        
        if full_path.exists():
            valid_images.append(filename)
        else:
            missing_images.append(filename)
    
    if missing_images:
        print(f"  ⚠️  {place_id}: Missing {len(missing_images)} images: {missing_images[:3]}...")
    
    return valid_images


def transform_entry(raw_entry: Dict, image_dir: Path) -> Optional[Dict]:
    """Transform a single raw entry to TTPlaceInfo format."""
    try:
        post_id = raw_entry.get("post_id")
        title = raw_entry.get("title", "")
        
        if not title or not post_id:
            print(f"  ⚠️  Skipping entry: missing title or post_id")
            return None
        
        # Generate place_id
        place_id = generate_place_id(title, post_id)
        
        # Extract coordinates
        coordinates = raw_entry.get("coordinates", {}) or {}
        lat = coordinates.get("lat", 0.0) if coordinates else 0.0
        lng = coordinates.get("lng", 0.0) if coordinates else 0.0
        
        if lat == 0.0 or lng == 0.0:
            print(f"  ⚠️  {place_id}: Missing coordinates, skipping")
            return None
        
        # Validate images
        raw_images = raw_entry.get("images", []) or []
        if raw_images:
            valid_images = validate_images(raw_images, image_dir, place_id)
        else:
            valid_images = []
            print(f"  ℹ️  {place_id}: No images")
        
        # Build place info
        place_info = {
            "place_id": place_id,
            "place_name": title,
            "place_editorial_summary": raw_entry.get("excerpt", "")[:200],
            "place_address": raw_entry.get("address", f"{lat},{lng}"),
            "place_primary_type": "event",
            "place_types": ["event", "light_display", raw_entry.get("type", "art").lower().replace(" ", "_")],
            "place_location": {
                "latitude": lat,
                "longitude": lng
            },
            "retrieved_at": datetime.now().isoformat()
        }
        
        # Build metadata
        metadata = {
            "post_id": post_id,
            "title_url": raw_entry.get("title_url", ""),
            "dates": raw_entry.get("dates"),
            "type": raw_entry.get("type", ""),
            "map_number": raw_entry.get("map_number", ""),
            "zones": raw_entry.get("zones", []),
            "artists": raw_entry.get("artists", []),
            "artist_socials": raw_entry.get("artist_socials", []),
            "thumbnail": raw_entry.get("thumbnail", ""),
            "images": valid_images,  # Local image filenames
            "description": raw_entry.get("description", "")
        }
        
        return {
            "place_info": place_info,
            "metadata": metadata,
            "image_count": len(valid_images)
        }
        
    except Exception as e:
        print(f"  ❌ Error transforming entry: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Transform Winter Lights data to TTPlaceInfo format")
    parser.add_argument("--input", type=str, required=True, help="Path to all_content.json")
    parser.add_argument("--output", type=str, default="winter_lights_transformed.json", 
                        help="Output JSON file path")
    parser.add_argument("--image-dir", type=str, required=True, 
                        help="Path to images directory")
    parser.add_argument("--limit", type=int, default=None, 
                        help="Limit to N entries (for testing)")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    image_dir = Path(args.image_dir)
    
    # Validate paths
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)
    
    if not image_dir.exists():
        print(f"❌ Error: Image directory not found: {image_dir}")
        sys.exit(1)
    
    print(f"🚀 Starting Stage 1: Data Transformation")
    print(f"   Input: {input_path}")
    print(f"   Image dir: {image_dir}")
    print(f"   Output: {output_path}")
    print()
    
    # Load raw data
    print("📂 Loading raw data...")
    with open(input_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    
    print(f"   Found {len(raw_data)} entries")
    
    # Apply limit if specified
    if args.limit:
        raw_data = raw_data[:args.limit]
        print(f"   Limited to {args.limit} entries for testing")
    
    print()
    
    # Transform each entry
    print("🔧 Transforming entries...")
    transformed = []
    errors = 0
    
    for i, entry in enumerate(raw_data, 1):
        if i % 50 == 0:
            print(f"   Progress: {i}/{len(raw_data)}")
        
        result = transform_entry(entry, image_dir)
        if result:
            transformed.append(result)
        else:
            errors += 1
    
    print()
    print("=" * 60)
    print(f"✅ Transformation complete!")
    print(f"   Successfully transformed: {len(transformed)} entries")
    print(f"   Errors/skipped: {errors}")
    
    # Calculate statistics
    total_images = sum(e["image_count"] for e in transformed)
    with_description = sum(1 for e in transformed if e["metadata"]["description"])
    
    print(f"   Total valid images: {total_images}")
    print(f"   Entries with descriptions: {with_description}/{len(transformed)}")
    print()
    
    # Sample entries
    print("📋 Sample entries:")
    for i, entry in enumerate(transformed[:3], 1):
        pi = entry["place_info"]
        print(f"   {i}. {pi['place_id']}")
        print(f"      Name: {pi['place_name']}")
        print(f"      Location: ({pi['place_location']['latitude']}, {pi['place_location']['longitude']})")
        print(f"      Images: {entry['image_count']}")
        print(f"      Description length: {len(entry['metadata']['description'])} chars")
        print()
    
    # Save output
    print(f"💾 Saving to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "transformed_at": datetime.now().isoformat(),
            "total_entries": len(transformed),
            "entries": transformed
        }, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved {len(transformed)} entries to {output_path}")
    
    # Generate validation report
    report_path = output_path.with_suffix(".report.txt")
    print(f"📝 Validation report: {report_path}")
    with open(report_path, "w") as f:
        f.write(f"Winter Lights Data Transformation Report\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"=" * 60 + "\n\n")
        f.write(f"Total entries: {len(transformed)}\n")
        f.write(f"Total images: {total_images}\n")
        f.write(f"Entries with descriptions: {with_description}\n\n")
        
        f.write("Place IDs:\n")
        for entry in transformed:
            f.write(f"  - {entry['place_info']['place_id']}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
