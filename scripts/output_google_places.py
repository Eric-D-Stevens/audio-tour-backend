import json
import os

from dotenv import load_dotenv

from tensortours.services.google_places import GooglePlacesClient

client = GooglePlacesClient(os.environ.get('GOOGLE_MAPS_API_KEY'))

def output_place_details(place_id):
    details = client.get_place_details(place_id)
    print(json.dumps(details, indent=2))

def compare_outputs():
    places = client.search_nearby(
        latitude=37.7694,
        longitude=-122.4862,
        radius=1500,
        include_types=["tourist_attraction", "museum"],
        exclude_types=[],
        max_results=5
    )
    place = places['places'][0]
    print(f"\nPlace: {place['displayName']['text']}")
    print("==================PLACE SEARCH NEARBY================")
    print(json.dumps(place, indent=2))
    print("==================PLACE DETAILS================")
    output_place_details(place['id'])

if __name__ == "__main__":
    compare_outputs()
    
    