import pytest
import swapper

from baseapp_profiles.tests.factories import ProfileFactory

from .factories import RateFactory

Rate = swapper.load_model("baseapp_ratings", "Rate")
RatableMetadata = swapper.load_model("baseapp_ratings", "RatableMetadata")

pytestmark = pytest.mark.django_db


def test_rate_save_creates_metadata_and_increments_count():
    """Creating a Rate through the ORM should populate `RatableMetadata` for the
    target with a fresh count/sum/average."""
    target = ProfileFactory()

    RateFactory(target=target, value=4)

    metadata = RatableMetadata.get_for_object(target)
    assert metadata is not None
    assert metadata.ratings_count == 1
    assert metadata.ratings_sum == 4
    assert metadata.ratings_average == pytest.approx(4.0)


def test_rate_save_aggregates_multiple_ratings():
    target = ProfileFactory()

    RateFactory(target=target, value=2)
    RateFactory(target=target, value=4)
    RateFactory(target=target, value=3)

    metadata = RatableMetadata.get_for_object(target)
    assert metadata.ratings_count == 3
    assert metadata.ratings_sum == 9
    assert metadata.ratings_average == pytest.approx(3.0)


def test_rate_delete_decrements_count_and_recomputes_average():
    target = ProfileFactory()

    RateFactory(target=target, value=5)
    a = RateFactory(target=target, value=1)

    metadata = RatableMetadata.get_for_object(target)
    assert metadata.ratings_count == 2
    assert metadata.ratings_sum == 6

    a.delete()

    metadata.refresh_from_db()
    assert metadata.ratings_count == 1
    assert metadata.ratings_sum == 5
    assert metadata.ratings_average == pytest.approx(5.0)


def test_rate_delete_resets_metadata_to_zero_when_no_ratings_left():
    target = ProfileFactory()
    rate = RateFactory(target=target, value=3)

    metadata = RatableMetadata.get_for_object(target)
    assert metadata.ratings_count == 1

    rate.delete()

    metadata.refresh_from_db()
    assert metadata.ratings_count == 0
    assert metadata.ratings_sum == 0
    assert metadata.ratings_average == 0


def test_ratings_count_isolated_per_target():
    """Ratings against profile A must not bleed into profile B's metadata."""
    target_a = ProfileFactory()
    target_b = ProfileFactory()

    RateFactory(target=target_a, value=2)

    metadata_a = RatableMetadata.get_for_object(target_a)
    metadata_b = RatableMetadata.get_for_object(target_b)

    assert metadata_a.ratings_count == 1
    assert metadata_b is None or metadata_b.ratings_count == 0


def test_update_ratings_indicators_recomputes_from_existing_rates():
    """Calling `Rate.update_ratings_indicators(target)` directly should recompute
    counters from the live `Rate` rows even if the metadata row is out of sync."""
    target = ProfileFactory()

    RateFactory(target=target, value=4)

    metadata = RatableMetadata.get_for_object(target)
    metadata.ratings_count = 0
    metadata.ratings_sum = 0
    metadata.ratings_average = 0
    metadata.save(update_fields=["ratings_count", "ratings_sum", "ratings_average"])

    Rate.update_ratings_indicators(target)

    metadata.refresh_from_db()
    assert metadata.ratings_count == 1
    assert metadata.ratings_sum == 4
    assert metadata.ratings_average == pytest.approx(4.0)


def test_update_ratings_indicators_no_op_when_target_is_none():
    """`update_ratings_indicators(None)` should silently no-op rather than crash."""
    Rate.update_ratings_indicators(None)  # should not raise
