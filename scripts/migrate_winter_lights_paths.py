#!/usr/bin/env python3
"""
Migrate Winter Lights content to winter-lights/ prefix paths.

This script:
1. Reads winter_lights_with_audio.json
2. Moves S3 objects from root paths to winter-lights/ prefixed paths
3. Updates the JSON file with new paths
4. Re-uploads the updated places.json to S3

Usage:
    python migrate_winter_lights_paths.py \
        --input winter_lights_with_audio.json \
        --output winter_lights_migrated.json \
        --bucket tensortours-content-us-west-2 \
        --cloudfront-domain d2g5o5njd6p5e.cloudfront.net
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
import re

try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False
    print("⚠️  boto3 not available. Install with: pip install boto3")


def copy_s3_object(s3_client, source_bucket: str, source_key: str, dest_bucket: str, dest_key: str) -> bool:
    """Copy an S3 object from source to destination."""
    try:
        copy_source = {
            'Bucket': source_bucket,
            'Key': source_key
        }
        s3_client.copy(copy_source, dest_bucket, dest_key)
        return True
    except ClientError as e:
        print(f"   ❌ Failed to copy s3://{source_bucket}/{source_key} to s3://{dest_bucket}/{dest_key}: {e}")
        return False


def delete_s3_object(s3_client, bucket: str, key: str) -> bool:
    """Delete an S3 object."""
    try:
        s3_client.delete_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        print(f"   ❌ Failed to delete s3://{bucket}/{key}: {e}")
        return False


def s3_exists(s3_client, bucket: str, key: str) -> bool:
    """Check if an S3 object exists."""
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError:
        return False


def migrate_entry(entry: Dict, s3_client, bucket: str, cloudfront_domain: str, dry_run: bool = False) -> Dict:
    """Migrate a single entry's files to winter-lights/ prefix."""
    place_id = entry['place_info']['place_id']
    print(f"\n🔄 Processing {place_id}")
    
    # Track if we need to update paths
    updated = False
    
    # 1. Migrate photos
    photos = entry.get('photos', [])
    for i, photo in enumerate(photos):
        old_s3_url = photo.get('s3_url', '')
        if old_s3_url and 'winter-lights/' not in old_s3_url:
            # Extract old key from s3://bucket/key
            match = re.match(r's3://([^/]+)/(.+)', old_s3_url)
            if match:
                old_bucket = match.group(1)
                old_key = match.group(2)
                new_key = f"winter-lights/{old_key}"
                
                if not dry_run:
                    # Copy to new location
                    if s3_exists(s3_client, old_bucket, old_key):
                        if copy_s3_object(s3_client, old_bucket, old_key, bucket, new_key):
                            # Delete old object
                            delete_s3_object(s3_client, old_bucket, old_key)
                            print(f"   ✅ Migrated photo {i}: {old_key} -> {new_key}")
                        else:
                            print(f"   ⚠️  Failed to migrate photo {i}")
                    else:
                        print(f"   ⚠️  Source photo {i} not found: {old_key}")
                else:
                    print(f"   [DRY RUN] Would migrate photo {i}: {old_key} -> {new_key}")
                
                # Update URLs in entry
                new_s3_url = f"s3://{bucket}/{new_key}"
                new_cloudfront_url = f"https://{cloudfront_domain}/{new_key}"
                photo['s3_url'] = new_s3_url
                photo['cloudfront_url'] = new_cloudfront_url
                updated = True
    
    # 2. Migrate audio
    audio = entry.get('audio')
    if audio:
        old_s3_url = audio.get('s3_url', '')
        if old_s3_url and 'winter-lights/' not in old_s3_url:
            match = re.match(r's3://([^/]+)/(.+)', old_s3_url)
            if match:
                old_bucket = match.group(1)
                old_key = match.group(2)
                new_key = f"winter-lights/{old_key}"
                
                if not dry_run:
                    if s3_exists(s3_client, old_bucket, old_key):
                        if copy_s3_object(s3_client, old_bucket, old_key, bucket, new_key):
                            delete_s3_object(s3_client, old_bucket, old_key)
                            print(f"   ✅ Migrated audio: {old_key} -> {new_key}")
                        else:
                            print(f"   ⚠️  Failed to migrate audio")
                    else:
                        print(f"   ⚠️  Source audio not found: {old_key}")
                else:
                    print(f"   [DRY RUN] Would migrate audio: {old_key} -> {new_key}")
                
                new_s3_url = f"s3://{bucket}/{new_key}"
                new_cloudfront_url = f"https://{cloudfront_domain}/{new_key}"
                audio['s3_url'] = new_s3_url
                audio['cloudfront_url'] = new_cloudfront_url
                updated = True
    
    # 3. Migrate script (if script_text exists, upload it; if not, just update paths)
    script = entry.get('script')
    if script:
        old_s3_url = script.get('s3_url', '')
        if old_s3_url and 'winter-lights/' not in old_s3_url:
            match = re.match(r's3://([^/]+)/(.+)', old_s3_url)
            if match:
                old_bucket = match.group(1)
                old_key = match.group(2)
                new_key = f"winter-lights/{old_key}"
                script_text = script.get('text', '')
                
                if script_text and not dry_run:
                    # Upload script text to new location
                    try:
                        s3_client.put_object(
                            Bucket=bucket,
                            Key=new_key,
                            Body=script_text.encode('utf-8'),
                            ContentType='text/plain'
                        )
                        print(f"   ✅ Uploaded script: {new_key}")
                        
                        # Delete old script file if it exists
                        if s3_exists(s3_client, old_bucket, old_key):
                            delete_s3_object(s3_client, old_bucket, old_key)
                            print(f"   ✅ Deleted old script: {old_key}")
                    except ClientError as e:
                        print(f"   ⚠️  Failed to upload script: {e}")
                elif dry_run:
                    print(f"   [DRY RUN] Would upload script to: {new_key}")
                
                new_s3_url = f"s3://{bucket}/{new_key}"
                new_cloudfront_url = f"https://{cloudfront_domain}/{new_key}"
                script['s3_url'] = new_s3_url
                script['cloudfront_url'] = new_cloudfront_url
                updated = True
    elif not script:
        # No script entry but check for text in audio.script_text or metadata
        text_content = None
        if entry.get('audio') and entry['audio'].get('script_text'):
            text_content = entry['audio']['script_text']
        elif entry.get('metadata', {}).get('description'):
            text_content = entry['metadata']['description']
        
        if text_content:
            place_id = entry['place_info']['place_id']
            place_name = entry['place_info'].get('place_name', '')
            new_key = f"winter-lights/scripts/{place_id}_art.txt"
            
            if not dry_run:
                try:
                    s3_client.put_object(
                        Bucket=bucket,
                        Key=new_key,
                        Body=text_content.encode('utf-8'),
                        ContentType='text/plain'
                    )
                    print(f"   ✅ Created script from audio.script_text: {new_key}")
                except ClientError as e:
                    print(f"   ⚠️  Failed to upload script: {e}")
            else:
                print(f"   [DRY RUN] Would create script from audio.script_text: {new_key}")
            
            # Create script entry
            entry['script'] = {
                "script_id": f"script_{place_id}",
                "place_id": place_id,
                "place_name": place_name,
                "tour_type": "art",
                "model_info": {
                    "provider": "openai",
                    "model": "gpt-4",
                    "prompt_version": "1.0"
                },
                "s3_url": f"s3://{bucket}/{new_key}",
                "cloudfront_url": f"https://{cloudfront_domain}/{new_key}",
                "text": text_content,
                "word_count": len(text_content.split())
            }
            updated = True
    
    if updated:
        print(f"   ✅ Entry updated with new paths")
    else:
        print(f"   ℹ️  No changes needed (already at winter-lights/ paths or no files)")
    
    return entry


