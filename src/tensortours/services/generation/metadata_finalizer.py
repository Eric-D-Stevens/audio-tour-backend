"""Stage 3: Metadata finalization — merge input + generated data into a PoiInsertRequest."""

from ...models.generation import GenerationConfig, PoiInputData
from ...models.poi import PoiInsertRequest
from .tour_agent import TourGenerationResult


def finalize(
    poi_data: PoiInputData,
    generation_result: TourGenerationResult,
    config: GenerationConfig,
) -> PoiInsertRequest:
    """Merge pipeline inputs and outputs into a complete PoiInsertRequest.

    The resulting object is ready to be inserted (or used to UPDATE) the poi table.
    Status is left as 'pending' — audio generation is a separate future step.
    """
    summary = generation_result.summary or poi_data.summary or ""

    return PoiInsertRequest(
        title=poi_data.title,
        lat=poi_data.lat,
        lng=poi_data.lng,
        source_ids=poi_data.source_ids,
        location_meta=poi_data.location_meta,
        summary=summary,
        overall_score=generation_result.overall_score,
        scores_vector=generation_result.scores_vector,
        photo_urls=poi_data.photo_urls,
        scripts={config.language: generation_result.script},
        audio_urls={},
    )
