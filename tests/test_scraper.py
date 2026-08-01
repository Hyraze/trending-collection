import datetime

import pytest
import requests

from gitreposcraper import (
    ScrapeError,
    parse_trending_html,
    render_day,
    scrape,
    write_day,
)


TRENDING_HTML = """
<div class="Box">
  <article class="Box-row">
    <h2 class="lh-condensed">
      <a href="/astral-sh/uv">
        <span class="text-normal">astral-sh / </span>uv
      </a>
    </h2>
    <p class="col-9">An extremely fast Python package manager</p>
  </article>
  <article class="Box-row">
    <h2 class="lh-condensed">
      <a href="/psf/black">
        <span class="text-normal">psf / </span>black
      </a>
    </h2>
    <p class="col-9">The uncompromising code formatter</p>
  </article>
</div>
"""

EMPTY_HTML = '<div class="Box"></div>'


class FakeResponse:
    def __init__(self, content, status_code=200):
        self.content = content.encode("utf-8")
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class FakeSession:
    """Records the kwargs each request was made with."""

    def __init__(self, response):
        self._response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


# --- parsing -----------------------------------------------------------------


def test_parse_trending_html_extracts_repos():
    repos = parse_trending_html(TRENDING_HTML)

    assert repos == [
        {
            "title": "astral-sh / uv",
            "url": "https://github.com/astral-sh/uv",
            "description": "An extremely fast Python package manager",
            "language": "",
            "languageColor": None,
            "stars": 0,
            "forks": 0,
            "added_stars": "",
        },
        {
            "title": "psf / black",
            "url": "https://github.com/psf/black",
            "description": "The uncompromising code formatter",
            "language": "",
            "languageColor": None,
            "stars": 0,
            "forks": 0,
            "added_stars": "",
        },
    ]


def test_parse_trending_html_handles_missing_description():
    html = """
    <div class="Box">
      <article class="Box-row">
        <h2 class="lh-condensed"><a href="/a/b"><span class="text-normal">a / </span>b</a></h2>
      </article>
    </div>
    """

    assert parse_trending_html(html) == [
        {
            "title": "a / b",
            "url": "https://github.com/a/b",
            "description": "",
            "language": "",
            "languageColor": None,
            "stars": 0,
            "forks": 0,
            "added_stars": "",
        }
    ]


# --- scrape ------------------------------------------------------------------


def test_scrape_sends_timeout():
    session = FakeSession(FakeResponse(TRENDING_HTML))

    scrape(session, "python")

    url, kwargs = session.calls[0]
    assert url == "https://github.com/trending/python?since=daily"
    assert kwargs["timeout"] == pytest.approx(30)


def test_scrape_raises_on_empty_results():
    """Selector rot must fail loudly, not write an empty section."""
    session = FakeSession(FakeResponse(EMPTY_HTML))

    with pytest.raises(ScrapeError, match="python"):
        scrape(session, "python")


def test_scrape_raises_on_http_error():
    session = FakeSession(FakeResponse(EMPTY_HTML, status_code=503))

    with pytest.raises(requests.HTTPError):
        scrape(session, "python")


# --- rendering ---------------------------------------------------------------


def test_render_day_matches_archive_format():
    sections = {
        "python": [
            {
                "title": "astral-sh / uv",
                "url": "https://github.com/astral-sh/uv",
                "description": "Fast",
            }
        ],
        "rust": [
            {
                "title": "a / b",
                "url": "https://github.com/a/b",
                "description": "Desc",
            }
        ],
    }

    result = render_day("2026-07-27", ["python", "rust"], sections)

    assert result == (
        "## 2026-07-27\n"
        "\n"
        "#### python\n"
        "* [astral-sh / uv](https://github.com/astral-sh/uv):Fast\n"
        "\n"
        "#### rust\n"
        "* [a / b](https://github.com/a/b):Desc\n"
    )


def test_render_day_orders_sections_by_language_list():
    sections = {
        "rust": [{"title": "r", "url": "u", "description": "d"}],
        "python": [{"title": "p", "url": "u", "description": "d"}],
    }

    result = render_day("2026-07-27", ["python", "rust"], sections)

    assert result.index("#### python") < result.index("#### rust")


# --- atomic write ------------------------------------------------------------


def test_write_day_creates_year_folder(tmp_path):
    path = write_day(str(tmp_path), "2026-07-27", "## 2026-07-27\n")

    assert (tmp_path / "2026" / "2026-07-27.md").read_text(encoding="utf-8") == (
        "## 2026-07-27\n"
    )
    assert path == str(tmp_path / "2026" / "2026-07-27.md")


def test_write_day_leaves_no_temp_files(tmp_path):
    write_day(str(tmp_path), "2026-07-27", "## 2026-07-27\n")

    assert [p.name for p in (tmp_path / "2026").iterdir()] == ["2026-07-27.md"]


def test_write_day_overwrites_existing_day(tmp_path):
    write_day(str(tmp_path), "2026-07-27", "old\n")
    write_day(str(tmp_path), "2026-07-27", "new\n")

    assert (tmp_path / "2026" / "2026-07-27.md").read_text(encoding="utf-8") == "new\n"


# --- job atomicity -----------------------------------------------------------


def test_job_writes_nothing_when_a_later_language_fails(tmp_path, monkeypatch):
    """A partial day must never reach disk — CI would commit it into the archive."""
    import gitreposcraper

    def fake_scrape(session, language, since="daily"):
        if language == "go":
            raise ScrapeError("boom")
        return [{"title": "a / b", "url": "https://github.com/a/b", "description": "d"}]

    monkeypatch.setattr(gitreposcraper, "scrape", fake_scrape)
    monkeypatch.setattr(gitreposcraper, "make_session", lambda: None)
    monkeypatch.setattr(
        gitreposcraper, "update_readme", lambda **kwargs: pytest.fail("must not run")
    )

    with pytest.raises(ScrapeError):
        gitreposcraper.job(root=str(tmp_path), today=datetime.date(2026, 7, 27))

    assert not (tmp_path / "2026").exists()
