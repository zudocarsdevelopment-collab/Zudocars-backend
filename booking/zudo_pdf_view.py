import os
import uuid
import re
from pathlib import Path
from html import escape
from zoneinfo import ZoneInfo
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .models import Booking
from .booking import booking_result
from .zudo_pdf_generator import generate_zudo_estimate_pdf


class ZudoEstimatePDFAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        booking = get_object_or_404(Booking.objects.select_related('vehicle'), reference=request.data.get('booking_reference', ''))
        tz = ZoneInfo(getattr(settings, 'BOOKING_TIME_ZONE', 'Asia/Kolkata'))
        start, end = timezone.localtime(booking.start_datetime, tz), timezone.localtime(booking.end_datetime, tz)
        payload = {
            'issued_date': timezone.localtime(booking.created_at, tz).strftime('%d %b %Y'),
            'customer_name': booking.customer_name, 'customer_phone': booking.customer_phone,
            'vehicle_name': booking.cart_vehicle.get('name', booking.vehicle.category),
            'transmission': booking.vehicle.transmission, 'fuel_type': booking.vehicle.fuel_type,
            'pickup_location_name': booking.pickup_custom_payload or f'Location {booking.pickup_location_id}',
            'dropoff_location_name': booking.dropoff_custom_payload or f'Location {booking.dropoff_location_id}',
            'date_from': start.strftime('%Y-%m-%d'), 'time_from': start.strftime('%H:%M'),
            'date_to': end.strftime('%Y-%m-%d'), 'time_to': end.strftime('%H:%M'),
            'booking_response': booking_result(booking),
        }
        filename = f'zudo-booking-{booking.reference}-{uuid.uuid4().hex[:8]}.pdf'
        for key, value in payload.items():
            if isinstance(value, str):
                payload[key] = escape(value)
        output_dir = os.path.join(settings.MEDIA_ROOT, 'estimates')
        os.makedirs(output_dir, exist_ok=True)
        generate_zudo_estimate_pdf(payload, os.path.join(output_dir, filename))
        return Response({'success': True, 'reference': booking.reference,
            'pdf_url': request.build_absolute_uri(reverse('estimate-pdf-download', kwargs={'filename': filename}))}, status=201)


class ZudoEstimatePDFDownloadAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, filename):
        # Match only generated filenames; never accept arbitrary media paths.
        if not re.fullmatch(r'zudo-booking-ZUDO-[A-F0-9]{12}-[a-f0-9]{8}\.pdf', filename):
            raise Http404('Estimate PDF not found.')
        path = Path(settings.MEDIA_ROOT) / 'estimates' / filename
        try:
            handle = path.open('rb')
        except FileNotFoundError:
            raise Http404('Estimate PDF not found.')
        response = FileResponse(handle, content_type='application/pdf', filename=filename)
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response
