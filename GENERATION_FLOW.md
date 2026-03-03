# TensorTours: Main Tour Generation Flow

This document describes the current pre-generation pipeline — the flow that fires when a user opens the map and nearby places are discovered. This is **not** the on-demand flow.

---

## High-Level Architecture

```
┌──────────┐      ┌──────────────┐      ┌─────────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Client   │─────▶│  get_places  │─────▶│  SQS Generation Q   │─────▶│  photo_retriever  │─────▶│  SQS Script Q    │
│ (App)     │      │  Lambda      │      │                     │      │  Lambda           │      │                  │
└──────────┘      └──────────────┘      └─────────────────────┘      └──────────────────┘      └────────┬─────────┘
                                                                                                        │
                                                                                                        ▼
                                                                     ┌──────────────────┐      ┌──────────────────┐
                                                                     │  SQS Audio Q     │◀─────│ script_generator │
                                                                     │                  │      │  Lambda          │
                                                                     └────────┬─────────┘      └──────────────────┘
                                                                              │
                                                                              ▼
                                                                     ┌──────────────────┐
                                                                     │ audio_generator   │
                                                                     │  Lambda           │
                                                                     └──────────────────┘
```

There are **four Lambda functions** connected by **three SQS queues** forming a linear pipeline:

1. **`get_places`** — entry point, called by the client
2. **`photo_retriever_handler`** — Stage 1 of the pipeline
3. **`script_generator_handler`** — Stage 2
4. **`audio_generator_handler`** — Stage 3

---

## Step-by-Step Walkthrough

### 1. Client Requests Nearby Places (`get_places`)

**File:** `lambda_handlers/get_places.py`

The mobile app sends a POST with `latitude`, `longitude`, `radius`, `tour_type`, and `max_results`.

#### 1a. Google Places API Search

The handler calls `GooglePlacesClient.search_nearby()` using the Google Places API v1 `searchNearby` endpoint. The place types sent to Google are determined by a static mapping in `TourTypeToGooglePlaceTypes`:

| Tour Type     | Google Place Types Sent                                                                                         |
|---------------|----------------------------------------------------------------------------------------------------------------|
| `history`     | `historical_place`, `monument`, `historical_landmark`, `cultural_landmark`, `sculpture`                        |
| `cultural`    | `art_gallery`, `museum`, `performing_arts_theater`, `cultural_center`, `tourist_attraction`, `cultural_landmark`, `historical_landmark`, `market`, `community_center`, `event_venue`, `historical_place`, `plaza` |
| `art`         | `art_gallery`, `art_studio`, `sculpture`, `museum`, `cultural_center`, `performing_arts_theater`, `opera_house`, `concert_hall`, `philharmonic_hall`, `cultural_landmark` |
| `nature`      | `park`, `national_park`, `state_park`, `botanical_garden`, `garden`, `wildlife_park`, `zoo`, `aquarium`, `beach`, `hiking_area`, `wildlife_refuge`, `observation_deck`, `fishing_pond`, `picnic_ground` |
| `architecture`| `cultural_landmark`, `monument`, `church`, `hindu_temple`, `mosque`, `synagogue`, `stadium`, `opera_house`, `university`, `city_hall`, `courthouse`, `historical_landmark`, `amphitheatre` |

**Key detail:** The API request uses `max_results` (default 20, capped at 20 per Google API page) and does **not** paginate — it's a single request.

#### 1b. Transform to TTPlaceInfo

The raw Google response is transformed into `TTPlaceInfo` objects. Each object captures:
- `place_id`, `place_name`, `place_address`
- `place_primary_type`, `place_types` (list)
- `place_editorial_summary` (may be empty string)
- `place_location` (lat/lng)

**No filtering or ranking happens here.** Every place Google returns is kept.

#### 1c. Check Tour Table & Forward to Generation Queue

For each place, the handler checks `TTTourTable` (DynamoDB) to see if a completed tour already exists for this `(place_id, tour_type)` pair. If not, the place is forwarded to the **Generation SQS Queue** with the full `TTPlaceInfo` serialized in the message body.

The response is returned to the client immediately with all places — the client does not wait for generation to complete.