def upload_to_s3(s3_client, local_path: Path, s3_key: str, bucket: str) -> bool:
    """Upload a file to S3."""
    try:
        s3_client.upload_file(str(local_path), bucket, s3_key)
        return True
    except ClientError as e:
        print(f"❌ S3 upload failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Migrate Winter Lights content to winter-lights/ prefix")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to winter_lights_with_audio.json")
    parser.add_argument("--output", type=str, default="winter_lights_migrated.json",
                        help="Output JSON file path")
    parser.add_argument("--bucket", type=str, default="tensortours-content-us-west-2",
                        help="S3 bucket name")
    parser.add_argument("--cloudfront-domain", type=str,
                        default="d2g5o5njd6p5e.cloudfront.net",
                        help="CloudFront domain")
    parser.add_argument("--upload-places", action="store_true",
                        help="Also upload updated places.json to S3")
    parser.add_argument("--places-key", type=str, default="winter-lights/places.json",
                        help="S3 key for places.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without making changes")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to N entries (for testing)")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)
    
    if not HAS_BOTO:
        print("❌ Error: boto3 required for S3 operations")
        sys.exit(1)
    
    print(f"🚀 Starting migration")
    print(f"   Input: {input_path}")
    print(f"   Output: {output_path}")
    print(f"   Bucket: {args.bucket}")
    print(f"   CloudFront: {args.cloudfront_domain}")
    print(f"   Dry run: {args.dry_run}")
    print()
    
    # Load data
    print("📂 Loading data...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entries = data.get('entries', [])
    print(f"   Found {len(entries)} entries")
    
    if args.limit:
        entries = entries[:args.limit]
        print(f"   Limited to {args.limit} entries for testing")
    
    print()
    
    # Initialize S3 client
    s3_client = boto3.client('s3')
    
    # Process each entry
    migrated_entries = []
    success_count = 0
    error_count = 0
    
    for i, entry in enumerate(entries, 1):
        print(f"{'='*60}")
        print(f"Entry {i}/{len(entries)}")
        
        try:
            migrated_entry = migrate_entry(
                entry, 
                s3_client, 
                args.bucket, 
                args.cloudfront_domain,
                dry_run=args.dry_run
            )
            migrated_entries.append(migrated_entry)
            success_count += 1
        except Exception as e:
            print(f"   ❌ Error processing entry: {e}")
            import traceback
            traceback.print_exc()
            migrated_entries.append(entry)  # Keep original on error
            error_count += 1
    
    # Save updated JSON
    print(f"\n{'='*60}")
    print("💾 Saving migrated data...")
    output_data = {
        'metadata': data.get('metadata', {}),
        'entries': migrated_entries
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Saved to {output_path}")
    
    # Upload places.json if requested
    if args.upload_places and not args.dry_run:
        print("\n📤 Uploading places.json...")
        
        # Generate places.json content
        places_data = {
            "version": "1.0",
            "count": len(migrated_entries),
            "event": "Portland Winter Lights Festival",
            "places": [entry.get('place_info', {}) for entry in migrated_entries]
        }
        
        # Save temporarily
        temp_places_path = Path("temp_places.json")
        with open(temp_places_path, "w", encoding="utf-8") as f:
            json.dump(places_data, f, indent=2)
        
        # Upload to S3
        if upload_to_s3(s3_client, temp_places_path, args.places_key, args.bucket):
            print(f"   ✅ Uploaded to s3://{args.bucket}/{args.places_key}")
            print(f"   CloudFront: https://{args.cloudfront_domain}/{args.places_key}")
        else:
            print(f"   ❌ Failed to upload places.json")
        
        # Clean up
        temp_places_path.unlink()
    
    # Summary
    print(f"\n{'='*60}")
    print("✅ Migration complete!")
    print(f"   Total: {len(entries)}")
    print(f"   Successful: {success_count}")
    print(f"   Errors: {error_count}")
    if args.dry_run:
        print("   [DRY RUN - No actual changes made]")


if __name__ == "__main__":
    main()
