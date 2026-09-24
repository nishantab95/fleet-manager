from datetime import UTC, datetime, timedelta

from fleet_api.domain.reporting import _trip_timing_metrics


def test_trip_timing_metrics_use_consecutive_approved_completion_times() -> None:
    first = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    timestamps = [
        first,
        first + timedelta(minutes=42),
        first + timedelta(hours=1, minutes=50),
        first + timedelta(hours=2, minutes=20),
    ]

    result = _trip_timing_metrics(timestamps)

    assert result[0] == first
    assert result[1] == first + timedelta(hours=2, minutes=20)
    assert result[2] == timedelta(hours=2, minutes=20)
    assert result[3] == timedelta(minutes=46, seconds=40)
    assert result[4] == timedelta(minutes=42)
    assert result[5] == timedelta(minutes=68)


def test_trip_timing_metrics_have_explicit_small_sample_contract() -> None:
    assert _trip_timing_metrics([]) == (None, None, None, None, None, None)

    only_trip = datetime(2025, 1, 15, 8, 0, tzinfo=UTC)
    assert _trip_timing_metrics([only_trip]) == (
        only_trip,
        only_trip,
        timedelta(0),
        None,
        None,
        None,
    )
