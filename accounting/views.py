from decimal import Decimal, InvalidOperation
from django.db import transaction, IntegrityError
from uuid import UUID
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from authenticator.authentication import DashboardAuthentication
from booking.models import Booking
from maintenance.models import ServiceRecord
from fleet.models import Vehicle
from .models import Payment, Expense
from .serializers import PaymentSerializer, ExpenseSerializer

ZERO = Decimal('0.00')


def net_received(booking):
    return sum((p.amount if p.kind == 'receipt' else -p.amount for p in booking.payments.filter(voided_at__isnull=True)), ZERO)


class AccountingAPI(APIView):
    authentication_classes = [DashboardAuthentication]
    permission_classes = [IsAuthenticated]


class SummaryAPI(AccountingAPI):
    def get(self, request):
        rows = []
        revenue = received = outstanding = credit = ZERO
        for booking in Booking.objects.prefetch_related('payments').all():
            paid = sum((p.amount if p.kind == 'receipt' else -p.amount for p in booking.payments.all() if p.voided_at is None), ZERO)
            billed = booking.total_amount if booking.status in ('confirmed', 'completed') else ZERO
            due = max(billed - paid, ZERO)
            excess = max(paid - billed, ZERO)
            revenue += billed
            received += paid
            outstanding += due
            credit += excess
            rows.append({'reference': booking.reference, 'customer': booking.customer_name, 'vehicle': booking.vehicle_plate_number,
                         'status': booking.status, 'total': str(booking.total_amount), 'billed': str(billed), 'received': str(paid),
                         'outstanding': str(due), 'credit': str(excess)})
        services = ServiceRecord.objects.select_related('car').all()
        maintenance = sum((s.total_cost for s in services), ZERO)
        manual = sum((e.amount for e in Expense.objects.filter(voided_at__isnull=True)), ZERO)
        return Response({'revenue': str(revenue), 'received': str(received), 'outstanding': str(outstanding), 'customer_credit': str(credit),
                         'expenses': str(maintenance + manual), 'maintenance_expenses': str(maintenance), 'manual_expenses': str(manual),
                         'net_balance': str(revenue - maintenance - manual), 'bookings': rows,
                         'vehicles': list(Vehicle.objects.values('id', 'plate_number')),
                         'payments': PaymentSerializer(Payment.objects.select_related('booking', 'created_by', 'voided_by').all(), many=True).data,
                         'expense_entries': ExpenseSerializer(Expense.objects.select_related('created_by', 'voided_by').all(), many=True).data,
                         'maintenance_entries': [{'id': s.pk, 'date': s.service_date, 'description': s.description or s.service_center,
                                                  'vehicle': s.car.plate_number, 'amount': str(s.total_cost)} for s in services]})


class EntryAPI(AccountingAPI):
    model = Expense
    serializer_class = ExpenseSerializer

    def post(self, request):
        try:
            request_id = UUID(str(request.data.get('request_id', '')))
        except (ValueError, TypeError, AttributeError):
            raise ValidationError({'request_id': 'Provide a valid submission ID.'})
        with transaction.atomic():
            # Serialize ledger mutations, including duplicate submissions and refunds.
            type(request.user).objects.select_for_update().get(pk=request.user.pk)
            existing = self.model.objects.filter(request_id=request_id).first()
            if existing:
                original = self.serializer_class(existing).data
                for field in ('amount', 'date', 'reference', 'notes', 'booking', 'kind', 'method', 'category', 'description', 'vehicle'):
                    submitted = request.data.get(field)
                    same = str(submitted or '') == str(original.get(field) or '')
                    if field == 'amount':
                        try:
                            same = Decimal(str(submitted)) == Decimal(original['amount'])
                        except (InvalidOperation, ValueError, TypeError):
                            same = False
                    if field in request.data and not same:
                        raise ValidationError('This submission ID was already used for a different transaction.')
                return Response(original)
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            if self.model is Payment:
                booking = Booking.objects.select_for_update().get(pk=serializer.validated_data['booking'].pk)
                if booking.currency != 'INR':
                    raise ValidationError('Only INR bookings are supported.')
                if serializer.validated_data.get('kind', 'receipt') == 'refund' and serializer.validated_data['amount'] > net_received(booking):
                    raise ValidationError('Refund cannot exceed the money received for this booking.')
            try:
                with transaction.atomic():
                    serializer.save(created_by=request.user)
            except IntegrityError:
                raise ValidationError('This submission was already recorded. Refresh the accounts page before retrying.')
        return Response(serializer.data, status=201)


class PaymentAPI(EntryAPI):
    model = Payment
    serializer_class = PaymentSerializer


class VoidAPI(AccountingAPI):
    model = Expense
    serializer_class = ExpenseSerializer

    def post(self, request, pk):
        reason = request.data.get('reason', '')
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 250:
            raise ValidationError('Enter a reason of 1–250 characters for voiding this entry.')
        with transaction.atomic():
            initial = get_object_or_404(self.model, pk=pk)
            if self.model is Payment:
                booking = Booking.objects.select_for_update().get(pk=initial.booking_id)
            entry = self.model.objects.select_for_update().get(pk=pk)
            if entry.voided_at is None:
                if self.model is Payment and entry.kind == 'receipt' and net_received(booking) < entry.amount:
                    raise ValidationError('Void the related refunds first so receipts cannot become negative.')
                entry.voided_at = timezone.now()
                entry.voided_by = request.user
                entry.void_reason = reason.strip()
                entry.save(update_fields=['voided_at', 'voided_by', 'void_reason'])
        return Response(self.serializer_class(entry).data)


class PaymentVoidAPI(VoidAPI):
    model = Payment
    serializer_class = PaymentSerializer
