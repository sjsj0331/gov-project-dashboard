# 정부 기관 사이트를 크롤링하여 index.html의 공고 목록을 자동 업데이트
import re
import os
import warnings
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings('ignore')  # SSL 경고 숨김

TODAY = date.today()
TODAY_STR = TODAY.strftime('%Y-%m-%d')
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_PATH = os.path.join(BASE_DIR, 'index.html')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
}


def dday_info(deadline_str):
    if not deadline_str:
        return 'neutral', '상시'
    try:
        dl = datetime.strptime(deadline_str, '%Y-%m-%d').date()
        diff = (dl - TODAY).days
        if diff < 0:
            return None, None
        if diff == 0:
            return 'urgent', '오늘'
        if diff <= 5:
            return 'urgent', f'D-{diff}'
        if diff <= 10:
            return 'warning', f'D-{diff}'
        return 'safe', f'D-{diff}'
    except ValueError:
        return 'neutral', '상시'


def make_li(title, href, deadline_str='', meta=''):
    cls, text = dday_info(deadline_str)
    if cls is None:
        return None
    title_esc = (title
                 .replace('&', '&amp;')
                 .replace('<', '&lt;')
                 .replace('>', '&gt;')
                 .replace('"', '&quot;'))
    return (
        f'          <li class="announcement-item">\n'
        f'            <div class="announcement-row">\n'
        f'              <a class="announcement-link" href="{href}" target="_blank" rel="noopener">\n'
        f'                <span class="dday {cls}" data-deadline="{deadline_str}">{text}</span>\n'
        f'                <div class="announcement-content">\n'
        f'                  <div class="announcement-title">{title_esc}</div>\n'
        f'                  <div class="announcement-meta">{meta}</div>\n'
        f'                </div>\n'
        f'              </a>\n'
        f'              <button class="bookmark-btn" onclick="toggleBookmark(this)" title="북마크">☆</button>\n'
        f'            </div>\n'
        f'          </li>'
    )


def find_last_date(text):
    """텍스트에서 마지막 날짜(마감일)를 추출 — YYYY-MM-DD 형식으로 반환."""
    matches = re.findall(r'(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})', text)
    for y, mo, d in reversed(matches):
        try:
            return date(int(y), int(mo), int(d)).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return ''


# ── NIPA ──────────────────────────────────────────────────────────────────────
def scrape_nipa():
    url = 'https://www.nipa.kr/home/bsnsAll/0/nttList?bbsNo=4&tab=2'
    base = 'https://www.nipa.kr/home/bsnsAll/0/'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'lxml')

        items, seen = [], set()
        for a in soup.find_all('a', href=re.compile(r'nttNo=\d+')):
            title = a.get_text(strip=True)
            href = a.get('href', '')
            if not title or len(title) < 5 or href in seen:
                continue
            seen.add(href)

            if href.startswith('./'):
                href = base + href[2:]
            elif not href.startswith('http'):
                href = base + href.lstrip('/')

            row = a.find_parent('tr') or a.find_parent('li') or a.find_parent()
            deadline = find_last_date(row.get_text()) if row else ''

            meta = f'<span>마감 {deadline}</span>' if deadline else ''
            li = make_li(title, href, deadline, meta)
            if li:
                items.append(li)
                if len(items) >= 5:
                    break

        print(f'NIPA: {len(items)}건')
        return items
    except Exception as e:
        print(f'NIPA 오류: {e}')
        return []


# ── KHIDI ─────────────────────────────────────────────────────────────────────
def scrape_khidi():
    url = 'https://www.khidi.or.kr/board?menuId=MENU01108'
    base = 'https://www.khidi.or.kr'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'lxml')

        items, seen = [], set()
        for row in soup.select('table tr'):
            a = row.find('a', href=re.compile(r'(linkId|no1)=\d+'))
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get('href', '')
            if not title or len(title) < 5 or href in seen:
                continue
            seen.add(href)

            if not href.startswith('http'):
                href = base + href

            row_text = row.get_text()
            deadline = find_last_date(row_text)

            # 마감일이 이미 지난 항목 제외
            if deadline:
                try:
                    dl = datetime.strptime(deadline, '%Y-%m-%d').date()
                    if (dl - TODAY).days < 0:
                        continue
                except ValueError:
                    pass

            meta = f'<span>마감 {deadline}</span>' if deadline else ''
            li = make_li(title, href, deadline, meta)
            if li:
                items.append(li)
                if len(items) >= 5:
                    break

        print(f'KHIDI: {len(items)}건')
        return items
    except Exception as e:
        print(f'KHIDI 오류: {e}')
        return []


