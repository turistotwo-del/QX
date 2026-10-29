"""Known federal workday transfers, five-day workweek; legal caution remains."""
import unittest
from datetime import date
from modern.ru_work_calendar import add_workdays, is_working_day
from modern.tender_store import calculate_deadline

class FederalCalendar(unittest.TestCase):
    def test_2026_new_year_transfer(self):
        self.assertFalse(is_working_day(date(2026,1,9)))
        self.assertTrue(is_working_day(date(2026,1,12)))
        self.assertEqual(add_workdays(date(2026,1,8),1),date(2026,1,12))

    def test_2026_end_of_year_transfer(self):
        self.assertFalse(is_working_day(date(2026,12,31)))
        self.assertEqual(add_workdays(date(2026,12,30),1),date(2027,1,11))

    def test_2027_february_saturday(self):
        self.assertTrue(is_working_day(date(2027,2,20)))
        self.assertFalse(is_working_day(date(2027,2,22)))
        self.assertEqual(add_workdays(date(2027,2,19),1),date(2027,2,20))

    def test_2027_may_and_november(self):
        self.assertFalse(is_working_day(date(2027,5,3)))
        self.assertFalse(is_working_day(date(2027,11,5)))
        self.assertEqual(add_workdays(date(2027,11,4),1),date(2027,11,8))

    def test_outside_coverage_flagged(self):
        with self.assertRaises(ValueError):is_working_day(date(2028,1,3))
        result=calculate_deadline({'signed_on':'2028-01-03','due_days':5,'due_unit':'work'},today=date(2028,1,3))
        self.assertIn('ОРИЕНТИРОВОЧНАЯ',result['caution'])

    def test_deadline_2026_uses_verified_days_but_warns_regional(self):
        result=calculate_deadline({'signed_on':'2026-12-30','due_days':1,'due_unit':'work'},today=date(2026,12,30))
        self.assertEqual(result['due_on'],'2027-01-11')
        self.assertIn('Региональные',result['caution'])

if __name__=='__main__':unittest.main()
