#!/usr/bin/env python3
"""
Quick script to test the GooglePlacesClient.get_place_details method
and print the indented JSON result.
"""

import json
import os
import sys
from dotenv import load_dotenv
from tensortours.services.google_places import GooglePlacesClient

def main():
    # Load environment variables (to get API key if it's in .env)
    load_dotenv()
    
    # Get API key from environment or ask user for it
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        api_key = input("Enter your Google Places API key: ")
    
    # Get place_id from command line or ask user for it
    if len(sys.argv) > 1:
        place_id = sys.argv[1]
    else:
        place_id = input("Enter a place ID: ")
    
    # Initialize the client
    client = GooglePlacesClient(api_key=api_key)
    
    try:
        # Call the get_place_details method
        result = client.get_place_details(place_id)
        
        # Print indented JSON result
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Error retrieving place details: {e}")

if __name__ == "__main__":
    main()
