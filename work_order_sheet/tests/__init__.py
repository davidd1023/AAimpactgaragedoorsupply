from . import test_kit_flow
from . import test_kit_spring
from . import test_work_order_sheet
from . import test_delivery_confirmation
from . import test_wo_number

# THE WORK STATION TESTS ARE PUT AWAY WITH THE STATIONS THEMSELVES, 2026-10-14.
# They are a careful description of a feature that is deliberately switched
# off - no kiosk routes, no sorting on confirm, no menus - so running them now
# would report failures that are the instruction being followed. The file
# stays, and comes back with the benches.
#
#   from . import test_work_stations
from . import test_order_ready_alert
from . import test_order_cancel
from . import test_customer_emails
