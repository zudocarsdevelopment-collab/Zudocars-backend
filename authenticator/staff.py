from rest_framework import serializers, generics
from rest_framework.permissions import IsAuthenticated
from .models import StaffMember
from .authentication import DashboardAuthentication


class StaffSerializer(serializers.ModelSerializer):
    employeeId = serializers.CharField(source='employee_id', max_length=50)

    class Meta:
        model = StaffMember
        fields = ['id', 'name', 'email', 'phone', 'employeeId', 'department', 'role', 'status']

    def validate_employeeId(self, value):
        rows = StaffMember.objects.filter(employee_id=value)
        if self.instance:
            rows = rows.exclude(pk=self.instance.pk)
        if rows.exists():
            raise serializers.ValidationError('Employee ID is already in use.')
        return value


class StaffListAPI(generics.ListCreateAPIView):
    authentication_classes = [DashboardAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = StaffMember.objects.all()
    serializer_class = StaffSerializer


class StaffDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    authentication_classes = [DashboardAuthentication]
    permission_classes = [IsAuthenticated]
    queryset = StaffMember.objects.all()
    serializer_class = StaffSerializer
