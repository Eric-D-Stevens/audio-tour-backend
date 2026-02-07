#!/usr/bin/env python3
"""
Generate Winter Lights S3 data file.
Creates a JSON file with all TTPlaceInfo objects ready for S3.

Usage:
    python generate_winter_lights_s3_file.py \
        --input winter_lights_with_audio.json \
        --bucket tensortours-content-us-west-2 \
        --key winter-lights/places.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False
    print("⚠️  boto3 not available. Install with: pip install boto3")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
try:
    from tensortours.models.tour import TTPlaceInfo, TourType
    HAS_MODELS = True
except ImportError as e:
    HAS_MODELS = False
    print(f"⚠️  Cannot import models: {e}")
    sys.exit(1)


def upload_to_s3(local_path: Path, bucket: str, key: str) -> bool:
    """Upload file to S3."""
    if not HAS_BOTO:
        print("❌ boto3 not available")
        return False
    
    try:
        s3 = boto3.client('s3')
        s3.upload_file(
            str(local_path),
            bucket,
            key,
            ExtraArgs={
                'ContentType': 'application/json',
                'CacheControl': 'max-age=3600'  # 1 hour cache
            }
        )
        print(f"✅ Uploaded to s3://{bucket}/{key}")
        return True
        
    except ClientError as e:
        print(f"❌ S3 upload failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error uploading to S3: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Generate Winter Lights S3 data file")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to JSON with audio (from Stage 3)")
    parser.add_argument("--bucket", type=str, default="tensortours-content-us-west-2",
                        help="S3 bucket name")
    parser.add_argument("--key", type=str, default="winter-lights/places.json",
                        help="S3 key path")
    parser.add_argument("--output", type=str, default="winter_lights_s3_data.json",
                        help="Local output file path")
    parser.add_argument("--upload", action="store_true",
                        help="Upload to S3 after generating")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)
    
    print(f"🚀 Generating Winter Lights S3 data file")
    print(f"   Input: {input_path}")
    print(f"   Output: {output_path}")
    print()
    
    # Load the data
    print("📂 Loading data...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entries = data.get('entries', [])
    print(f"   Found {len(entries)} entries")
    
    # Extract place_info objects
    print("📝 Extracting place info...")
    places = []
    for entry in entries:
        place_info_data = entry.get('place_info')
        if place_info_data:
            try:
                # Validate it's a proper TTPlaceInfo
                place = TTPlaceInfo.model_validate(place_info_data)
                # Use mode='json' to serialize datetime objects properly
                places.append(place.model_dump(mode='json'))
            except Exception as e:
                print(f"   ⚠️  Error validating place {place_info_data.get('place_id', 'unknown')}: {e}")
                continue
    
    print(f"   Extracted {len(places)} places")
    
    # Create output structure
    output_data = {
        "version": "1.0",
        "count": len(places),
        "event": "Portland Winter Lights Festival",
        "places": places
    }
    
    # Save locally
    print(f"\n💾 Saving to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    file_size = output_path.stat().st_size / 1024
    print(f"✅ Saved ({file_size:.1f} KB)")
    
    # Upload to S3 if requested
    if args.upload:
        print(f"\n📤 Uploading to S3...")
        if upload_to_s3(output_path, args.bucket, args.key):
            print(f"\n✅ Complete!")
            print(f"   S3 URL: s3://{args.bucket}/{args.key}")
            print(f"   CloudFront: https://d2g5o5njd6p5e.cloudfront.net/{args.key}")
        else:
            print("\n❌ Upload failed")
            sys.exit(1)
    else:
        print(f"\n✅ File generated locally: {output_path}")
        print(f"   To upload, run with --upload flag")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
