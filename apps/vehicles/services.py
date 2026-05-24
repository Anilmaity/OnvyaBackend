from apps.common.services import AgencyScopedService
from apps.vehicles.models import Vehicle


class VehicleService(AgencyScopedService):
    model = Vehicle
