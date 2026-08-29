import datetime as dt


def report_window(period, ref_date):
    """
    Daily/weekly/monthly window (plus the matching previous window, for
    period-over-period comparison) anchored on ref_date. Shared by
    DataUsageView and RouterBandwidthTrendView.
    """
    if period == 'weekly':
        start = ref_date - dt.timedelta(days=ref_date.weekday())
        end = start + dt.timedelta(days=6)
        prev_start = start - dt.timedelta(days=7)
        prev_end = start - dt.timedelta(days=1)
    elif period == 'monthly':
        start = ref_date.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1) - dt.timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1, day=1) - dt.timedelta(days=1)
        prev_month_end = start - dt.timedelta(days=1)
        prev_start = prev_month_end.replace(day=1)
        prev_end = prev_month_end
    else:  # daily
        start = end = ref_date
        prev_start = prev_end = ref_date - dt.timedelta(days=1)
    return start, end, prev_start, prev_end