# ── GJTP ──────────────────────────────────────────────────────────────────────
def scrape_gjtp():
    url = 'https://www.gjtp.or.kr/home/business.cs?m=8'
    base = 'https://www.gjtp.or.kr'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'lxml')

        items, seen = [], set()
        for row in soup.select('table tr'):
            cells = row.find_all('td')
            if not cells:
                continue

            # 마지막 셀이 접수 상태 — "접수마감"이면 건너뜀
            status = cells[-1].get_text(strip=True)
            if '마감' in status or '준비' in status:
                continue

            a = row.find('a', href=re.compile(r'bsnssId=\d+'))
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get('href', '')
            if not title or len(title) < 5 or href in seen:
                continue
            seen.add(href)

            m = re.search(r'bsnssId=(\d+)', href)
            if m:
                href = f'{base}/home/business.cs?act=view&bsnssId={m.group(1)}'
            elif not href.startswith('http'):
                href = base + href

            # 기간 셀에서 마감일 추출 (예: "2026-06-01 ~ 2026-07-16")
            row_text = row.get_text()
            deadline = find_last_date(row_text)

            meta = f'<span>마감 {deadline}</span>' if deadline else ''
            li = make_li(title, href, deadline, meta)
            if li:
                items.append(li)
                if len(items) >= 5:
                    break

        print(f'GJTP: {len(items)}건')
        return items
    except Exception as e:
        print(f'GJTP 오류: {e}')
        return []


# ── DGTP ──────────────────────────────────────────────────────────────────────
def scrape_dgtp():
    url = 'https://dgtp.or.kr/bbs/BoardControll.do?bbsId=BBSMSTR_000000000003'
    base = 'https://dgtp.or.kr'
    try:
        r = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        r.encoding = 'utf-8'
        soup = BeautifulSoup(r.text, 'lxml')

        items, seen = [], set()
        for row in soup.select('table tr'):
            a = row.find('a', href=re.compile(r'nttId=\d+'))
            if not a:
                continue
            title = a.get_text(strip=True)
            href = a.get('href', '')
            if not title or len(title) < 5 or href in seen:
                continue
            seen.add(href)

            if not href.startswith('http'):
                href = base + href

            row_text = row.get_text()
            deadline = find_last_date(row_text)

            meta = f'<span>마감 {deadline}</span>' if deadline else ''
            li = make_li(title, href, deadline, meta)
            if li:
                items.append(li)
                if len(items) >= 5:
                    break

        print(f'DGTP: {len(items)}건')
        return items
    except Exception as e:
        print(f'DGTP 오류: {e}')
        return []


# ── HTML 업데이트 ──────────────────────────────────────────────────────────────
def replace_section(html, agency, new_items):
    if not new_items:
        print(f'{agency}: 항목 없음, 기존 데이터 유지')
        return html

    new_content = '\n'.join(new_items)
    pattern = (
        rf'(<!-- {agency} -->.*?<ul class="announcement-list">)'
        rf'.*?'
        rf'(</ul>)'
    )
    replacement = rf'\1\n{new_content}\n        \2'
    result, n = re.subn(pattern, replacement, html, count=1, flags=re.DOTALL)
    if n == 0:
        print(f'{agency}: HTML에서 섹션을 찾지 못함')
    return result


def main():
    with open(INDEX_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    original = html

    nipa  = scrape_nipa()
    khidi = scrape_khidi()
    gjtp  = scrape_gjtp()
    dgtp  = scrape_dgtp()

    html = replace_section(html, 'NIPA',  nipa)
    html = replace_section(html, 'KHIDI', khidi)
    html = replace_section(html, 'GJTP',  gjtp)
    html = replace_section(html, 'DGTP',  dgtp)

    # 날짜 업데이트
    html = re.sub(
        r'(<span id="dataDate">)[^<]*(</span>)',
        rf'\g<1>{TODAY_STR}\g<2>', html
    )
    html = re.sub(
        r'(<strong id="footerDate">)[^<]*(</strong>)',
        rf'\g<1>{TODAY_STR}\g<2>', html
    )

    if html == original:
        print('변경사항 없음')
        return

    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'저장 완료: {INDEX_PATH}')


if __name__ == '__main__':
    main()
