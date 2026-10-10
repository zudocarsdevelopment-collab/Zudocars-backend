# Local Zudo bookings

Availability, reservation creation, dashboard management and PDFs use the local database. No AVS account or login is required for these flows. Fleet sync remains a separate optional integration; fleet entries can also be added manually.

## Deployment

Estimate PDFs are served through `/api/estimates/pdf/<filename>/`. The generation
endpoint returns this URL, so nginx does not need direct access to the media
directory to serve estimates. Proxy `/api/` to Django as usual. Existing files
can be opened using the same filename under this endpoint after deploying.
Older `/media/estimates/` links still require the nginx media alias and filesystem
permissions to be configured correctly.

1. Deploy backend changes and run `python manage.py migrate` from the backend project.
2. Deploy the UI build.
3. Sign out and sign in to the dashboard to obtain the new 12-hour management token.
4. Ensure fleet entries are active, have vehicle_type `Car` and a positive hourly_rate.

Existing AVS reservations are not imported. Add any outstanding reservations locally before opening booking availability to customers, to avoid conflicting with commitments held only in AVS.

## Pricing and availability

Pickup/return input is interpreted in Asia/Kolkata, configurable with BOOKING_TIME_ZONE. Charge whole hours rounded up, with the fleet min_hours_rate as a minimum rental amount. BOOKING_DELIVERY_AMOUNT defaults to 1200 INR for delivery and return, matching the existing car booking screen. Rates are treated as customer-facing inclusive prices; no additional tax or deposit is calculated. Client totals are ignored.

Pending and confirmed bookings reserve the vehicle. Cancelled/completed bookings release it. Adjacent reservations are permitted. Reservation creation locks the vehicle row on PostgreSQL to serialize concurrent bookings. Pending reservations remain blocked until an operator confirms or cancels them.

## Endpoints

- POST /api/vehicles/available/: dates, times and pickup/dropoff location IDs; returns local vehicles and calculated prices.
- POST /api/bookings/: same trip fields plus cart_vehicle (local fleet primary key), customer_name and customer_phone. Returns reference and the persisted booking.
- GET /api/bookings/list/: requires Authorization: Bearer <login token>.
- PATCH /api/bookings/<reference>/: authenticated operator may update status, assigned_email and notes.
- POST /api/estimates/pdf/: booking_reference; renders saved details and prices.

Status changes: pending -> confirmed/cancelled; confirmed -> completed/cancelled. Terminal records cannot be reopened.

The /api/estimates/create/ path remains an alias for local booking creation for existing clients.

## Verification

Install test dependencies with `pip install -r requirements-dev.txt`, then run `python manage.py test booking.tests`. Tests cover local creation without outbound requests, trusted pricing, overlaps/adjacent windows, authentication, lifecycle changes, cancellation releasing availability, validation and PDF generation. SQLite tests do not exercise PostgreSQL concurrency locking.

## Pickup hubs

Create hubs in Dashboard -> Pickup Hubs (or Django admin), then assign each vehicle in Fleet -> Edit vehicle -> Pickup hub. Active hubs populate the home and cars location selectors. Availability filters by the assigned pickup hub; bookings reject a vehicle belonging to another hub. Return hubs must be active. Deactivating a hub removes its vehicles from customer availability. Hubs with linked vehicles cannot be deleted.

Fleet migrations add the pickup_hub relationship and derive hubs from existing nonempty location_base names without deleting data. Vehicles lacking a base name need a manual hub selection. Existing booking location names remain historical snapshots.
