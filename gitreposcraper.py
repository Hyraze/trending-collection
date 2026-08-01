"""Scrape GitHub trending repositories and archive them as daily Markdown files."""

import datetime
import logging
import os
import tempfile
import json
import time

import requests
from pyquery import PyQuery as pq
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from readme_generator import LANGUAGES, update_readme

REQUEST_TIMEOUT = 30
RETRY_TOTAL = 4
RETRY_BACKOFF = 2
RETRY_STATUSES = (429, 500, 502, 503, 504)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

logger = logging.getLogger(__name__)


class ScrapeError(RuntimeError):
    """Raised when a trending page yields no repositories."""


def make_session() -> requests.Session:
    """Session that retries transient failures with exponential backoff."""
    session = requests.Session()
    retry = Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=RETRY_STATUSES,
        allowed_methods=frozenset(['GET']),
        raise_on_status=False,
    )
    session.mount('https://', HTTPAdapter(max_retries=retry))
    return session


def parse_trending_html(html) -> list[dict]:
    """Extract repository entries from a GitHub trending page."""
    document = pq(html)
    repos = []
    for item in document('div.Box article.Box-row'):
        element = pq(item)
        href = element('.lh-condensed a').attr('href')
        if not href:
            continue
        repos.append({
            'title': element('.lh-condensed a').text(),
            'url': 'https://github.com' + href,
            'description': element('p.col-9').text(),
        })
    return repos


def scrape(session: requests.Session, language: str) -> list[dict]:
    """Fetch one trending language page.

    Raises ScrapeError when a featured page yields no repositories.
    Non-featured languages just return an empty list.
    """
    url = 'https://github.com/trending/{language}'.format(language=language)
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    repos = parse_trending_html(response.content)
    if not repos:
        if language in LANGUAGES:
            raise ScrapeError(
                'no repositories parsed for {language} — selector rot or blocked request'.format(
                    language=language
                )
            )
        return []
    return repos


def render_day(date: str, languages: list[str], sections: dict[str, list[dict]]) -> str:
    """Render the daily archive file. Format must stay stable — readme_generator parses it."""
    lines = ['## {date}\n'.format(date=date)]
    for language in languages:
        repos = sections.get(language)
        if not repos:
            continue
        lines.append('\n#### {language}\n'.format(language=language))
        for repo in repos:
            lines.append('* [{title}]({url}):{description}\n'.format(**repo))
    return ''.join(lines)


def write_day(root: str, date: str, content: str) -> str:
    """Write the day file atomically so a crash can never leave a partial archive."""
    year_dir = os.path.join(root, date.split('-')[0])
    os.makedirs(year_dir, exist_ok=True)
    target = os.path.join(year_dir, '{date}.md'.format(date=date))

    handle, temp_path = tempfile.mkstemp(dir=year_dir, suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(temp_path, target)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return target


def write_api_json(root: str, sections: dict[str, list[dict]]) -> None:
    """Generate JSON API files for each language and an all.json."""
    api_dir = os.path.join(root, 'api', 'daily')
    os.makedirs(api_dir, exist_ok=True)
    
    pub_date = datetime.datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    all_items = []
    
    for language, repos in sections.items():
        if not repos:
            continue
            
        items = []
        for repo in repos:
            item = {
                "title": repo.get('title', ''),
                "url": repo.get('url', ''),
                "description": repo.get('description', ''),
                "language": language,
            }
            items.append(item)
            all_items.append(item)
            
        lang_data = {
            "title": f"GitHub {language.capitalize()} Languages Daily Trending",
            "description": f"Daily Trending of {language.capitalize()} Languages in GitHub",
            "link": "https://github.com/trending",
            "pubDate": pub_date,
            "items": items
        }
        
        with open(os.path.join(api_dir, f"{language}.json"), 'w', encoding='utf-8') as f:
            json.dump(lang_data, f, indent=2, ensure_ascii=False)
            
    # Write all.json
    all_data = {
        "title": "GitHub Daily Trending",
        "description": "Daily Trending of All Languages in GitHub",
        "link": "https://github.com/trending",
        "pubDate": pub_date,
        "items": all_items
    }
    with open(os.path.join(api_dir, "all.json"), 'w', encoding='utf-8') as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)


def job(root: str = '.', today: datetime.date | None = None) -> str:
    """Scrape all languages, then write the archive and refresh the README.
    
    Featured languages (used in README) must succeed, otherwise we fail loudly.
    Non-featured languages are scraped for the JSON API but failure is ignored.
    """
    today = today or datetime.date.today()
    date = today.strftime('%Y-%m-%d')
    session = make_session()

    all_languages = []
    langs_file = os.path.join(root, 'languages.json')
    if os.path.exists(langs_file):
        with open(langs_file, 'r', encoding='utf-8') as f:
            for item in json.load(f):
                if item.get('aliases'):
                    all_languages.append(item['aliases'][0])
                    
    # Ensure featured languages are always present
    for lang in LANGUAGES:
        if lang not in all_languages:
            all_languages.insert(0, lang)

    sections = {}
    for i, language in enumerate(all_languages):
        is_featured = language in LANGUAGES
        try:
            repos = scrape(session, language)
            if repos:
                sections[language] = repos
                if is_featured:
                    logger.info('%s: %d repositories', language, len(repos))
        except Exception as e:
            if is_featured:
                raise e
            logger.warning('Failed to scrape %s: %s', language, e)
            
        time.sleep(0.5)  # Be nice to GitHub rate limits

    path = write_day(root, date, render_day(date, LANGUAGES, sections))
    write_api_json(root, sections)
    update_readme(root=root, today=today)
    logger.info('wrote %s and api json files', path)
    return path


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    job()
