from functools import lru_cache

from ..services.tour_table import TourTableClient


@lru_cache
def get_tour_table_client() -> TourTableClient:
    return TourTableClient()
