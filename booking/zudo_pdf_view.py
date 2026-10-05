# yourapp/views.py (or wherever your estimate-related views live)
#
# Requires: pip install reportlab --break-system-packages
# Uses DejaVu Sans (usually preinstalled on Ubuntu at
# /usr/share/fonts/truetype/dejavu/) so the ₹ symbol renders correctly --
# reportlab's built-in Helvetica has no glyph for it and silently draws a
# black box instead. If your server doesn't have these fonts, install with:
#   apt-get install fonts-dejavu-core

import os
import uuid

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers

from .zudo_pdf_generator import generate_zudo_estimate_pdf


class RepositionChargeSerializer(serializers.Serializer):
    name = serializers.CharField()
    total_estimate = serializers.FloatField(required=False, default=0)
    tax_amt = serializers.FloatField(required=False, default=0)


class TheRentosEstimateSerializer(serializers.Serializer):
    """Mirrors the shape of theRentOS's /admin/estimates response --
    only the fields the PDF actually uses; extra fields are ignored."""
    estimate_id = serializers.IntegerField()
    estimate_slug = serializers.CharField(required=False, allow_blank=True)
    public_url = serializers.URLField(required=False, allow_blank=True)
    status = serializers.CharField(required=False, default='draft')
    customer_name = serializers.CharField(required=False, allow_blank=True)
    estimate = serializers.DictField()  # kept loose -- validated further in the generator


class ZudoEstimatePDFRequestSerializer(serializers.Serializer):
    """
    Combines:
      - booking context you already had before calling theRentOS (theRentOS
        doesn't echo back phone, vehicle name, or location names), and
      - the raw JSON theRentOS returned from /admin/estimates.
    """
    customer_name = serializers.CharField()
    customer_phone = serializers.CharField()
    customer_country_code = serializers.CharField(default='91')

    vehicle_name = serializers.CharField()
    transmission = serializers.CharField(required=False, default='')
    fuel_type = serializers.CharField(required=False, default='')

    pickup_location_name = serializers.CharField()
    dropoff_location_name = serializers.CharField()

    date_from = serializers.DateField()
    time_from = serializers.CharField(default='00:00')
    date_to = serializers.DateField()
    time_to = serializers.CharField(default='00:00')

    extra_km_charge = serializers.FloatField(required=False, allow_null=True, default=None)

    staff_name = serializers.CharField(required=False, allow_blank=True, default='')
    staff_phone = serializers.CharField(required=False, allow_blank=True, default='')
    staff_phone_display = serializers.CharField(required=False, allow_blank=True, default='')

    therentos_response = TheRentosEstimateSerializer()


class ZudoEstimatePDFAPIView(APIView):
    """
    POST /api/estimates/pdf/

    Body: booking context + the JSON theRentOS returned from
    /admin/estimates (see ZudoEstimatePDFRequestSerializer above).

    Generates a Zudo Cars-branded PDF (different layout/branding from
    theRentOS's own PDF) and returns a URL to it.
    """

    def post(self, request):
        serializer = ZudoEstimatePDFRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # DateField -> isoformat strings for the generator
        data['date_from'] = data['date_from'].isoformat()
        data['date_to'] = data['date_to'].isoformat()

        estimate_id = data['therentos_response']['estimate_id']
        filename = f"zudo-estimate-{estimate_id}-{uuid.uuid4().hex[:8]}.pdf"

        output_dir = os.path.join(settings.MEDIA_ROOT, 'estimates')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, filename)

        try:
            generate_zudo_estimate_pdf(data, output_path)
        except Exception as e:
            return Response(
                {'error': f'Failed to generate PDF: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        pdf_url = request.build_absolute_uri(
    f"{settings.MEDIA_URL.rstrip('/')}/estimates/{filename}"
)

        return Response(
            {
                'success': True,
                'estimate_id': estimate_id,
                'pdf_url': pdf_url,
                'therentos_public_url': data['therentos_response'].get('public_url'),
            },
            status=status.HTTP_201_CREATED,
        )