from datetime import date

import pytest

from pipeline.common.epiweek import date_from_iso_week, iso_week_of, iter_weekly_dates, shift_weeks


@pytest.mark.unit
class TestIsoWeekOf:
    def test_mid_year_date_returns_expected_iso_year_and_week(self):
        assert iso_week_of(date(2023, 6, 15)) == (2023, 24)

    def test_late_december_date_rolls_into_next_iso_year(self):
        # 2018-12-31 is a Monday, ISO week 1 of 2019
        assert iso_week_of(date(2018, 12, 31)) == (2019, 1)

    def test_early_january_date_rolls_into_previous_iso_year(self):
        # 2023-01-01 is a Sunday, ISO week 52 of 2022
        assert iso_week_of(date(2023, 1, 1)) == (2022, 52)

    def test_iso_week_53_year(self):
        # 2020 has an ISO week 53
        assert iso_week_of(date(2020, 12, 31)) == (2020, 53)


@pytest.mark.unit
class TestDateFromIsoWeek:
    def test_roundtrips_with_iso_week_of(self):
        d = date_from_iso_week(2023, 24)
        assert iso_week_of(d) == (2023, 24)

    def test_week_1_of_year_with_late_start(self):
        # ISO week 1 of 2019 starts 2018-12-31 (Monday)
        assert date_from_iso_week(2019, 1) == date(2018, 12, 31)

    def test_week_53_of_2020(self):
        assert date_from_iso_week(2020, 53) == date(2020, 12, 28)

    def test_invalid_week_raises(self):
        with pytest.raises(ValueError):
            date_from_iso_week(2023, 54)

    def test_week_zero_raises(self):
        with pytest.raises(ValueError):
            date_from_iso_week(2023, 0)

    def test_weekday_out_of_range_raises(self):
        with pytest.raises(ValueError):
            date_from_iso_week(2023, 24, weekday=8)

    def test_week_53_in_a_year_without_one_raises(self):
        # 2023 has no ISO week 53
        with pytest.raises(ValueError):
            date_from_iso_week(2023, 53)


@pytest.mark.unit
class TestShiftWeeks:
    def test_shift_forward_across_year_boundary(self):
        assert shift_weeks(date(2018, 12, 24), 2) == date(2019, 1, 7)

    def test_shift_backward(self):
        assert shift_weeks(date(2023, 6, 15), -2) == date(2023, 6, 1)

    def test_shift_zero_is_identity(self):
        d = date(2023, 6, 15)
        assert shift_weeks(d, 0) == d


@pytest.mark.unit
class TestIterWeeklyDates:
    def test_returns_weekly_dates_inclusive_of_both_ends(self):
        dates = iter_weekly_dates(date(2023, 1, 2), date(2023, 1, 16))
        assert dates == [date(2023, 1, 2), date(2023, 1, 9), date(2023, 1, 16)]

    def test_single_day_window_returns_one_date(self):
        assert iter_weekly_dates(date(2023, 1, 2), date(2023, 1, 2)) == [date(2023, 1, 2)]

    def test_end_before_start_returns_empty_list(self):
        assert iter_weekly_dates(date(2023, 1, 16), date(2023, 1, 2)) == []

    def test_end_not_landing_exactly_on_a_step_is_excluded(self):
        dates = iter_weekly_dates(date(2023, 1, 2), date(2023, 1, 20))
        assert dates == [date(2023, 1, 2), date(2023, 1, 9), date(2023, 1, 16)]
