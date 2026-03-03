-- Extensions
create extension if not exists postgis;      -- geography type + GIST spatial indexing
create extension if not exists vector;       -- pgvector: dedupe_embedding column

-- Points of Interest
-- System-managed table: rows are written by the generation pipeline, not directly by end users.
-- No RLS applied — Lambda connects via service role (bypasses RLS) and sets no per-user context.
-- Revisit if user-owned POI rows are added in a future phase.
create table if not exists poi (

    -- Identity & lifecycle
    id                  uuid          primary key default gen_random_uuid(),
    status              text          not null
                                      check (status in ('pending', 'processing', 'ready', 'failed')),
    created_at          timestamptz   not null default now(),
    updated_at          timestamptz   not null default now(),
    generation_version  int           not null default 1,
    generation_error    jsonb         null,     -- e.g. {"stage":"audio","message":"...","retry_count":2}

    -- Source identity / deduplication
    -- Keyed by source system, e.g. {"wikidata":"Q123","osm":"node/456","google":"ChIJ..."}
    source_ids          jsonb         not null default '{}'::jsonb,
    canonical_id        uuid          null references poi(id),  -- points to canonical row if merged

    -- Geospatial (PostGIS geography; SRID 4326 = WGS-84)
    location            geography(Point,4326) not null,
    -- Generated columns derived from location — no sync risk, convenient for API serialization
    lat                 double precision generated always as (st_y(location::geometry)) stored,
    lng                 double precision generated always as (st_x(location::geometry)) stored,
    -- Freeform location metadata — structure varies by region and data source.
    -- Store whatever the source provides: display string, country, city, region, postal code, etc.
    -- No enforced schema; keys are advisory. Omit keys that don't apply.
    location_meta       jsonb             null,

    -- Map payload
    title               text          not null,
    overall_score       real          not null default 0,
    scores_vector       jsonb         not null default '{}'::jsonb,  -- category subscores

    -- Preview + tour content
    summary             text          null,
    photo_urls          jsonb         not null default '{}'::jsonb,  -- {"thumbnail":"...","images":["..."]}
    scripts             jsonb         not null default '{}'::jsonb,  -- {"en":"...","es":"..."}
    audio_urls          jsonb         not null default '{}'::jsonb,  -- {"en":"https://cdn/.../en.mp3"}

    -- Optional: vector deduplication (embed title + summary; enable fuzzy-dedupe when ready)
    dedupe_embedding    vector(1536)  null
);

-- Indexes

-- 1) Geo lookup — primary access pattern for map load (nearby POIs)
create index if not exists poi_location_gist
    on poi using gist (location);

-- 2) Source-ID deduplication — fast exact match when ingesting external data
create index if not exists poi_source_ids_gin
    on poi using gin (source_ids);

-- 3) Status filter — pipeline polling for pending/processing rows
create index if not exists poi_status_idx
    on poi (status);

-- 4) Score sort — top-N queries (ORDER BY overall_score DESC LIMIT N)
create index if not exists poi_overall_score_idx
    on poi (overall_score desc);

-- 5) Vector similarity (IVFFLAT) — uncomment once fuzzy dedupe is in use.
--    Requires at least a few thousand rows before IVFFLAT is effective.
-- create index poi_dedupe_embedding_ivfflat
--     on poi using ivfflat (dedupe_embedding vector_cosine_ops)
--     with (lists = 100);
