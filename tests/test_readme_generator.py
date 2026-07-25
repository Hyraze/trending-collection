import os
import datetime
import pytest
from readme_generator import parse_day_file


SAMPLE_DAY = """\
## 2026-05-27

#### python
* [anthropics / knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins):Open source plugins
* [sherlock-project / sherlock](https://github.com/sherlock-project/sherlock):Hunt down social accounts
* [paperless-ngx / paperless-ngx](https://github.com/paperless-ngx/paperless-ngx):Document management
* [zed-industries / zed](https://github.com/zed-industries/zed):High-performance code editor

#### rust
* [zed-industries / zed](https://github.com/zed-industries/zed):High-performance code editor
* [astral-sh / uv](https://github.com/astral-sh/uv):Fast Python package manager

#### javascript
* [facebook / react](https://github.com/facebook/react):The library for web and native UIs

#### go
* [kubernetes / kubernetes](https://github.com/kubernetes/kubernetes):Production-grade container scheduler

#### swift
* [Alamofire / Alamofire](https://github.com/Alamofire/Alamofire):Elegant HTTP Networking in Swift

#### typescript
* [microsoft / TypeScript](https://github.com/microsoft/TypeScript):TypeScript is a superset of JavaScript
"""


@pytest.fixture
def archive(tmp_path):
    """Create a minimal archive tree with 3 days across 2 years."""
    # today: 2026-05-27
    day1_dir = tmp_path / "2026"
    day1_dir.mkdir()
    (day1_dir / "2026-05-27.md").write_text(SAMPLE_DAY, encoding="utf-8")

    # yesterday: 2026-05-26 (same repos, different order)
    day2 = """\
## 2026-05-26

#### python
* [donnemartin / system-design-primer](https://github.com/donnemartin/system-design-primer):System design
* [anthropics / knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins):Open source plugins

#### rust
* [zed-industries / zed](https://github.com/zed-industries/zed):High-performance code editor
"""
    (day1_dir / "2026-05-26.md").write_text(day2, encoding="utf-8")

    # older year
    old_dir = tmp_path / "2025"
    old_dir.mkdir()
    old_day = """\
## 2025-01-01

#### python
* [vinta / awesome-python](https://github.com/vinta/awesome-python):Awesome Python list
"""
    (old_dir / "2025-01-01.md").write_text(old_day, encoding="utf-8")

    return tmp_path


def test_parse_day_file_returns_all_repos(archive):
    filepath = archive / "2026" / "2026-05-27.md"
    entries = parse_day_file(str(filepath))
    assert len(entries) == 10


def test_parse_day_file_entry_shape(archive):
    filepath = archive / "2026" / "2026-05-27.md"
    entries = parse_day_file(str(filepath))
    entry = entries[0]
    assert entry["url"] == "https://github.com/anthropics/knowledge-work-plugins"
    assert entry["description"] == "Open source plugins"
    assert entry["language"] == "python"


def test_parse_day_file_respects_language_sections(archive):
    filepath = archive / "2026" / "2026-05-27.md"
    entries = parse_day_file(str(filepath))
    langs = [e["language"] for e in entries]
    assert langs.count("python") == 4
    assert langs.count("rust") == 2
    assert langs.count("javascript") == 1
    assert langs.count("go") == 1
    assert langs.count("swift") == 1
    assert langs.count("typescript") == 1


from readme_generator import count_total_days, compute_last_7_days


def test_count_total_days(archive):
    assert count_total_days(str(archive)) == 3  # 2 in 2026, 1 in 2025


def test_compute_last_7_days_returns_available_days(archive):
    today = datetime.date(2026, 5, 27)
    result = compute_last_7_days(str(archive), today=today)
    dates = [d["date"] for d in result]
    assert "2026-05-27" in dates
    assert "2026-05-26" in dates


def test_compute_last_7_days_top1_per_lang(archive):
    today = datetime.date(2026, 5, 27)
    result = compute_last_7_days(str(archive), today=today)
    day = next(d for d in result if d["date"] == "2026-05-27")
    assert day["top"]["python"] == "https://github.com/anthropics/knowledge-work-plugins"
    assert day["top"]["rust"] == "https://github.com/zed-industries/zed"


def test_compute_last_7_days_skips_missing_files(archive):
    today = datetime.date(2026, 5, 27)
    result = compute_last_7_days(str(archive), today=today)
    # Only 2 days exist in 2026 — no file for 2026-05-25 through 2026-05-21
    assert len(result) == 2


from readme_generator import compute_hall_of_fame


def test_compute_hall_of_fame_returns_sorted_by_days(archive):
    result = compute_hall_of_fame(str(archive))
    days = [entry["days"] for entry in result]
    assert days == sorted(days, reverse=True)


def test_compute_hall_of_fame_deduplicates_per_day(archive):
    # knowledge-work-plugins appears in both 2026-05-27 and 2026-05-26 → 2 days
    result = compute_hall_of_fame(str(archive))
    kwp = "https://github.com/anthropics/knowledge-work-plugins"
    entry = next((e for e in result if e["url"] == kwp), None)
    assert entry is not None
    assert entry["days"] == 2


