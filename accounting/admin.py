from django.contrib import admin
from .models import Payment, Expense


class LedgerAdmin(admin.ModelAdmin):
    list_display = ['id', 'amount', 'date', 'created_by', 'voided_at']
    def has_add_permission(self, request):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Payment, LedgerAdmin)
admin.site.register(Expense, LedgerAdmin)
