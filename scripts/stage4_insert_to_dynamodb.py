#!/usr/bin/env python3
"""
Stage 4: DynamoDB Data Insertion
Insert complete Winter Lights tour records into DynamoDB.

Usage:
    python stage4_insert_to_dynamodb.py \
        --input winter_lights_with_audio.json \
        --table-name tensortours-tours
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

try:
    import boto3
    from botocore.exceptions import ClientError
    from mypy_boto3_dynamodb.service_resource import Table
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False
    print("⚠️  boto3 not available. Install with: pip install boto3")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
try:
    from tensortours.models.tour import TTour, TTPlaceInfo, TTPlacePhotos, TTScript, TTAudio, TourType
    from tensortours.services.tour_table import TourTableItem, GenerationStatus
    HAS_MODELS = True
except ImportError as e:
    HAS_MODELS = False
    print(f"⚠️  Cannot import models: {e}")


def create_tour_table_item(entry: Dict) -> Optional[TourTableItem]:
    """Create a TourTableItem from a transformed entry."""
    try:
        place_info_data = entry['place_info']
        metadata = entry.get('metadata', {})
        photos_data = entry.get('photos', [])
        audio_data = entry.get('audio')
        script_data = entry.get('script')
        
        # Create TTPlaceInfo
        place_info = TTPlaceInfo(
            place_id=place_info_data['place_id'],
            place_name=place_info_data['place_name'],
            place_editorial_summary=place_info_data.get('place_editorial_summary', ''),
            place_address=place_info_data.get('place_address', ''),
            place_primary_type=place_info_data.get('place_primary_type', 'event'),
            place_types=place_info_data.get('place_types', ['event', 'light_display']),
            place_location=place_info_data.get('place_location', {})
        )
        
        # Create TTPlacePhotos list
        photos = []
        for photo in photos_data:
            photos.append(TTPlacePhotos(
                photo_id=photo.get('photo_id', ''),
                place_id=photo.get('place_id', place_info.place_id),
                cloudfront_url=photo.get('cloudfront_url', ''),
                s3_url=photo.get('s3_url', ''),
                attribution=photo.get('attribution', {}),
                size_width=photo.get('size_width', 1200),
                size_height=photo.get('size_height', 800)
            ))
        
        # Create TTScript if available
        script = None
        if script_data:
            script = TTScript(
                script_id=script_data.get('script_id', f"script_{place_info.place_id}"),
                place_id=place_info.place_id,
                place_name=place_info.place_name,
                tour_type=TourType.EVENT_PORTLAND_WINTER_LIGHTS,
                model_info=script_data.get('model_info', {}),
                s3_url=script_data.get('s3_url', ''),
                cloudfront_url=script_data.get('cloudfront_url', '')
            )
        
        # Create TTAudio if available
        audio = None
        if audio_data:
            audio = TTAudio(
                place_id=place_info.place_id,
                script_id=script.script_id if script else f"script_{place_info.place_id}",
                cloudfront_url=audio_data.get('cloudfront_url', ''),
                s3_url=audio_data.get('s3_url', ''),
                model_info=audio_data.get('model_info', {})
            )
        
        # Determine status
        status = GenerationStatus.COMPLETED if (script and audio) else GenerationStatus.IN_PROGRESS
        
        # Create TourTableItem
        tour_item = TourTableItem(
            place_id=place_info.place_id,
            tour_type=TourType.EVENT_PORTLAND_WINTER_LIGHTS,
            place_info=place_info,
            status=status,
            photos=photos if photos else None,
            script=script,
            audio=audio
        )
        
        return tour_item
        
    except Exception as e:
        print(f"   ❌ Error creating TourTableItem: {e}")
        import traceback
        traceback.print_exc()
        return None


def insert_to_dynamodb(tour_item: TourTableItem, table: Table) -> bool:
    """Insert a TourTableItem into DynamoDB."""
    try:
        # Convert to DynamoDB format
        item_data = tour_item.dump()
        
        # Put item
        table.put_item(Item=item_data)
        return True
        
    except ClientError as e:
        print(f"   ❌ DynamoDB error: {e}")
        return False
    except Exception as e:
        print(f"   ❌ Error inserting item: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Insert Winter Lights data into DynamoDB")
    parser.add_argument("--input", type=str, required=True,
                        help="Path to JSON with audio (from Stage 3)")
    parser.add_argument("--table-name", type=str, default="TTTourTable",
                        help="DynamoDB table name")
    parser.add_argument("--region", type=str, default="us-west-2",
                        help="AWS region")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to N entries (for testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Process but don't insert")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"❌ Error: Input file not found: {input_path}")
        sys.exit(1)
    
    if not HAS_BOTO or not HAS_MODELS:
        print("❌ Error: Required libraries not available")
        sys.exit(1)
    
    print(f"🚀 Starting Stage 4: DynamoDB Insertion")
    print(f"   Input: {input_path}")
    print(f"   Table: {args.table_name}")
    print(f"   Region: {args.region}")
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
    
    # Initialize DynamoDB
    if not args.dry_run:
        print("🔧 Initializing DynamoDB...")
        dynamodb = boto3.resource('dynamodb', region_name=args.region)
        table = dynamodb.Table(args.table_name)
        
        # Test connection
        try:
            table.meta.client.describe_table(TableName=args.table_name)
            print(f"   ✅ Connected to table: {args.table_name}")
        except ClientError as e:
            print(f"   ❌ Error connecting to table: {e}")
            sys.exit(1)
        print()
    
    # Process each entry
    inserted = 0
    skipped = 0
    errors = 0
    
    for i, entry in enumerate(entries, 1):
        place_id = entry['place_info']['place_id']
        
        print(f"{'='*60}")
        print(f"Entry {i}/{len(entries)}: {place_id}")
        
        if args.dry_run:
            tour_item = create_tour_table_item(entry)
            if tour_item:
                print(f"   ✅ Would insert: {tour_item.status.value}")
                print(f"      Photos: {len(tour_item.photos) if tour_item.photos else 0}")
                print(f"      Script: {'Yes' if tour_item.script else 'No'}")
                print(f"      Audio: {'Yes' if tour_item.audio else 'No'}")
                inserted += 1
            else:
                print(f"   ❌ Would skip (validation error)")
                errors += 1
        else:
            try:
                tour_item = create_tour_table_item(entry)
                if tour_item:
                    if insert_to_dynamodb(tour_item, table):
                        print(f"   ✅ Inserted successfully")
                        inserted += 1
                    else:
                        print(f"   ❌ Insert failed")
                        errors += 1
                else:
                    print(f"   ❌ Failed to create TourTableItem")
                    errors += 1
                    
            except Exception as e:
                print(f"   ❌ Error: {e}")
                errors += 1
    
    print()
    print("=" * 60)
    print(f"✅ DynamoDB insertion complete!")
    print(f"   Total processed: {len(entries)}")
    print(f"   Inserted: {inserted}")
    print(f"   Errors: {errors}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
