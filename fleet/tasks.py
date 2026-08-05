# yourapp/tasks.py
from celery import shared_task
from .services import sync_vehicles_from_therentos

@shared_task(bind=True)
def sync_vehicles_task(self, asset_type='car'):
    return sync_vehicles_from_therentos(asset_type=asset_type)