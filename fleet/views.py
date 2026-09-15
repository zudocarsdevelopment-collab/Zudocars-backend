from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from .tasks import sync_vehicles_task
from celery.result import AsyncResult
from .services import sync_vehicles_from_therentos
from .models import Vehicle
from .serializers import VehicleSerializer
import uuid
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import generics, filters, status


class VehicleListCreateAPIView(generics.ListCreateAPIView):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    # MultiPartParser/FormParser handle vehicle_image (ImageField) uploads;
    # JSONParser keeps plain JSON payloads (photo_url only, no file) working.
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filter_backends = [filters.SearchFilter]
    search_fields = ['plate_number', 'category', 'sub_category', 'location_base']
    # permission_classes = [IsAdminUser]  # enable once real auth is wired up

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for field, param in [
            ('fuel_type', 'fuel_type'),
            ('transmission', 'transmission'),
            ('body_type', 'body_type'),
            ('vehicle_type', 'vehicle_type'),
            ('is_active', 'is_active'),
        ]:
            value = params.get(param)
            if value is not None and value != '':
                if field == 'is_active':
                    qs = qs.filter(is_active=value.lower() in ('1', 'true', 'yes'))
                else:
                    qs = qs.filter(**{f'{field}__iexact': value})
        return qs

    def perform_create(self, serializer):
        # Manually-added vehicles won't have a theRentOS id, but external_id
        # is unique/required at the DB level — generate a placeholder one.
        external_id = serializer.validated_data.get('external_id')
        if not external_id:
            serializer.save(external_id=f"manual-{uuid.uuid4().hex[:12]}")
        else:
            serializer.save()

class VehicleRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Vehicle.objects.all()
    serializer_class = VehicleSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    # permission_classes = [IsAdminUser]

class SyncVehiclesAPIView(APIView):
    # permission_classes = [IsAdminUser]

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