---

### 2. Photo Retrieval (`photo_retriever_handler`)

**File:** `lambda_handlers/tour_generation_pipeline.py`

Triggered by the Generation SQS Queue. For each message:

1. Creates a `TourTableItem` in DynamoDB with status `IN_PROGRESS` (or skips if already `IN_PROGRESS` / `COMPLETED`)
2. Calls `GooglePlacesClient.get_place_details(place_id)` to get photo references
3. Downloads up to **5 photos** in parallel (ThreadPoolExecutor, 10 workers)
4. Uploads each photo to S3 at `tours/{place_id}/photos/photo_{index}.jpg`
5. Creates `TTPlacePhotos` objects with CloudFront URLs
6. Updates the `TourTableItem` with the photos array
7. Sends the full `TourTableItem` (serialized JSON) to the **Script SQS Queue**

---

### 3. Script Generation (`script_generator_handler`)

**File:** `lambda_handlers/tour_generation_pipeline.py`

Triggered by the Script SQS Queue. For each message:

1. Deserializes the `TourTableItem` from the message
2. Calls `generate_tour_script(place_info, tour_type)` which:
   - Builds a **system prompt** (base + tour-type-specific guidelines)
   - Builds a **user prompt** with the place name, address, types, and editorial summary
   - Calls **OpenAI GPT-4o** (`temperature=0.7`, `max_tokens=6000`)
3. Saves the script text to S3 at `tours/{place_id}/script/{tour_type}_script.txt`
4. Updates the `TourTableItem` with the `TTScript` object
5. Sends the full `TourTableItem` to the **Audio SQS Queue**

#### What the LLM receives as context about the place:

```
place_info.place_name           → e.g. "Powell's City of Books"
place_info.place_address        → e.g. "1005 W Burnside St, Portland, OR 97209"
place_info.place_types          → e.g. ["book_store", "store", "point_of_interest"]
place_info.place_editorial_summary → e.g. "Iconic independent bookstore..." (often empty)
```

That's it. **No web search, no Wikipedia lookup, no additional enrichment.** The LLM generates the script purely from its training data + these four fields.

---

### 4. Audio Generation (`audio_generator_handler`)

**File:** `lambda_handlers/tour_generation_pipeline.py`

Triggered by the Audio SQS Queue. For each message:

1. Deserializes the `TourTableItem` from the message
2. Reads the script text back from S3
3. Calls **AWS Polly** (neural engine, voice `Amy`) to synthesize speech
4. Uploads the MP3 to S3 at `tours/{place_id}/audio/{tour_type}_audio.mp3`
5. Updates the `TourTableItem` with the `TTAudio` object and sets status to `COMPLETED`

---

### 5. Tour Retrieval (`get_tour`)

**File:** `lambda_handlers/get_tour.py`

When the client wants to play a tour, it calls this endpoint with `place_id` and `tour_type`. The handler:

1. Looks up the `TourTableItem` in DynamoDB
2. Returns 404 if not found or if script/audio are still missing (still generating)
3. Returns the full `TTour` object (place_info, photos, script, audio) with CloudFront URLs

---

## Data Flow Summary

```
Google Places API  ──▶  TTPlaceInfo  ──▶  SQS  ──▶  Photos from Google  ──▶  SQS
                                                                                │
                                                                                ▼
                                                     S3 (script.txt)  ◀──  GPT-4o
                                                                                │
                                                                                ▼
                                                     S3 (audio.mp3)   ◀──  AWS Polly
                                                                                │
                                                                                ▼
                                                     DynamoDB (COMPLETED)
```

---

## Known Weaknesses & Why Points Are "Not Great"

### 1. No Filtering or Ranking of Places

**The biggest issue.** Google Places `searchNearby` returns whatever matches the `includedTypes` list, and **every single result is accepted**. There is no:

- **Minimum rating threshold** — a 2.5-star location is treated the same as a 4.8-star one
- **Minimum review count** — a place with 3 reviews is treated the same as one with 5,000
- **Relevance scoring** — no check for whether the place is actually interesting for the given tour type
- **Deduplication** — overlapping type lists (e.g. `cultural_landmark` appears in History, Culture, and Architecture) can cause the same place to appear across tour types, but within a single request there's no dedup logic needed since it's one tour type at a time
- **Distance weighting** — a place at the edge of the radius is treated the same as one right next to the user

