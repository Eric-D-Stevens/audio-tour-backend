#!/usr/bin/env python3
"""
Stage 3: Audio Generation using AWS Polly
Generate audio from descriptions using the existing AWSPollyClient.

Usage:
    python stage3_generate_audio.py \
        --input winter_lights_with_photos.json \
        --output winter_lights_with_audio.json
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import re
import html

try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False
    print("⚠️  boto3 not available. Install with: pip install boto3")

# Import the existing AWSPollyClient from the codebase
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
try:
    from tensortours.services.aws_poly import AWSPollyClient
    HAS_POLLY_CLIENT = True
except ImportError as e:
    HAS_POLLY_CLIENT = False
    print(f"⚠️  Cannot import AWSPollyClient: {e}")


def clean_description(description: str) -> str:
    """
    Clean description for TTS:
    - Remove HTML tags
    - Fix spacing issues
    - Remove URLs
    - Normalize whitespace
    """
    if not description:
        return ""
    
    # Unescape HTML entities
    text = html.unescape(description)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    
    # Fix multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Strip whitespace
    text = text.strip()
    
    return text


def optimize_for_tts(description: str, place_name: str) -> str:
    """
    Optimize description for TTS output.
    Creates a 90-120 second script (150-200 words).
    """
    # Clean the description
    cleaned = clean_description(description)
    
    if not cleaned:
        # Fallback if no description
        return f"Welcome to {place_name}. This light installation is part of the Portland Winter Lights Festival. Enjoy the display!"
    
    # Add opening
    opening = f"Welcome to {place_name}. "
    
    # Add closing
    closing = " Enjoy the magical display!"
    
    # Combine
    script = opening + cleaned + closing
    
    # Limit to ~200 words (good for 90-120 seconds)
    words = script.split()
    if len(words) > 200:
        # Find a good break point (end of sentence)
        truncated = ' '.join(words[:200])
        # Find last period
        last_period = truncated.rfind('.')
        if last_period > 150:
            script = truncated[:last_period + 1] + closing
        else:
            script = truncated + "..." + closing
    
    return script


def upload_script_to_s3(script_text: str, s3_key: str, bucket: str) -> bool:
    """Upload script text to S3."""
    if not HAS_BOTO:
        print("    ⚠️  boto3 not available, skipping S3 upload")
        return False
    
    try:
        s3_client = boto3.client('s3')
        s3_client.put_object(
            Bucket=bucket,
            Key=s3_key,
            Body=script_text.encode('utf-8'),
            ContentType='text/plain'
        )
        return True
    except ClientError as e:
        print(f"    ❌ S3 script upload failed: {e}")
        return False
    except Exception as e:
        print(f"    ❌ Error uploading script to S3: {e}")
        return False


def generate_audio_for_entry(
    entry: Dict, 
    polly_client: AWSPollyClient,
    bucket: str,
    cloudfront_domain: str
) -> Optional[Dict]:
    """Generate audio for a single entry using AWS Polly."""
    place_id = entry['place_info']['place_id']
    place_name = entry['place_info']['place_name']
    description = entry['metadata'].get('description', '')
    
    print(f"\n🎙️  Processing {place_id}")
    
    if not description:
        print(f"   ℹ️  No description, skipping audio generation")
        entry['audio'] = None
        return entry
    
    # Optimize description for TTS
    script_text = optimize_for_tts(description, place_name)
    word_count = len(script_text.split())
    print(f"   📝 Script: {word_count} words")
    
    try:
        # Define S3 key for audio
        audio_key = f"winter-lights/audio/{place_id}_art.mp3"
        
        # Generate audio using AWS Polly
        print(f"   🎵 Generating audio with Polly...")
        result = polly_client.synthesize_speech_to_s3(
            text=script_text,
            bucket=bucket,
            key=audio_key,
            voice_id="Amy",  # Same voice as standard tours
            engine="generative",  # Use generative engine (matches standard flow)
            metadata={
                "place_id": place_id,
                "place_name": place_name,
                "word_count": str(word_count),
                "generated_for": "portland_winter_lights_event"
            }
        )
        
        # Create CloudFront URL
        cloudfront_url = f"https://{cloudfront_domain}/{audio_key}"
        s3_url = f"s3://{bucket}/{audio_key}"
        
        # Build audio object
        entry['audio'] = {
            "place_id": place_id,
            "cloudfront_url": cloudfront_url,
            "s3_url": s3_url,
            "script_text": script_text,
            "word_count": word_count,
            "model_info": {
                "provider": "aws_polly",
                "voice": "Amy",
                "engine": "generative"
            }
        }
        
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
            "s3_url": f"s3://{bucket}/winter-lights/scripts/{place_id}_art.txt",
            "cloudfront_url": f"https://{cloudfront_domain}/winter-lights/scripts/{place_id}_art.txt",
            "script_text": script_text,
            "word_count": word_count
        }
        
        # Upload script text to S3
        script_key = f"winter-lights/scripts/{place_id}_art.txt"
        if upload_script_to_s3(script_text, script_key, bucket):
            print(f"   ✅ Script uploaded: s3://{bucket}/{script_key}")
        else:
            print(f"   ⚠️  Script upload failed")
        
        print(f"   ✅ Audio generated: {cloudfront_url}")
        return entry
        
    except Exception as e:
        print(f"   ❌ Error generating audio: {e}")
        entry['audio'] = None
        entry['script'] = None
        return entry


def main():
    parser = argparse.ArgumentParser(description="Generate audio for Winter Lights using AWS Polly")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to transformed JSON (from Stage 2)")
    parser.add_argument("--output", type=str, default="winter_lights_with_audio.json",
                        help="Output JSON file path")
    parser.add_argument("--bucket", type=str, default="tensortours-content-us-west-2",
                        help="S3 bucket name")
    parser.add_argument("--cloudfront-domain", type=str, 
                        default="d2g5o5njd6p5e.cloudfront.net",
                        help="CloudFront domain")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to N entries (for testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process but don't generate audio")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    # Validate paths
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)
    
    if not HAS_BOTO or not HAS_POLLY_CLIENT:
        print("❌ Error: Required libraries not available")
        sys.exit(1)
    
    print(f"🚀 Starting Stage 3: Audio Generation")
    print(f"   Input: {input_path}")
    print(f"   S3 bucket: {args.bucket}")
    print(f"   CloudFront: {args.cloudfront_domain}")
    print(f"   Dry run: {args.dry_run}")
    print()
    
    # Load data
    print("📂 Loading data...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entries = data.get('entries', [])
    print(f"   Found {len(entries)} entries")
    
    # Apply limit if specified
    if args.limit:
        entries = entries[:args.limit]
        print(f"   Limited to {args.limit} entries for testing")
    
    print()
    
    # Initialize Polly client
    if not args.dry_run:
        print("🔧 Initializing AWS Polly client...")
        polly_client = AWSPollyClient(voice_id="Amy", engine="standard")
        print("   ✅ Polly client ready")
        print()
    
    # Process each entry
    processed = []
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, entry in enumerate(entries, 1):
        print(f"{'='*60}")
        print(f"Entry {i}/{len(entries)}")
        
        if args.dry_run:
            # Just check if description exists
            description = entry['metadata'].get('description', '')
            if description:
                cleaned = clean_description(description)
                word_count = len(cleaned.split())
                print(f"   📝 Would generate audio: ~{word_count} words")
                success_count += 1
            else:
                print(f"   ℹ️  No description, would skip")
                skip_count += 1
            processed.append(entry)
        else:
            try:
                result = generate_audio_for_entry(
                    entry, 
                    polly_client, 
                    args.bucket, 
                    args.cloudfront_domain
                )
                processed.append(result)
                
                if result.get('audio'):
                    success_count += 1
                elif result['metadata'].get('description'):
                    error_count += 1
                else:
                    skip_count += 1
                    
            except Exception as e:
                print(f"   ❌ Error processing entry: {e}")
                entry['audio'] = None
                processed.append(entry)
                error_count += 1
    
    print()
    print("=" * 60)
    print(f"✅ Audio generation complete!")
    print(f"   Total: {len(processed)}")
    print(f"   Generated: {success_count}")
    print(f"   Skipped (no description): {skip_count}")
    print(f"   Errors: {error_count}")
    
    # Save output
    print(f"\n💾 Saving to {output_path}...")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_entries": len(processed),
            "audio_generated": success_count,
            "skipped": skip_count,
            "errors": error_count,
            "s3_bucket": args.bucket,
            "cloudfront_domain": args.cloudfront_domain,
            "dry_run": args.dry_run,
            "entries": processed
        }, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved to {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
