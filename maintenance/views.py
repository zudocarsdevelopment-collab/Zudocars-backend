from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from authenticator.authentication import DashboardAuthentication
from .models import ServiceType, ServiceRecord, MaintenanceSchedule
from .serializers import ServiceTypeSerializer, ServiceRecordSerializer, MaintenanceScheduleSerializer


class OperatorAPI:
    authentication_classes = [DashboardAuthentication]
    permission_classes = [IsAuthenticated]


class ServiceTypeAPIView(OperatorAPI, generics.ListCreateAPIView):
    queryset = ServiceType.objects.all()
    serializer_class = ServiceTypeSerializer


class ServiceTypeDetailAPIView(OperatorAPI, generics.RetrieveUpdateDestroyAPIView):
    queryset = ServiceType.objects.all()
    serializer_class = ServiceTypeSerializer


class ServiceRecordAPIView(OperatorAPI, generics.ListCreateAPIView):
    serializer_class = ServiceRecordSerializer

    def get_queryset(self):
        records = ServiceRecord.objects.all()
        if self.request.query_params.get('car_id'):
            records = records.filter(car_id=self.request.query_params['car_id'])
        return records


class ServiceRecordDetailAPIView(OperatorAPI, generics.RetrieveUpdateDestroyAPIView):
    queryset = ServiceRecord.objects.all()
    serializer_class = ServiceRecordSerializer


class MaintenanceScheduleAPIView(OperatorAPI, generics.ListCreateAPIView):
    serializer_class = MaintenanceScheduleSerializer

    def get_queryset(self):
        schedules = MaintenanceSchedule.objects.all()
        for field, param in [('car_id', 'car_id'), ('status', 'status')]:
            if self.request.query_params.get(param):
                schedules = schedules.filter(**{field: self.request.query_params[param]})
        return schedules


class MaintenanceScheduleDetailAPIView(OperatorAPI, generics.RetrieveUpdateDestroyAPIView):
    queryset = MaintenanceSchedule.objects.all()
    serializer_class = MaintenanceScheduleSerializer
