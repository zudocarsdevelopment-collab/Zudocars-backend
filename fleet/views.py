from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from .tasks import sync_vehicles_task
from celery.result import AsyncResult
from .services import sync_vehicles_from_therentos
from .models import Vehicle
from .serializers import VehicleSerializer


class VehicleListCreateAPIView(generics.ListCreateAPIView):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer


class VehicleRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer

class SyncVehiclesAPIView(APIView):
    # permission_classes = [IsAdminUser]  # only staff/admin users can trigger this

    def post(self, request):
        asset_type = request.data.get('type', 'car')
        try:
            result = sync_vehicles_from_therentos(asset_type=asset_type)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )
        return Response(result, status=status.HTTP_200_OK)

class SyncStatusAPIView(APIView):
    # permission_classes = [IsAdminUser]

    def get(self, request, task_id):
        result = AsyncResult(task_id)
        return Response({
            'task_id': task_id,
            'status': result.status,
            'result': result.result if result.ready() else None,
        })