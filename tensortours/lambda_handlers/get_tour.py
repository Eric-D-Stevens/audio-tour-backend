import logging
import json
from typing import Optional

from ..models.api import GetPregeneratedTourRequest, GetPregeneratedTourResponse
from ..services.tour_table import TourTableClient, TourTableItem
from ..models.tour import TTour
from ..utils.general_utils import get_tour_table_client

logger = logging.getLogger(__name__)

def handler(event, context):
    """Get a tour item by place_id and tour_type."""
    request = GetPregeneratedTourRequest.model_validate(event['body'])
    tour_table_client: TourTableClient = get_tour_table_client()

    tour_item: Optional[TourTableItem] = tour_table_client.get_item(request.place_id, request.tour_type)
    if tour_item is None:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Tour not found'})
        }

    tour = TTour(
        place_id=tour_item.place_id,
        tour_type=tour_item.tour_type,
        place_info=tour_item.place_info,
        photos=tour_item.photos,
        script=tour_item.script,
        audio=tour_item.audio
    )
    tour_response = GetPregeneratedTourResponse(tour=tour)
    return {
        'statusCode': 200,
        'body': tour_response.model_dump_json()
    }


