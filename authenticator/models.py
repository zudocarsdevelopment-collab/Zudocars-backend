from django.db import models


class StaffMember(models.Model):
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=30, blank=True)
    employee_id = models.CharField(max_length=50, unique=True)
    department = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=10, choices=[('staff', 'Staff'), ('admin', 'Admin')], default='staff')
    status = models.CharField(max_length=10, choices=[('Pending', 'Pending'), ('Approved', 'Approved'), ('Rejected', 'Rejected')], default='Pending')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