The legacy `geolocation.py` handler *does* have an `interestingness_score` function that weights rating (60%), normalized review count (30%), and editorial summary presence (10%), but **the new `get_places.py` handler does not use any scoring at all**.

### 2. Overly Broad Type Lists

Some tour type mappings cast a very wide net:

- **Culture** includes `market`, `community_center`, `event_venue`, `plaza` — these frequently return mundane locations (grocery markets, community halls, parking plazas)
- **Nature** includes `fishing_pond`, `picnic_ground` — these can return unremarkable park amenities
- **Art** includes `concert_hall`, `philharmonic_hall` — these are more performance venues than visual art sites

The broader the type list, the more noise Google returns.

### 3. Minimal Context for Script Generation

The LLM receives only:
- **Place name**
- **Address**
- **Google place types** (machine labels like `tourist_attraction`)
- **Editorial summary** (frequently empty or a single generic sentence)

There is **no**:
- Wikipedia or Wikidata enrichment
- Web search for additional context
- Historical records or cultural databases
- Visitor reviews or notable mentions
- Information about what's physically at the site

This means the LLM is generating scripts almost entirely from its parametric memory. For well-known landmarks this works fine; for lesser-known places, the scripts can be generic, vague, or even inaccurate.

### 4. No Place Validation

There is no step that asks: *"Is this place actually worth visiting on a tour?"* A gas station that happens to be tagged as a `historical_landmark` in Google's data will get a full tour generated for it. There's no:

- LLM-based pre-screening ("Is this place tour-worthy?")
- Heuristic filtering (minimum rating, minimum reviews, must have editorial summary)
- Blocklist for known bad place types (e.g. `gas_station`, `parking`)

### 5. Single API Page, No Pagination

`get_places` makes a single `searchNearby` request capped at 20 results. It cannot:
- Fetch more candidates and then filter down to the best ones
- Use multiple searches with different type subsets to get better coverage

### 6. No Feedback Loop

There is no mechanism to:
- Track which tours users actually listen to vs. skip
- Mark low-quality places/tours for exclusion
- Learn from user behavior to improve place selection over time

### 7. Audio Quality (Minor)

AWS Polly neural voice `Amy` is functional but not particularly engaging for a tour guide experience. The legacy pipeline used Eleven Labs which produces more natural-sounding speech.

---

## File Reference

| File | Role |
|------|------|
| `lambda_handlers/get_places.py` | Entry point — fetches places from Google, forwards to generation queue |
| `lambda_handlers/tour_generation_pipeline.py` | 3-stage pipeline: photo retrieval → script generation → audio generation |
| `lambda_handlers/get_tour.py` | Retrieval endpoint — returns completed tours to the client |
| `services/google_places.py` | Google Places API v1 client (search, details, photos) |
| `services/openai_client.py` | OpenAI API client (GPT-4o completions) |
| `services/aws_poly.py` | AWS Polly TTS client |
| `services/tour_table.py` | DynamoDB tour table client (TTTourTable) |
| `utils/script_utils.py` | Prompt construction and script generation logic |
| `models/tour.py` | Data models: `TourType`, `TTPlaceInfo`, `TTScript`, `TTAudio`, `TTour`, `TourTypeToGooglePlaceTypes` |
| `models/api.py` | API request/response models |

---

## Legacy Flow (geolocation.py)

There is also an older `geolocation.py` handler that has its own parallel flow:
- Its own Google Places search with a different type mapping
- An `interestingness_score` ranking function
- Sends to a separate `TOUR_PREGENERATION_QUEUE_URL` → `tour_pre_generation.py`
- The pre-generation handler uses Eleven Labs for audio instead of Polly
- Stores results in a different DynamoDB table (`PLACES_TABLE_NAME`) with a different schema

This legacy flow and the new pipeline coexist but are **not connected**. The new pipeline (`get_places` → `tour_generation_pipeline`) is the active path for authenticated users.
