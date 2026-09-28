from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from .models import (
    ServiceRecord,
    ServiceType,
    MaintenanceSchedule,
)

from .serializers import (
    ServiceRecordSerializer,
    ServiceTypeSerializer,
    MaintenanceScheduleSerializer,
)


# SERVICE TYPE API
class ServiceTypeAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        types = ServiceType.objects.all()
        serializer = ServiceTypeSerializer(types, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ServiceTypeSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# SERVICE RECORD LIST AND CREATE
class ServiceRecordAPIView(APIView):

    def get(self, request):
        records = ServiceRecord.objects.all().order_by("-service_date")

        car_id = request.query_params.get("car_id")

        if car_id:
            records = records.filter(car_id=car_id)

        serializer = ServiceRecordSerializer(records, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = ServiceRecordSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# SERVICE RECORD DETAIL, UPDATE, DELETE
class ServiceRecordDetailAPIView(APIView):
    permission_classes = [AllowAny]
    def get_object(self, pk):
        try:
            return ServiceRecord.objects.get(pk=pk)
        except ServiceRecord.DoesNotExist:
            return None

    def get(self, request, pk):
        record = self.get_object(pk)

        if not record:
            return Response(
                {"error": "Service record not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ServiceRecordSerializer(record)
        return Response(serializer.data)

    def put(self, request, pk):
        record = self.get_object(pk)

        if not record:
            return Response(
                {"error": "Service record not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ServiceRecordSerializer(
            record,
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        record = self.get_object(pk)

        if not record:
            return Response(
                {"error": "Service record not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ServiceRecordSerializer(
            record,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        record = self.get_object(pk)

        if not record:
            return Response(
                {"error": "Service record not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        record.delete()

        return Response(
            {"message": "Service record deleted successfully"},
            status=status.HTTP_200_OK
        )


# MAINTENANCE SCHEDULE LIST AND CREATE
class MaintenanceScheduleAPIView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        schedules = MaintenanceSchedule.objects.all()

        car_id = request.query_params.get("car_id")
        schedule_status = request.query_params.get("status")

        if car_id:
            schedules = schedules.filter(car_id=car_id)

        if schedule_status:
            schedules = schedules.filter(status=schedule_status)

        serializer = MaintenanceScheduleSerializer(
            schedules,
            many=True
        )

        return Response(serializer.data)

    def post(self, request):
        serializer = MaintenanceScheduleSerializer(
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


# MAINTENANCE SCHEDULE DETAIL
class MaintenanceScheduleDetailAPIView(APIView):

    def get_object(self, pk):
        try:
            return MaintenanceSchedule.objects.get(pk=pk)
        except MaintenanceSchedule.DoesNotExist:
            return None

    def get(self, request, pk):
        schedule = self.get_object(pk)

        if not schedule:
            return Response(
                {"error": "Maintenance schedule not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = MaintenanceScheduleSerializer(schedule)
        return Response(serializer.data)

    def put(self, request, pk):
        schedule = self.get_object(pk)

        if not schedule:
            return Response(
                {"error": "Maintenance schedule not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = MaintenanceScheduleSerializer(
            schedule,
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    def patch(self, request, pk):
        schedule = self.get_object(pk)

        if not schedule:
            return Response(
                {"error": "Maintenance schedule not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = MaintenanceScheduleSerializer(
            schedule,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )

    def delete(self, request, pk):
        schedule = self.get_object(pk)

        if not schedule:
            return Response(
                {"error": "Maintenance schedule not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        schedule.delete()

        return Response(
            {"message": "Maintenance schedule deleted successfully"},
            status=status.HTTP_200_OK
        )