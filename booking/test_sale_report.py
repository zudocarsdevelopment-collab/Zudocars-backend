from datetime import datetime
from decimal import Decimal
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from django.test import TestCase
from . import tests as booking_tests
from .models import Booking


class SaleReportTests(TestCase):
    def setUp(self):
        booking_tests.LocalBookingTests.setUp(self)
        booking_tests.LocalBookingTests.sign_in(self)
        from authenticator.models import StaffMember
        self.staff = StaffMember.objects.create(name='Operator', email=self.user.email, employee_id='SALE-TEST', role='staff', status='Approved')
        self.query = {'date_from': '2026-10-01', 'date_to': '2026-10-01', 'file_type': 'xlsx'}
        self.booking = Booking.objects.create(
            vehicle=self.vehicle, vehicle_plate_number=self.vehicle.plate_number,
            cart_vehicle={'name': 'Long vehicle description & special characters'},
            customer_name='=SUM(A1:A5)', customer_phone='9000000000',
            start_datetime=datetime(2026, 9, 29, tzinfo=ZoneInfo('Asia/Kolkata')),
            end_datetime=datetime(2026, 10, 1, tzinfo=ZoneInfo('Asia/Kolkata')),
            returned_at=datetime(2026, 9, 30, 18, 30, tzinfo=ZoneInfo('UTC')),
            pickup_location_id=self.hub.pk, dropoff_location_id=self.hub.pk,
            rental_amount=Decimal('1500'), delivery_amount=Decimal('200'),
            discount_amount=Decimal('150'), discount_type='percentage', discount_value=10,
            total_amount=Decimal('1550'), status='completed', assigned_email=self.user.email)

    def download(self, **kwargs):
        return self.client.get('/api/reports/sales/', {**self.query, **kwargs})

    def test_excel_has_numeric_totals_and_literal_customer_text(self):
        response = self.download()
        self.assertEqual(response.status_code, 200)
        with ZipFile(BytesIO(response.content)) as archive:
            for name in archive.namelist():
                ET.fromstring(archive.read(name))
            root = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
            ns = {'m': root.tag[1:].split('}')[0]}
            self.assertEqual(root.find('.//m:c[@r="I6"]/m:v', ns).text, '1550.00')
            self.assertEqual(root.find('.//m:c[@r="G7"]/m:v', ns).text, '150.00')
            self.assertEqual(root.find('.//m:c[@r="B6"]/m:is/m:t', ns).text, '=SUM(A1:A5)')
            self.assertIsNone(root.find('.//m:f', ns))

    def test_date_boundaries_are_in_india_time_and_end_is_inclusive(self):
        self.assertIn(self.booking.reference.encode(), self._sheet(self.download()))
        self.assertNotIn(self.booking.reference.encode(), self._sheet(self.download(date_from='2026-09-30', date_to='2026-09-30')))
        self.booking.returned_at = datetime(2026, 10, 1, 18, 29, 59, tzinfo=ZoneInfo('UTC'))
        self.booking.save()
        self.assertIn(self.booking.reference.encode(), self._sheet(self.download()))
        self.booking.returned_at = datetime(2026, 10, 1, 18, 30, tzinfo=ZoneInfo('UTC'))
        self.booking.save()
        self.assertNotIn(self.booking.reference.encode(), self._sheet(self.download()))

    @staticmethod
    def _sheet(response):
        with ZipFile(BytesIO(response.content)) as archive:
            return archive.read('xl/worksheets/sheet1.xml')

    def test_search_status_and_staff_scope(self):
        self.assertNotIn(self.booking.reference.encode(), self._sheet(self.download(search='unmatched')))
        self.booking.assigned_email = 'other@example.com'
        self.booking.save()
        self.assertNotIn(self.booking.reference.encode(), self._sheet(self.download()))
        self.staff.role = 'admin'
        self.staff.save()
        self.assertIn(self.booking.reference.encode(), self._sheet(self.download()))
        self.booking.status = 'confirmed'
        self.booking.save()
        self.assertNotIn(self.booking.reference.encode(), self._sheet(self.download()))

    def test_pdf_and_empty_reports(self):
        from pypdf import PdfReader
        response = self.download(file_type='pdf')
        self.assertEqual(response.status_code, 200)
        text = PdfReader(BytesIO(response.content)).pages[0].extract_text()
        self.assertIn(self.booking.reference, text)
        self.assertIn('1,550.00', text)
        empty = self.download(file_type='pdf', search='unmatched')
        self.assertIn('No completed transactions', PdfReader(BytesIO(empty.content)).pages[0].extract_text())

    def test_auth_and_validation(self):
        for query in [{'date_to': '2026-09-30'}, {'date_from': 'invalid'}, {'file_type': 'csv'}, {'date_from': ''}]:
            self.assertEqual(self.download(**query).status_code, 400)
        self.client.credentials()
        self.assertEqual(self.download().status_code, 401)
