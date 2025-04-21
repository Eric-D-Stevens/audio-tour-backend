from functools import lru_cache

from ..services.tour_table import TourTableClient
from ..services.user_event_table import UserEventTableClient


@lru_cache
def get_tour_table_client() -> TourTableClient:
    return TourTableClient()


@lru_cache
def get_user_event_table_client() -> UserEventTableClient:
    return UserEventTableClient()
