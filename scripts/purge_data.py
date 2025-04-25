#!/usr/bin/env python
"""
Script to purge all data from TensorTours content bucket and DynamoDB tour table.
This is useful for resetting the application state during development or testing.
"""

import os
import boto3
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file if present
load_dotenv()

# Hardcoded resource names from CDK infrastructure
# Using us-west-2 as the default region based on other resources in the stack
CONTENT_BUCKET = "tensortours-content-us-west-2"
TOUR_TABLE = "TTTourTable"

def purge_s3_bucket(bucket_name):
    """Delete all objects in the specified S3 bucket."""
    if not bucket_name:
        logger.error("No bucket name provided. Set CONTENT_BUCKET environment variable.")
        return

    try:
        logger.info(f"Connecting to S3 bucket: {bucket_name}")
        s3 = boto3.resource('s3')
        bucket = s3.Bucket(bucket_name)
        
        # Count objects first
        count = 0
        for _ in bucket.objects.all():
            count += 1
        
        if count == 0:
            logger.info(f"Bucket {bucket_name} is already empty.")
            return
        
        logger.info(f"Preparing to delete {count} objects from bucket {bucket_name}...")
        
        # Delete objects
        confirmation = input(f"Are you sure you want to delete all {count} objects from {bucket_name}? (yes/no): ")
        if confirmation.lower() != "yes":
            logger.info("Operation cancelled.")
            return
        
        # Delete objects
        logger.info(f"Deleting all objects from bucket {bucket_name}...")
        bucket.objects.all().delete()
        logger.info(f"Successfully deleted all objects from bucket {bucket_name}.")
    
    except Exception as e:
        logger.error(f"Error purging S3 bucket: {str(e)}")

def purge_dynamodb_table(table_name):
    """Delete all items from the specified DynamoDB table."""
    if not table_name:
        logger.error("No table name provided. Set TOUR_TABLE environment variable.")
        return
    
    try:
        logger.info(f"Connecting to DynamoDB table: {table_name}")
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table(table_name)
        
        # Get table info to check primary key
        table_description = dynamodb.meta.client.describe_table(TableName=table_name)
        key_schema = table_description['Table']['KeySchema']
        
        # Extract the primary key and sort key (if any)
        primary_key = None
        sort_key = None
        for key in key_schema:
            if key['KeyType'] == 'HASH':
                primary_key = key['AttributeName']
            elif key['KeyType'] == 'RANGE':
                sort_key = key['AttributeName']
        
        if not primary_key:
            logger.error("Could not determine primary key for table.")
            return
        
        # Scan table to get items
        logger.info(f"Scanning table {table_name} for items...")
        response = table.scan()
        items = response.get('Items', [])
        
        total_items = len(items)
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
            total_items = len(items)
        
        if total_items == 0:
            logger.info(f"Table {table_name} is already empty.")
            return
        
        logger.info(f"Found {total_items} items in table {table_name}.")
        
        # Confirm deletion
        confirmation = input(f"Are you sure you want to delete all {total_items} items from {table_name}? (yes/no): ")
        if confirmation.lower() != "yes":
            logger.info("Operation cancelled.")
            return
        
        # Delete items
        logger.info(f"Deleting {total_items} items from table {table_name}...")
        with table.batch_writer() as batch:
            for item in items:
                key = {primary_key: item[primary_key]}
                if sort_key:
                    key[sort_key] = item[sort_key]
                batch.delete_item(Key=key)
        
        logger.info(f"Successfully deleted all items from table {table_name}.")
    
    except Exception as e:
        logger.error(f"Error purging DynamoDB table: {str(e)}")

def main():
    """Main function to run the purge operations."""
    print("TensorTours Data Purge Utility")
    print("-" * 30)
    
    # Check environment variables
    if not CONTENT_BUCKET:
        logger.warning("CONTENT_BUCKET environment variable not set.")
    else:
        print(f"S3 Bucket: {CONTENT_BUCKET}")
    
    if not TOUR_TABLE:
        logger.warning("TOUR_TABLE environment variable not set.")
    else:
        print(f"DynamoDB Table: {TOUR_TABLE}")
    
    print("-" * 30)
    print("This utility will purge ALL data from the specified resources.")
    print("This action cannot be undone.")
    print("-" * 30)
    
    # Ask for confirmation
    confirmation = input("Do you want to continue? (yes/no): ")
    if confirmation.lower() != "yes":
        logger.info("Operation cancelled.")
        return
    
    # Purge S3 bucket
    if CONTENT_BUCKET:
        purge_s3_bucket(CONTENT_BUCKET)
    
    # Purge DynamoDB table
    if TOUR_TABLE:
        purge_dynamodb_table(TOUR_TABLE)
    
    print("-" * 30)
    print("Purge operation completed.")

if __name__ == "__main__":
    main()
