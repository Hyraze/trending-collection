import os
import time
import requests
import datetime
import codecs
from pyquery import PyQuery as pq

def createMarkdown(date, filename):
    folder_name = date.split('-')[0]
    if not os.path.exists(folder_name):
        os.mkdir(folder_name)
    filename = os.path.join(folder_name, filename)
    with open(filename, 'w') as f:
        f.write("## " + date + "\n")

def gitAddCommitPush(date, filename):
    git_add = 'git add {filename}'.format(filename=filename)
    git_commit = 'git commit -m "{date}"'.format(date=date)
    git_push = 'git push -u origin main'
    os.system(git_add)
    os.system(git_commit)
    os.system(git_push)

def scrape(language, filename):
    HEADERS = {
        'User-Agent'		: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.7; rv:11.0) Gecko/20100101 Firefox/11.0',
        'Accept'			: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding'	: 'gzip,deflate,sdch',
        'Accept-Language'	: 'zh-CN,zh;q=0.8'
    }

    url = 'https://github.com/trending/{language}'.format(language=language)
    r = requests.get(url, headers=HEADERS)
    assert r.status_code == 200
    d = pq(r.content)
    items = d('div.Box article.Box-row')
    folder_name = filename.split('-')[0]
    filename = os.path.join(folder_name, filename)
    with codecs.open(filename, "a", "utf-8") as f:
        f.write('\n#### {language}\n'.format(language=language))

        for item in items:
            i = pq(item)
            title = i(".lh-condensed a").text()
            owner = i(".lh-condensed span.text-normal").text()
            description = i("p.col-9").text()
            url = i(".lh-condensed a").attr("href")
            url = "https://github.com" + url
            # ownerImg = i("p.repo-list-meta a img").attr("src")
            # print(ownerImg)
            f.write(u"* [{title}]({url}):{description}\n".format(title=title, url=url, description=description))


def job():
    strdate = datetime.datetime.now().strftime('%Y-%m-%d')
    filename = '{date}.md'.format(date=strdate)
    createMarkdown(strdate, filename)
    scrape('python', filename)
    scrape('swift', filename)
    scrape('javascript', filename)
    scrape('go', filename)
    # gitAddCommitPush(strdate, filename)


if __name__ == '__main__':
    job()
