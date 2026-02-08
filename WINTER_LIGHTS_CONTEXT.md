# Winter Lights Pipeline - Current State & Context Handoff

## Summary

The Winter Lights data pipeline for TensorTours has been completely fixed and migrated. All 192 Winter Lights entries now have their content properly organized under the `winter-lights/` prefix in S3, with updated DynamoDB entries and a new metadata field for storing original scraped data.

---

## Current Architecture

### S3 Content Structure

All Winter Lights content is now stored under the `winter-lights/` prefix in the `tensortours-content-us-west-2` bucket:

```
winter-lights/
├── photos/{place_id}/{idx}.jpg     # Photos for each installation
├── audio/{place_id}_art.mp3        # Generated audio narration
├── scripts/{place_id}_art.txt      # Script text files
└── places.json                     # Index file for getPlaces Lambda
```

**Example URLs:**
- Photo: `https://d2g5o5njd6p5e.cloudfront.net/winter-lights/photos/pwl_cosmic_cuddle_22058/0.jpg`
- Audio: `https://d2g5o5njd6p5e.cloudfront.net/winter-lights/audio/pwl_cosmic_cuddle_22058_art.mp3`
- Script: `https://d2g5o5njd6p5e.cloudfront.net/winter-lights/scripts/pwl_cosmic_cuddle_22058_art.txt`

### DynamoDB Table (`TTTourTable`)

Each entry has the following structure:

```json
{
  "place_id": "pwl_cosmic_cuddle_22058",
  "tour_type": "event:portland-winter-lights",
  "status": "completed",
  "created_at": "2026-02-08T...",
  "data": "{serialized JSON of place_info, photos, script, audio}",
  "metadata": "{serialized JSON string of original scraped data}"
}
```

**Important:** The `metadata` field is a **JSON-encoded string** containing the original scraped data (title, description, scraped_at timestamp, etc.). When reading from DynamoDB, you'll need to parse this string to access the metadata.

---

## Metadata Field (NEW)

### What It Contains

The `metadata` field in DynamoDB stores a JSON string of the original scraped data from the Portland Winter Lights Festival website. Example contents:

```json
{
  "title": "Cosmic Cuddle",
  "description": "Meet a giant sparkling illuminated cuttlefish...",
  "scraped_at": "2026-02-01T12:00:00Z",
  "source_url": "https://...",
  "original_data": { ... }
}
```

### How to Access It

In the backend (`tour_table.py`):
- The `TourTableItem.load()` method automatically deserializes the metadata string
- Access via `tour_item.metadata` (will be a Dict after loading)

In the frontend:
- When calling `getTour` Lambda, the metadata is included in the response
- Parse it as JSON if you need to access nested fields

### Implementation Details

**Backend Model (`src/tensortours/services/tour_table.py`):**

```python
class TourTableItem(BaseModel):
    ...
    metadata: Optional[str] = None  # JSON-encoded string

    def dump(self) -> Dict:
        result = { ... }
        if self.metadata is not None:
            result["metadata"] = self.metadata  # Stored as string
        return result
```

**Pipeline Script (`scripts/stage4_insert_to_dynamodb.py`):**

```python
# Metadata is serialized before being passed to TourTableItem
tour_item = TourTableItem(
    ...
    metadata=json.dumps(metadata) if metadata else None
)
```

---

## Lambda Handlers

### `getTour` (`src/tensortours/lambda_handlers/get_tour.py`)

- Retrieves a specific tour by `place_id` and `tour_type`
- Returns a `TTour` object including photos, script, and audio
- Script and audio URLs point to CloudFront (under `winter-lights/`)
- Metadata is included in the response

### `getPlaces` (`src/tensortours/lambda_handlers/get_places.py`)

- Loads `winter-lights/places.json` from S3
- Returns list of `TTPlaceInfo` objects for all Winter Lights installations
- This is the index file used by the frontend to show the list of places

---

## Pipeline Stages

### Stage 1: Transform Data
`scripts/stage1_transform_data.py`
- Transforms raw scraped data into standardized format
- Creates `place_info` with proper structure

### Stage 2: Process Images
`scripts/stage2_process_images.py`
- Downloads and processes photos
- Uploads to S3 at `winter-lights/photos/{place_id}/{idx}.jpg`

### Stage 3: Generate Audio
`scripts/stage3_generate_audio.py`
- Generates audio using AWS Polly
- Uploads audio to `winter-lights/audio/{place_id}_art.mp3`
- Uploads script text to `winter-lights/scripts/{place_id}_art.txt`

### Stage 4: Insert to DynamoDB
`scripts/stage4_insert_to_dynamodb.py`
- Creates `TourTableItem` with all data
- Serializes metadata as JSON string
- Inserts into `TTTourTable`

### Migration Script
`scripts/migrate_winter_lights_paths.py`
- One-time script used to migrate existing data
- Moves S3 objects from root paths to `winter-lights/` prefix
- Uploads missing script text files from `script.text` field
- Updates JSON entries and re-uploads places.json

