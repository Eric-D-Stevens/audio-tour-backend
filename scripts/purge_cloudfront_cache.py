#!/usr/bin/env python

"""
Utility script to purge CloudFront cache for TensorTours preview content.
This creates an invalidation request for all preview content or specific paths.

Usage:
    python purge_cloudfront_cache.py --all-preview             # Purge all preview content
    python purge_cloudfront_cache.py --city new-york           # Purge specific city
    python purge_cloudfront_cache.py --city new-york --tour-type history  # Purge specific city and tour type
"""

import argparse
import boto3
import logging
import os
import time
from typing import List

# Set up logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get distribution ID from environment or hardcode for convenience
CLOUDFRONT_DISTRIBUTION_ID = os.environ.get(
    "CLOUDFRONT_DISTRIBUTION_ID", 
    "E3GIQDVR3F1CQF"  # Distribution ID for d2g5o5njd6p5e.cloudfront.net
)


def create_invalidation(paths: List[str]) -> None:
    """
    Create a CloudFront invalidation for the specified paths.
    
    Args:
        paths: List of paths to invalidate, e.g. ['/preview/*', '/preview/new-york/*']
    """
    if not paths:
        logger.error("No paths specified for invalidation")
        return
    
    # Create a timestamp-based caller reference to ensure uniqueness
    caller_reference = f"purge-{int(time.time())}"
    
    try:
        cloudfront = boto3.client('cloudfront')
        
        # Create the invalidation
        response = cloudfront.create_invalidation(
            DistributionId=CLOUDFRONT_DISTRIBUTION_ID,
            InvalidationBatch={
                'Paths': {
                    'Quantity': len(paths),
                    'Items': paths
                },
                'CallerReference': caller_reference
            }
        )
        
        invalidation_id = response['Invalidation']['Id']
        logger.info(f"Created invalidation {invalidation_id} for paths: {paths}")
        logger.info(f"Invalidation status: {response['Invalidation']['Status']}")
        logger.info("Note: Invalidation may take 5-10 minutes to complete")
        
    except Exception as e:
        logger.error(f"Failed to create invalidation: {str(e)}")


def main():
    """Parse arguments and create appropriate invalidations."""
    parser = argparse.ArgumentParser(description='Purge CloudFront cache for TensorTours preview content.')
    
    # Add arguments
    parser.add_argument('--all-preview', action='store_true', help='Purge all preview content')
    parser.add_argument('--city', type=str, help='City to purge (e.g., "new-york")')
    parser.add_argument('--tour-type', type=str, help='Tour type to purge (e.g., "history")')
    
    args = parser.parse_args()
    
    # Determine which paths to invalidate
    paths_to_invalidate = []
    
    if args.all_preview:
        paths_to_invalidate.append('/preview/*')
    elif args.city and args.tour_type:
        paths_to_invalidate.append(f'/preview/{args.city}/{args.tour_type}/*')
    elif args.city:
        paths_to_invalidate.append(f'/preview/{args.city}/*')
    else:
        # Default - no args provided
        paths_to_invalidate.append('/preview/*')
        logger.info("No specific paths provided, invalidating all preview content")
    
    # Create the invalidation
    create_invalidation(paths_to_invalidate)


if __name__ == "__main__":
    main()
