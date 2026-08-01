import os
import re
import datetime

REPO_RE = re.compile(r'^\* \[.+?\]\((https://github\.com/[^)]+)\):(.*)$')
LANG_RE = re.compile(r'^#### (\w+)$')

LANG_EMOJI = {
    'python': '🐍',
    'rust': '🦀',
    'javascript': '⚡',
    'go': '🐹',
    'swift': '🍎',
    'typescript': '🔷',
}
LANGUAGES = ['python', 'rust', 'javascript', 'go', 'swift', 'typescript']

MARKER_START = '<!-- TRENDING_START -->'
MARKER_END = '<!-- TRENDING_END -->'


def parse_day_file(filepath):
    """Return list of {url, description, language} from a daily .md file."""
    entries = []
    current_lang = None
    with open(filepath, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            lang_match = LANG_RE.match(line)
            if lang_match:
                current_lang = lang_match.group(1)
                continue
            repo_match = REPO_RE.match(line)
            if repo_match and current_lang:
                entries.append({
                    'url': repo_match.group(1),
                    'description': repo_match.group(2),
                    'language': current_lang,
                })
    return entries


def count_total_days(root='.'):
    count = 0
    for entry in os.listdir(root):
        year_path = os.path.join(root, entry)
        if os.path.isdir(year_path) and entry.isdigit():
            count += sum(1 for f in os.listdir(year_path) if f.endswith('.md'))
    return count


def compute_last_7_days(root='.', today=None):
    if today is None:
        today = datetime.date.today()
    result = []
    for i in range(7):
        d = today - datetime.timedelta(days=i)
        filepath = os.path.join(root, str(d.year), d.strftime('%Y-%m-%d') + '.md')
        if not os.path.exists(filepath):
            continue
        entries = parse_day_file(filepath)
        day_data = {'date': d.strftime('%Y-%m-%d'), 'top': {}}
        seen = set()
        for entry in entries:
            lang = entry['language']
            if lang not in seen:
                day_data['top'][lang] = entry['url']
                seen.add(lang)
        result.append(day_data)
    return result


def compute_hall_of_fame(root='.', top_n=10):
    counts = {}
    for year_entry in sorted(os.listdir(root)):
        year_path = os.path.join(root, year_entry)
        if not (os.path.isdir(year_path) and year_entry.isdigit()):
            continue
        for fname in sorted(os.listdir(year_path)):
            if not fname.endswith('.md'):
                continue
            filepath = os.path.join(year_path, fname)
            entries = parse_day_file(filepath)
            urls_today = {e['url'] for e in entries}
            for url in urls_today:
                counts[url] = counts.get(url, 0) + 1
    top = sorted(counts.items(), key=lambda x: -x[1])[:top_n]
    return [{'url': url, 'days': days} for url, days in top]


def compute_new_this_month(root='.', today=None, max_results=10):
    if today is None:
        today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=30)
    first_seen = {}  # url -> (date, description, language)
    for year_entry in sorted(os.listdir(root)):
        year_path = os.path.join(root, year_entry)
        if not (os.path.isdir(year_path) and year_entry.isdigit()):
            continue
        for fname in sorted(os.listdir(year_path)):
            if not fname.endswith('.md'):
                continue
            date_str = fname[:-3]
            try:
                file_date = datetime.date.fromisoformat(date_str)
            except ValueError:
                continue
            filepath = os.path.join(year_path, fname)
            for entry in parse_day_file(filepath):
                url = entry['url']
                if url not in first_seen:
                    first_seen[url] = (file_date, entry['description'], entry['language'])
    new_repos = [
        {
            'url': url,
            'first_seen': d.strftime('%Y-%m-%d'),
            'description': desc,
            'language': lang,
        }
        for url, (d, desc, lang) in first_seen.items()
        if d > cutoff
    ]
    new_repos.sort(key=lambda x: x['first_seen'], reverse=True)
    return new_repos[:max_results]


