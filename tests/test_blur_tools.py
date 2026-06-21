from app.schemas.render import BlurKeyframe, BlurRegion
from app.services.blur_tools import BlurService


def test_normalize_single_region_single_keyframe():
    service = BlurService()
    regions = [
        BlurRegion(
            start=0, end=10,
            keyframes=[BlurKeyframe(time=0, x=0.1, y=0.2, width=0.3, height=0.4, strength=12)],
            interpolate=False,
        )
    ]
    intervals = service._normalize_regions(regions, 1920, 1080, 10)
    assert len(intervals) == 1
    start, end, x, y, w, h, s = intervals[0]
    assert start == 0
    assert end == 10
    assert x == 192
    assert y == 216
    assert w == 576
    assert h == 432
    assert s == 12


def test_normalize_multiple_keyframes():
    service = BlurService()
    regions = [
        BlurRegion(
            start=0, end=10,
            keyframes=[
                BlurKeyframe(time=2, x=0, y=0, width=0.5, height=0.5, strength=10),
                BlurKeyframe(time=5, x=0.5, y=0.5, width=0.5, height=0.5, strength=15),
            ],
            interpolate=False,
        )
    ]
    intervals = service._normalize_regions(regions, 1920, 1080, 10)
    # Should produce 3 intervals:
    # [0, 2) with first keyframe
    # [2, 5) with first keyframe (holds until next)
    # [5, 10) with second keyframe
    assert len(intervals) == 3
    assert intervals[0][0] == 0
    assert intervals[0][1] == 2
    assert intervals[0][6] == 10
    assert intervals[1][0] == 2
    assert intervals[1][1] == 5
    assert intervals[1][6] == 10
    assert intervals[2][0] == 5
    assert intervals[2][1] == 10
    assert intervals[2][6] == 15


def test_normalize_multiple_regions():
    service = BlurService()
    regions = [
        BlurRegion(
            start=0, end=5,
            keyframes=[BlurKeyframe(time=0, x=0.1, y=0.1, width=0.2, height=0.2, strength=10)],
            interpolate=False,
        ),
        BlurRegion(
            start=3, end=8,
            keyframes=[BlurKeyframe(time=3, x=0.8, y=0.8, width=0.15, height=0.15, strength=12)],
            interpolate=False,
        ),
    ]
    intervals = service._normalize_regions(regions, 1920, 1080, 10)
    assert len(intervals) == 2


def test_filter_complex_structure():
    service = BlurService()
    intervals = [(0, 5, 100, 200, 300, 400, 12), (5, 10, 200, 300, 400, 500, 15)]
    result = service._filter_complex(intervals)
    assert "[0:v]split=3[v0][k0][k1];" in result
    assert "[k0]crop=300:400:100:200,boxblur=12:10[b0];" in result
    assert "[k1]crop=400:500:200:300,boxblur=15:10[b1];" in result
    assert "[v0][b0]overlay=100:200:enable='between(t,0,5)'[v1];" in result
    assert "[v1][b1]overlay=200:300:enable='between(t,5,10)'[v2]" in result


def test_filter_complex_empty():
    service = BlurService()
    assert service._filter_complex([]) == ""


def test_normalize_empty_regions():
    service = BlurService()
    assert service._normalize_regions([], 1920, 1080, 10) == []


def test_normalize_keyframe_region_boundary():
    service = BlurService()
    regions = [
        BlurRegion(
            start=2, end=8,
            keyframes=[
                BlurKeyframe(time=3, x=0.1, y=0.1, width=0.3, height=0.3, strength=10),
                BlurKeyframe(time=6, x=0.5, y=0.5, width=0.4, height=0.4, strength=15),
            ],
            interpolate=False,
        )
    ]
    intervals = service._normalize_regions(regions, 1920, 1080, 10)
    assert len(intervals) == 3
    # [2, 3) — uses first keyframe (start < first kf time)
    assert intervals[0][0] == 2
    assert intervals[0][1] == 3
    assert intervals[0][6] == 10
    assert intervals[0][2] == 192
    assert intervals[0][3] == 108
    # [3, 6) — uses first keyframe (holds until next)
    assert intervals[1][0] == 3
    assert intervals[1][1] == 6
    assert intervals[1][6] == 10
    # [6, 8) — uses second keyframe
    assert intervals[2][0] == 6
    assert intervals[2][1] == 8
    assert intervals[2][6] == 15
    assert intervals[2][2] == 960
    assert intervals[2][3] == 540


def test_normalize_keyframe_high_strength():
    service = BlurService()
    regions = [
        BlurRegion(
            start=0, end=10,
            keyframes=[
                BlurKeyframe(time=0, x=0.25, y=0.25, width=0.5, height=0.5, strength=30),
            ],
            interpolate=False,
        )
    ]
    intervals = service._normalize_regions(regions, 1920, 1080, 10)
    assert len(intervals) == 1
    _, _, x, y, w, h, s = intervals[0]
    assert x == 480
    assert y == 270
    assert w == 960
    assert h == 540
    assert s == 30
