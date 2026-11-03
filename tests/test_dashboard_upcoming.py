"""Read-only upcoming Dashboard query, ordering and ownership boundaries."""
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import test_trip_service as fixtures
from trip_service import list_dashboard_upcoming_trips,TripConsistencyError

class DashboardUpcomingReadTests(unittest.TestCase):
 setUp=fixtures.TripServiceTests.setUp
 def query(self,rows):
  q=Mock(spec=['select','eq','gte','order','range','retry','execute'])
  for name in ['select','eq','gte','order','range','retry']:getattr(q,name).return_value=q
  q.execute.return_value=SimpleNamespace(data=rows);self.queries.append(q);return q
 def test_read_is_three_upcoming_owned_trips_not_newest_created(self):
  q=self.query([fixtures.trip(visit_date='2026-11-06')])
  result=list_dashboard_upcoming_trips(self.context,today=date(2026,11,1))
  self.assertEqual(result[0].visit_date,date(2026,11,6))
  q.eq.assert_called_once_with('user_id',fixtures.OWNER)
  q.gte.assert_called_once_with('visit_date','2026-11-01')
  self.assertEqual(q.order.call_args_list[0].args,('visit_date',))
  q.range.assert_called_once_with(0,2);self.client.rpc.assert_not_called()
 def test_null_past_foreign_and_excess_rows_are_rejected(self):
  for rows in ([fixtures.trip(visit_date=None)],[fixtures.trip(visit_date='2026-10-31')],[fixtures.trip(user_id=fixtures.OTHER,visit_date='2026-11-06')],[fixtures.trip(visit_date='2026-11-06')]*4):
   self.query(rows)
   with self.assertRaises(TripConsistencyError):list_dashboard_upcoming_trips(self.context,today=date(2026,11,1))