---

## Key Files for Frontend

### `winter-lights/places.json`
S3 path: `s3://tensortours-content-us-west-2/winter-lights/places.json`
CloudFront URL: `https://d2g5o5njd6p5e.cloudfront.net/winter-lights/places.json`

Contains the list of all Winter Lights installations for the getPlaces endpoint.

### JSON Entry Structure

```json
{
  "place_info": {
    "place_id": "pwl_cosmic_cuddle_22058",
    "place_name": "Cosmic Cuddle",
    "place_editorial_summary": "A giant illuminated cuttlefish",
    "place_address": "Portland, OR",
    "place_primary_type": "event",
    "place_types": ["event", "light_display"],
    "place_location": { "lat": 45.5, "lng": -122.6 }
  },
  "photos": [{
    "photo_id": "pwl_cosmic_cuddle_22058_0",
    "place_id": "pwl_cosmic_cuddle_22058",
    "cloudfront_url": "https://d2g5o5njd6p5e.cloudfront.net/winter-lights/photos/pwl_cosmic_cuddle_22058/0.jpg",
    "s3_url": "s3://tensortours-content-us-west-2/winter-lights/photos/pwl_cosmic_cuddle_22058/0.jpg",
    "attribution": { "displayName": "Portland Winter Lights Festival" },
    "size_width": 1200,
    "size_height": 800,
    "index": 0
  }],
  "audio": {
    "place_id": "pwl_cosmic_cuddle_22058",
    "script_id": "script_pwl_cosmic_cuddle_22058",
    "cloudfront_url": "https://d2g5o5njd6p5e.cloudfront.net/winter-lights/audio/pwl_cosmic_cuddle_22058_art.mp3",
    "s3_url": "s3://tensortours-content-us-west-2/winter-lights/audio/pwl_cosmic_cuddle_22058_art.mp3",
    "script_text": "Welcome to Cosmic Cuddle...",
    "word_count": 82,
    "model_info": { "provider": "aws_polly", "voice": "Amy", "engine": "generative" }
  },
  "script": {
    "script_id": "script_pwl_cosmic_cuddle_22058",
    "place_id": "pwl_cosmic_cuddle_22058",
    "place_name": "Cosmic Cuddle",
    "tour_type": "art",
    "s3_url": "s3://tensortours-content-us-west-2/winter-lights/scripts/pwl_cosmic_cuddle_22058_art.txt",
    "cloudfront_url": "https://d2g5o5njd6p5e.cloudfront.net/winter-lights/scripts/pwl_cosmic_cuddle_22058_art.txt",
    "text": "Welcome to Cosmic Cuddle...",
    "word_count": 82
  },
  "metadata": {
    "title": "Cosmic Cuddle",
    "description": "Meet a giant sparkling illuminated cuttlefish...",
    "scraped_at": "2026-02-01T12:00:00Z"
  }
}
```

---

## Infrastructure Details

### AWS Account
- Account ID: `934308926622`
- Profile: `aws-profile-1`

### Resources
- **S3 Bucket**: `tensortours-content-us-west-2`
- **DynamoDB Table**: `TTTourTable` (us-west-2)
- **CloudFront Distribution**: `d2g5o5njd6p5e.cloudfront.net`
  - Distribution ID: `E3GIQDVR3F1CQF`

---

## Current Status

✅ **All tasks completed:**
- Migration script fixed to use `script.text` field
- All 192 entries migrated to `winter-lights/` paths in S3
- Script text files uploaded to S3 at `winter-lights/scripts/`
- DynamoDB entries updated with new paths and `tour_type: event:portland-winter-lights`
- Metadata field added to `TourTableItem` model
- Metadata serialized as JSON string in DynamoDB
- `places.json` uploaded to `winter-lights/places.json`
- CloudFront cache invalidated

---

## Next Steps for Frontend

1. **Verify Lambda responses** - Test `getTour` and `getPlaces` to confirm paths are correct
2. **Update frontend URL construction** - If frontend was constructing URLs manually, update to use the paths from Lambda responses
3. **Display metadata** - If desired, parse the metadata JSON to display original scraped descriptions or timestamps
4. **Test audio playback** - Verify audio files load from `winter-lights/audio/` paths
5. **Test script loading** - Verify script text files load from `winter-lights/scripts/` paths

---

## Important Notes

1. **All Winter Lights content is under `winter-lights/` prefix** - No content remains at root paths
2. **Metadata is a JSON string in DynamoDB** - Must be parsed when reading
3. **TourType is `EVENT_PORTLAND_WINTER_LIGHTS`** - Not `ART`
4. **Script text is in `script.text`** - Not `script.script_text`
5. **place_id format**: `pwl_{snake_case_name}_{random_id}` (e.g., `pwl_cosmic_cuddle_22058`)
