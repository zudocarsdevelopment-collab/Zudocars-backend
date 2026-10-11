from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser, AllowAny, IsAuthenticated
from authenticator.authentication import DashboardAuthentication
from django.db.models.deletion import ProtectedError
from .tasks import sync_vehicles_task
from celery.result import AsyncResult
from .services import sync_vehicles_from_therentos
from .models import Vehicle, PickupHub, Location
from .serializers import VehicleSerializer, PickupHubSerializer, LocationSerializer
from django.db.models import Q


class LocationListAPIView(generics.ListCreateAPIView):
    authentication_classes = [DashboardAuthentication]
    serializer_class = LocationSerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method == 'GET' else [IsAuthenticated()]

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.query_params.get('include_inactive') == '1':
            return Location.objects.all()
        return Location.objects.filter(is_active=True)


class LocationDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [DashboardAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = LocationSerializer
    queryset = Location.objects.all()

    def delete(self, request, *args, **kwargs):
        try:
            return super().delete(request, *args, **kwargs)
        except ProtectedError:
            return Response({'error': 'This location has pickup hubs. Reassign them or deactivate the location.'}, status=409)


class PickupHubListAPIView(generics.ListCreateAPIView):
    authentication_classes = [DashboardAuthentication]
    serializer_class = PickupHubSerializer

    def get_permissions(self):
        return [AllowAny()] if self.request.method == 'GET' else [IsAuthenticated()]

    def get_queryset(self):
        hubs = PickupHub.objects.select_related('location')
        if self.request.user.is_authenticated and self.request.query_params.get('include_inactive') == '1':
            return hubs
        return hubs.filter(Q(location__is_active=True) | Q(location__isnull=True), is_active=True)


class PickupHubDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [DashboardAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = PickupHub.objects.all()
    serializer_class = PickupHubSerializer

    def delete(self, request, *args, **kwargs):
        try:
            return super().delete(request, *args, **kwargs)
        except ProtectedError:
            return Response({'error': 'This hub has linked vehicles. Reassign them or deactivate the hub.'}, status=409)


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