def test_compute_hall_of_fame_deduplicates_within_day(archive):
    # zed appears in both python and rust on 2026-05-27 AND in rust on 2026-05-26 → 2 days total (not 3)
    result = compute_hall_of_fame(str(archive))
    zed = next((e for e in result if "zed-industries" in e["url"]), None)
    assert zed is not None
    assert zed["days"] == 2


def test_compute_hall_of_fame_top_n(archive):
    result = compute_hall_of_fame(str(archive), top_n=2)
    assert len(result) == 2


from readme_generator import compute_new_this_month


def test_compute_new_this_month_finds_recent_first_appearances(archive):
    today = datetime.date(2026, 5, 27)
    result = compute_new_this_month(str(archive), today=today)
    urls = [e["url"] for e in result]
    # sherlock only appears on 2026-05-27, well within 30 days
    assert "https://github.com/sherlock-project/sherlock" in urls


def test_compute_new_this_month_excludes_old_repos(archive):
    today = datetime.date(2026, 5, 27)
    result = compute_new_this_month(str(archive), today=today)
    urls = [e["url"] for e in result]
    # awesome-python first appeared on 2025-01-01, more than 30 days ago
    assert "https://github.com/vinta/awesome-python" not in urls


def test_compute_new_this_month_sorted_by_first_seen_desc(archive):
    today = datetime.date(2026, 5, 27)
    result = compute_new_this_month(str(archive), today=today)
    dates = [e["first_seen"] for e in result]
    assert dates == sorted(dates, reverse=True)


def test_compute_new_this_month_respects_max_results(archive):
    today = datetime.date(2026, 5, 27)
    result = compute_new_this_month(str(archive), today=today, max_results=2)
    assert len(result) <= 2


from readme_generator import render_readme


@pytest.fixture
def rendered(archive):
    today = datetime.date(2026, 5, 27)
    today_str = "2026-05-27"
    filepath = archive / "2026" / "2026-05-27.md"
    from readme_generator import parse_day_file, compute_last_7_days, compute_hall_of_fame, compute_new_this_month, count_total_days
    today_entries = parse_day_file(str(filepath))
    last7 = compute_last_7_days(str(archive), today=today)
    hof = compute_hall_of_fame(str(archive))
    ntm = compute_new_this_month(str(archive), today=today)
    total = count_total_days(str(archive))
    year_list = ["2025", "2026"]
    return render_readme(today_entries, last7, hof, ntm, total, year_list, today_str)


def test_render_readme_has_title(rendered):
    assert "# 📈 GitHub Trending Collection" in rendered


def test_render_readme_has_today_section(rendered):
    assert "🔥 Today's Trending" in rendered
    assert "2026-05-27" in rendered


def test_render_readme_top3_per_language(rendered):
    # Python has 4 repos in sample — only first 3 should appear
    assert "knowledge-work-plugins" in rendered
    assert "sherlock" in rendered
    assert "paperless-ngx" in rendered


def test_render_readme_has_last_7_days(rendered):
    assert "📅 Last 7 Days" in rendered
    assert "2026-05-26" in rendered


def test_render_readme_has_hall_of_fame(rendered):
    assert "🏆 Hall of Fame" in rendered
    assert "knowledge-work-plugins" in rendered


def test_render_readme_has_new_this_month(rendered):
    assert "🆕 New This Month" in rendered


def test_render_readme_has_archive(rendered):
    assert "🗄 Archive" in rendered
    assert "[2026]" in rendered
    assert "[2025]" in rendered


def test_render_readme_badges_show_total_days(rendered):
    assert "3" in rendered  # total_days from fixture


from readme_generator import update_readme, MARKER_START, MARKER_END


def test_update_readme_creates_dynamic_zone(archive):
    readme = archive / "README.md"
    readme.write_text(f"{MARKER_START}\nold content\n{MARKER_END}\n", encoding="utf-8")
    today = datetime.date(2026, 5, 27)
    update_readme(str(archive), today=today)
    content = readme.read_text(encoding="utf-8")
    assert MARKER_START in content
    assert MARKER_END in content
    assert "old content" not in content
    assert "🔥 Today's Trending" in content


def test_update_readme_preserves_content_outside_markers(archive):
    readme = archive / "README.md"
    readme.write_text(
        f"BEFORE\n{MARKER_START}\nold\n{MARKER_END}\nAFTER\n",
        encoding="utf-8"
    )
    today = datetime.date(2026, 5, 27)
    update_readme(str(archive), today=today)
    content = readme.read_text(encoding="utf-8")
    assert content.startswith("BEFORE\n")
    assert content.endswith("AFTER\n")


def test_update_readme_writes_markers_if_missing(archive):
    readme = archive / "README.md"
    readme.write_text("No markers here\n", encoding="utf-8")
    today = datetime.date(2026, 5, 27)
    update_readme(str(archive), today=today)
    content = readme.read_text(encoding="utf-8")
    assert MARKER_START in content
    assert "🔥 Today's Trending" in content