def render_readme(today_entries, last7, hall_of_fame, new_this_month, total_days, year_list, today_str):
    lines = []

    # Header
    lines += [
        '# 📈 GitHub Trending Collection',
        '_Daily snapshots of GitHub trending repositories since 2015_',
        '',
        ' '.join([
            f'![](https://img.shields.io/badge/⭐_days_archived-{total_days}-brightgreen?style=flat-square)',
            '![](https://img.shields.io/badge/🌐_languages-6-blue?style=flat-square)',
            '![](https://img.shields.io/badge/🔄_auto--updated-daily-purple?style=flat-square)',
            '![](https://img.shields.io/badge/📅_since-2015-red?style=flat-square)',
        ]),
        '',
        '---',
        '',
    ]

    # Today's trending
    year = today_str[:4]
    day_link = f'./{year}/{today_str}.md'
    lines += [
        f"## 🔥 Today's Trending — {today_str}",
        f'_Top 3 per language · [view full day →]({day_link})_',
        '',
        '| Repository | Lang | Description |',
        '|---|---|---|',
    ]
    by_lang = {}
    for entry in today_entries:
        lang = entry['language']
        if lang not in by_lang:
            by_lang[lang] = []
        if len(by_lang[lang]) < 3:
            by_lang[lang].append(entry)
    for lang in LANGUAGES:
        for entry in by_lang.get(lang, []):
            repo = entry['url'].replace('https://github.com/', '')
            emoji = LANG_EMOJI.get(lang, '')
            lines.append(f'| [{repo}]({entry["url"]}) | {emoji} | {entry["description"]} |')
    lines += ['', '---', '']

    # Last 7 days
    lang_headers = ' | '.join(LANG_EMOJI.get(l, l) for l in LANGUAGES)
    lines += [
        '## 📅 Last 7 Days',
        '',
        f'| Date | {lang_headers} |',
        '|---|' + '---|' * len(LANGUAGES),
    ]
    for day in last7:
        date_link = f'./{day["date"][:4]}/{day["date"]}.md'
        cells = []
        for lang in LANGUAGES:
            url = day['top'].get(lang, '')
            cells.append(f'[{url.split("/")[-1]}]({url})' if url else '—')
        lines.append(f'| [{day["date"]}]({date_link}) | ' + ' | '.join(cells) + ' |')
    year_folder = f'./{today_str[:4]}/'
    lines.append(f'| ... | [_view full archive →_]({year_folder}) | | | | | |')
    lines += ['', '---', '']

    # Hall of fame
    lines += [
        '## 🏆 Hall of Fame',
        '_Most days on trending, all time_',
        '',
        '| Repository | Days on Trending |',
        '|---|---|',
    ]
    for entry in hall_of_fame:
        repo = entry['url'].replace('https://github.com/', '')
        lines.append(f'| [{repo}]({entry["url"]}) | {entry["days"]} |')
    lines += ['', '---', '']

    # New this month
    lines += [
        '## 🆕 New This Month',
        '_Repos appearing on trending for the first time in the last 30 days_',
        '',
        '| Repository | Lang | First Seen | Description |',
        '|---|---|---|---|',
    ]
    for entry in new_this_month:
        repo = entry['url'].replace('https://github.com/', '')
        emoji = LANG_EMOJI.get(entry['language'], '')
        lines.append(f'| [{repo}]({entry["url"]}) | {emoji} | {entry["first_seen"]} | {entry["description"]} |')
    lines += ['', '---', '']

    # Archive
    archive_links = ' · '.join(f'[{y}](./{y}/)' for y in sorted(year_list, reverse=True))
    lines += ['## 🗄 Archive', '', archive_links, '']

    # API & RSS Usage
    lines += [
        '## 🚀 JSON API & RSS Feeds',
        '_This repository provides a free, static JSON API and RSS feeds for GitHub Trending repositories, supporting 700+ languages._',
        '',
        '### Endpoints',
        '- **JSON (All)**: `https://cdn.jsdelivr.net/gh/Hyraze/trending-collection@main/api/daily/all.json`',
        '- **JSON (Specific)**: `https://cdn.jsdelivr.net/gh/Hyraze/trending-collection@main/api/daily/{language}.json`',
        '- **RSS (All)**: `https://cdn.jsdelivr.net/gh/Hyraze/trending-collection@main/api/daily/all.xml`',
        '- **RSS (Specific)**: `https://cdn.jsdelivr.net/gh/Hyraze/trending-collection@main/api/daily/{language}.xml`',
        '',
        '> Replace `{language}` with the lowercase language name (e.g., `python`, `c++`, `javascript`). For spaces, use hyphens (e.g., `1c-enterprise`). We support all 700+ GitHub languages.',
        '',
        '### Example Response (`python.json`)',
        '```json',
        '{',
        '  "title": "GitHub Python Languages Daily Trending",',
        '  "description": "Daily Trending of Python Languages in GitHub",',
        '  "link": "https://github.com/trending",',
        '  "pubDate": "Sat, 01 Aug 2026 14:36:06 GMT",',
        '  "items": [',
        '    {',
        '      "title": "user/repo",',
        '      "url": "https://github.com/user/repo",',
        '      "description": "Repository description here",',
        '      "language": "python"',
        '    }',
        '  ]',
        '}',
        '```',
        ''
    ]

    return '\n'.join(lines)


def update_readme(root='.', today=None):
    if today is None:
        today = datetime.date.today()
    today_str = today.strftime('%Y-%m-%d')

    today_file = os.path.join(root, str(today.year), today_str + '.md')
    today_entries = parse_day_file(today_file) if os.path.exists(today_file) else []

    last7 = compute_last_7_days(root=root, today=today)
    hall_of_fame = compute_hall_of_fame(root=root)
    new_this_month = compute_new_this_month(root=root, today=today)
    total_days = count_total_days(root=root)
    year_list = [
        d for d in os.listdir(root)
        if os.path.isdir(os.path.join(root, d)) and d.isdigit()
    ]

    content = render_readme(today_entries, last7, hall_of_fame, new_this_month, total_days, year_list, today_str)

    readme_path = os.path.join(root, 'README.md')
    with open(readme_path, 'r', encoding='utf-8') as f:
        readme = f.read()

    start_idx = readme.find(MARKER_START)
    end_idx = readme.find(MARKER_END)

    if start_idx == -1 or end_idx == -1:
        new_readme = f'{MARKER_START}\n{content}\n{MARKER_END}\n'
    else:
        before = readme[:start_idx]
        after = readme[end_idx + len(MARKER_END):]
        new_readme = before + MARKER_START + '\n' + content + '\n' + MARKER_END + after

    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(new_readme)
