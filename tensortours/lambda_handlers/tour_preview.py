"""
Tour preview Lambda handler for TensorTours backend.
Provides a preview mode for guest users to sample the tour experience.
"""
import json
import logging
import os
import boto3
from typing import Dict, Any, List, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3 = boto3.client('s3')

# Environment variables
BUCKET_NAME = os.environ.get('CONTENT_BUCKET_NAME')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')


def handler(event, context):
    """
    Lambda handler for tour preview functionality.
    
    Expected request format:
    {
        "place_id": "Google Place ID",
        "preview_type": "demo" or "sample"
    }
    """
    logger.info(f"Received tour preview request")
    
    # Handle API Gateway proxy integration
    if 'body' in event:
        try:
            body = json.loads(event['body'])
        except (TypeError, json.JSONDecodeError):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid request body'})
            }
    else:
        body = event
    
    # Extract parameters
    place_id = body.get('place_id')
    if not place_id:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing required parameter: place_id'})
        }
    
    preview_type = body.get('preview_type', 'demo')  # 'demo' or 'sample'
    
    try:
        # Check if tour exists for this place
        tour = get_existing_tour(place_id)
        
        if tour:
            # If tour exists, return it (possibly with limitations for preview)
            preview = create_preview_from_tour(tour, preview_type)
            return {
                'statusCode': 200,
                'body': json.dumps(preview)
            }
        else:
            # No tour exists, return a template/demo tour
            demo_tour = get_demo_tour(preview_type)
            return {
                'statusCode': 200,
                'body': json.dumps(demo_tour)
            }
    except Exception as e:
        logger.exception(f"Error generating preview: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to generate preview', 'details': str(e)})
        }


def get_existing_tour(place_id: str) -> Optional[Dict[str, Any]]:
    """Get existing tour from S3 if available."""
    if not BUCKET_NAME:
        return None
    
    tour_key = f"tours/{place_id}/tour.json"
    
    try:
        response = s3.get_object(Bucket=BUCKET_NAME, Key=tour_key)
        tour_data = json.loads(response['Body'].read().decode('utf-8'))
        return tour_data
    except Exception as e:
        logger.info(f"No existing tour found for place {place_id}: {str(e)}")
        return None


def create_preview_from_tour(tour: Dict[str, Any], preview_type: str) -> Dict[str, Any]:
    """Create a preview version of an existing tour."""
    # For 'demo' type, return the full tour
    if preview_type == 'demo':
        return tour
    
    # For 'sample' type, return a limited version
    preview = dict(tour)
    
    # Limit to just the first segment or two
    if 'audio_segments' in preview and len(preview['audio_segments']) > 1:
        preview['audio_segments'] = preview['audio_segments'][:1]
        preview['is_preview'] = True
        
    # Limit the duration
    if 'duration_minutes' in preview:
        preview['duration_minutes'] = min(preview['duration_minutes'], 5)
        
    return preview


def get_demo_tour(preview_type: str) -> Dict[str, Any]:
    """Return a demo tour when no actual tour exists."""
    # Default demo tour data
    demo_tour = {
        "tour_id": "demo_tour",
        "place_id": "demo_place",
        "place_name": "TensorTours Demo",
        "tour_type": "demo",
        "duration_minutes": 5,
        "language": "en",
        "is_demo": True,
        "audio_segments": [
            {
                "segment_id": "demo_1",
                "title": "Welcome to TensorTours",
                "url": f"https://{CLOUDFRONT_DOMAIN}/demo/welcome.mp3" if CLOUDFRONT_DOMAIN else "https://example.com/demo.mp3",
                "duration_seconds": 60,
                "transcript": "Welcome to TensorTours, your AI-powered audio guide to the world's most interesting places."
            }
        ],
        "photos": [
            f"https://{CLOUDFRONT_DOMAIN}/demo/photo1.jpg" if CLOUDFRONT_DOMAIN else "https://example.com/demo1.jpg",
            f"https://{CLOUDFRONT_DOMAIN}/demo/photo2.jpg" if CLOUDFRONT_DOMAIN else "https://example.com/demo2.jpg"
        ]
    }
    
    return demo_tour
