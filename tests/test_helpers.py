"""纯函数单元测试：这些用例都来自实战踩过的坑，防止回归。"""
from parsers.page import money, norm_ws, parse_date
from parsers.uk.common import band, date_range, fee_near, ielts


def test_money():
    assert money("Full-time fee: £34,470") == 34470.0
    assert money("about £9,535.50 per year") == 9535.5
    assert money("no fee here") is None


def test_parse_date_formats():
    assert parse_date("20 Oct 2025") == "2025-10-20"
    assert parse_date("20 October 2025") == "2025-10-20"
    assert parse_date("nonsense") is None


def test_date_range_cross_month():
    # 格拉 2026-27 页实测格式：'Monday 30 November - Friday 11 December 2026'
    assert date_range("Monday 30 November - Friday 11 December 2026") == \
        ("2026-11-30", "2026-12-11")


def test_ielts_ignores_year_pollution():
    # 实战 bug：'4 years' 的 4 曾被当成单项最低分
    overall, each = ielts("IELTS 6.5 overall with 6.0 in each. Course lasts 4 years.")
    assert overall == 6.5 and each == 6.0


def test_ielts_absent():
    assert ielts("no english requirements mentioned") == (None, None)


def test_fee_near_excludes_scholarship():
    # 实战 bug：谢菲 £3,000 奖学金曾被当学费
    txt = "International students\n£3,000 scholarships for international students"
    assert fee_near(txt, ("International",)) is None


def test_fee_near_accepts_plausible_fee():
    txt = "International & EU\nFull-time fee:\n£34,470"
    assert fee_near(txt, ("International & EU",)) == 34470.0


def test_band():
    assert band("requires Band C for this course", letters="A-E") == "band-C"
    assert band("no banding here") is None


def test_norm_ws():
    assert norm_ws("  a \n b\t c ") == "a b c"
