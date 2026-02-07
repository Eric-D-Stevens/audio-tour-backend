#!/usr/bin/env python3
"""
Stage 2: Image Processing & Upload
Deduplicate, optimize, and upload Winter Lights images to S3.

Usage:
    python stage2_process_images.py \
        --input winter_lights_transformed.json \
        --image-dir /Users/ericstevens/workspace/lights/images \
        --output winter_lights_with_photos.json
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️  PIL not available. Install with: pip install Pillow")

try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False
    print("⚠️  boto3 not available. Install with: pip install boto3")


def compute_image_hash(image_path: Path) -> str:
    """Compute MD5 hash of image file for deduplication."""
    hash_md5 = hashlib.md5()
    with open(image_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def deduplicate_images(image_dir: Path, image_filenames: List[str], place_id: str) -> List[str]:
    """
    Deduplicate images by content hash.
    Returns list of unique image filenames, preferring non-suffixed versions.
    """
    seen_hashes: Set[str] = set()
    unique_images: List[str] = []
    
    # Sort to prefer non-suffixed versions (e.g., "image.jpg" before "image_1.jpg")
    sorted_images = sorted(image_filenames, key=lambda x: (x.count('_'), x))
    
    for filename in sorted_images:
        image_path = image_dir / filename
        if not image_path.exists():
            continue
        
        try:
            file_hash = compute_image_hash(image_path)
            if file_hash not in seen_hashes:
                seen_hashes.add(file_hash)
                unique_images.append(filename)
            else:
                print(f"    🔄 {place_id}: Skipping duplicate {filename}")
        except Exception as e:
            print(f"    ⚠️  {place_id}: Error hashing {filename}: {e}")
    
    return unique_images


def resize_image(image_path: Path, output_path: Path, max_size: int = 1200) -> bool:
    """Resize image to max dimensions while maintaining aspect ratio."""
    if not HAS_PIL:
        # Just copy if PIL not available
        import shutil
        shutil.copy(image_path, output_path)
        return True
    
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary (for PNG with transparency)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            
            # Calculate new dimensions
            width, height = img.size
            if width > max_size or height > max_size:
                if width > height:
                    new_width = max_size
                    new_height = int(height * (max_size / width))
                else:
                    new_height = max_size
                    new_width = int(width * (max_size / height))
                
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                print(f"      📐 Resized {width}x{height} → {new_width}x{new_height}")
            
            # Save as JPEG with optimization
            img.save(output_path, 'JPEG', quality=85, optimize=True, progressive=True)
            return True
            
    except Exception as e:
        print(f"    ❌ Error resizing {image_path}: {e}")
        return False


def upload_to_s3(local_path: Path, s3_key: str, bucket: str) -> Optional[str]:
    """Upload file to S3 and return CloudFront URL."""
    if not HAS_BOTO:
        print("    ⚠️  boto3 not available, skipping S3 upload")
        return None
    
    try:
        s3_client = boto3.client('s3')
        s3_client.upload_file(
            str(local_path),
            bucket,
            s3_key,
            ExtraArgs={
                'ContentType': 'image/jpeg',
                'CacheControl': 'max-age=31536000'
            }
        )
        
        # Build CloudFront URL
        # Note: CloudFront domain should be set via environment variable
        import os
        cloudfront_domain = os.environ.get('CLOUDFRONT_DOMAIN', 'd2g5o5njd6p5e.cloudfront.net')
        cloudfront_url = f"https://{cloudfront_domain}/{s3_key}"
        
        return cloudfront_url
        
    except ClientError as e:
        print(f"    ❌ S3 upload failed: {e}")
        return None
    except Exception as e:
        print(f"    ❌ Error uploading to S3: {e}")
        return None


def process_entry(entry: Dict, image_dir: Path, bucket: str, temp_dir: Path) -> Dict:
    """Process images for a single entry."""
    place_id = entry['place_info']['place_id']
    raw_images = entry['metadata']['images']
    
    print(f"\n📸 Processing {place_id}")
    
    if not raw_images:
        print(f"   ℹ️  No images to process")
        entry['photos'] = []
        return entry
    
    # Step 1: Deduplicate
    print(f"   🔍 Deduplicating {len(raw_images)} images...")
    unique_images = deduplicate_images(image_dir, raw_images, place_id)
    print(f"   ✅ {len(unique_images)} unique images")
    
    # Step 2: Resize and upload (limit to first 3 images per location)
    photos = []
    for idx, filename in enumerate(unique_images[:3]):  # Max 3 photos
        print(f"   📤 Uploading image {idx + 1}/{min(len(unique_images), 3)}: {filename}")
        
        local_path = image_dir / filename
        s3_key = f"photos/{place_id}/{idx}.jpg"
        
        # Resize to temp file
        temp_path = temp_dir / f"{place_id}_{idx}.jpg"
        if not resize_image(local_path, temp_path):
            continue
        
        # Upload to S3
        cloudfront_url = upload_to_s3(temp_path, s3_key, bucket)
        
        if cloudfront_url:
            photos.append({
                'photo_id': f"{place_id}_{idx}",
                'place_id': place_id,
                'cloudfront_url': cloudfront_url,
                's3_url': f"s3://{bucket}/{s3_key}",
                'attribution': {'displayName': 'Portland Winter Lights Festival'},
                'size_width': 1200,
                'size_height': 800,
                'index': idx
            })
            
            # Clean up temp file
            temp_path.unlink(missing_ok=True)
    
    entry['photos'] = photos
    entry['metadata']['image_count'] = len(photos)
    
    print(f"   ✅ Uploaded {len(photos)} photos")
    return entry


def main():
    parser = argparse.ArgumentParser(description="Process and upload Winter Lights images")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to transformed JSON (from Stage 1)")
    parser.add_argument("--image-dir", type=str, required=True,
                        help="Path to images directory")
    parser.add_argument("--output", type=str, default="winter_lights_with_photos.json",
                        help="Output JSON file path")
    parser.add_argument("--bucket", type=str, default="tensortours-content-us-west-2",
                        help="S3 bucket name")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to N entries (for testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process but don't upload to S3")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    image_dir = Path(args.image_dir)
    output_path = Path(args.output)
    temp_dir = Path("/tmp/winter_lights_images")
    
    # Validate paths
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)
    
    if not image_dir.exists():
        print(f"❌ Error: Image directory not found: {image_dir}")
        sys.exit(1)
    
    # Create temp directory
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"🚀 Starting Stage 2: Image Processing & Upload")
    print(f"   Input: {input_path}")
    print(f"   Image dir: {image_dir}")
    print(f"   S3 bucket: {args.bucket}")
    print(f"   Dry run: {args.dry_run}")
    print()
    
    # Load transformed data
    print("📂 Loading transformed data...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entries = data['entries']
    print(f"   Found {len(entries)} entries")
    
    # Apply limit if specified
    if args.limit:
        entries = entries[:args.limit]
        print(f"   Limited to {args.limit} entries for testing")
    
    print()
    
    # Process each entry
    processed = []
    total_photos = 0
    
    for i, entry in enumerate(entries, 1):
        print(f"\n{'='*60}")
        print(f"Entry {i}/{len(entries)}")
        
        try:
            if args.dry_run:
                # Just deduplicate and count
                raw_images = entry['metadata']['images']
                if raw_images:
                    unique = deduplicate_images(image_dir, raw_images, entry['place_info']['place_id'])
                    entry['photos'] = [{'index': j} for j in range(min(len(unique), 3))]
                    total_photos += len(entry['photos'])
                else:
                    entry['photos'] = []
                processed.append(entry)
            else:
                result = process_entry(entry, image_dir, args.bucket, temp_dir)
                processed.append(result)
                total_photos += len(result.get('photos', []))
                
        except Exception as e:
            print(f"   ❌ Error processing entry: {e}")
            import traceback
            traceback.print_exc()
            # Still add entry but without photos
            entry['photos'] = []
            processed.append(entry)
    
    print()
    print("=" * 60)
    print(f"✅ Image processing complete!")
    print(f"   Processed: {len(processed)} entries")
    print(f"   Total photos: {total_photos}")
    
    # Save output
    print(f"\n💾 Saving to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "processed_at": datetime.now().isoformat(),
            "total_entries": len(processed),
            "total_photos": total_photos,
            "s3_bucket": args.bucket,
            "dry_run": args.dry_run,
            "entries": processed
        }, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved to {output_path}")
    
    # Cleanup temp directory
    if not args.dry_run:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"🧹 Cleaned up temp directory")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
