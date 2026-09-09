from app.models import Rating
from app.tasting import ranked_brew_ids


def test_brew_ranking_uses_exact_scores_then_count_then_newest_record():
    scores = {
        10: [7] * 249 + [8],  # 7.004 beats 7.00333, even though both display 7.00.
        20: [7] * 299 + [8],
        30: [7] * 3,
        40: [7] * 6,
        50: [7] * 6,
        60: [9] * 2,  # An early result is not eligible for the ranking.
    }
    ratings = [
        Rating(brew_id=brew_id, liking=score)
        for brew_id, values in scores.items()
        for score in values
    ]
    assert ranked_brew_ids(ratings) == [10, 20, 50, 40, 30]
    assert ranked_brew_ids(list(reversed(ratings))) == [10, 20, 50, 40, 30]
    assert ranked_brew_ids([]) == []
