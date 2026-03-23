import base64
import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import logging

##获取ant design x官网的所有的文档

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


def check_rate_limit(headers, session):
    """
    检查GitHub API限额状态，若超限则等待重置。
    """
    try:
        response = session.get("https://api.github.com/rate_limit", headers=headers, timeout=60)
        response.raise_for_status()
        rate_limit_data = response.json()["rate"]
        remaining = rate_limit_data["remaining"]
        reset_time = rate_limit_data["reset"]
        logger.info(f"Rate limit: {remaining} requests remaining, resets at {time.ctime(reset_time)}")

        if remaining == 0:
            wait_time = reset_time - int(time.time()) + 1
            if wait_time > 0:
                logger.warning(f"Rate limit exceeded. Waiting {wait_time} seconds until reset.")
                time.sleep(wait_time)
                return check_rate_limit(headers, session)
        return True
    except Exception as e:
        logger.error(f"Error checking rate limit: {str(e)}")
        return False


def extract_title_from_content(content: str) -> str:
    """从 Markdown 内容提取一级标题。"""
    if not content:
        return ""
    match = re.search(r'^# (.+)$', content, re.MULTILINE)
    return match.group(1).strip() if match else ""


def get_markdown_title(md_url, headers, session, timeout=20):
    """
    下载 Markdown 文件并提取一级标题。失败时返回空字符串。
    """
    try:
        response = session.get(md_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return extract_title_from_content(response.text)
    except Exception as e:
        logger.error(f"Error fetching title from {md_url}: {str(e)}")
        return ""


def scrape_web_docs(repo_url, base_html_url="https://ant-design-x.antgroup.com", token=None):
    """
    递归扫描GitHub仓库main目录，收集所有 .md 文件的URL、HTML URL和标题，
    生成 antdesignx_docs_Internet.json，包含 theme、url、html_url 和 title。
    Markdown内容仅在内存中处理，运行结束释放。

    Args:
        repo_url (str): GitHub仓库目录URL（例如 'https://github.com/ant-design/x/tree/main/'）
        base_html_url (str): Ant design X文档网站根URL（例如 'https://ant-design-x.antgroup.com'）
        token (str, optional): GitHub Personal Access Token，提高API限额

    Returns:
        list: 包含文档信息的列表，每个文档包含 theme、url、html_url 和 title
    """
    docs = []

    # 配置请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/vnd.github.v3+json'
    }
    if token:
        headers['Authorization'] = f'token {token}'

    # 配置重试机制（raw.githubusercontent.com 国内访问慢，减少重试次数加快失败跳过）
    session = requests.Session()
    retries = Retry(total=2, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))

    # 手动文件名映射
    filename_map = {

    }

    json_path = Path(__file__).parent / "antdesignx.json"

    def save_docs(docs_list):
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"documents": docs_list}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error writing to JSON file: {e}")

    def scan_directory(url, docs, depth=0):
        if not check_rate_limit(headers, session):
            logger.error(f"{'  ' * depth}Skipping directory {url} due to rate limit check failure")
            return

        try:
            response = session.get(url, headers=headers, timeout=60)
            logger.info(f"{'  ' * depth}Fetching GitHub API {url}: Status {response.status_code}")
            response.raise_for_status()
            contents = response.json()

            for item in contents:
                if item['type'] == 'file' and item['name'].endswith('.md'):
                    theme = item['name'].replace('.md', '')
                    md_url = item['download_url']
                    # 生成HTML URL，去掉 main
                    relative_path = md_url.split('/main/')[-1]
                    html_filename = filename_map.get(theme, theme)
                    html_path = relative_path.replace(theme + '.md', html_filename + '.html')
                    html_url = f"{base_html_url}/{html_path}"
                    # 优先通过 GitHub API 获取 content（比 raw.githubusercontent.com 在国内更稳定）
                    title = ""
                    try:
                        file_resp = session.get(item['url'], headers=headers, timeout=15)
                        if file_resp.ok and file_resp.json().get('content'):
                            content = base64.b64decode(file_resp.json()['content']).decode('utf-8', errors='ignore')
                            title = extract_title_from_content(content)
                    except Exception:
                        pass
                    if not title:
                        title = get_markdown_title(md_url, headers, session)

                    docs.append({
                        "theme": theme,
                        "url": md_url,
                        "html_url": html_url,
                        "title": title
                    })
                    logger.info(
                        f"{'  ' * depth}Added file: {theme}, Markdown: {md_url}, HTML: {html_url}, Title: {title}")
                    # 每 10 个文档增量保存，避免中断丢失已抓取内容
                    if len(docs) % 10 == 0:
                        save_docs(docs)
                elif item['type'] == 'dir':
                    logger.info(f"{'  ' * depth}Entering directory: {item['path']}")
                    scan_directory(item['url'], docs, depth + 1)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code in [429, 403]:
                reset_time = int(e.response.headers.get('x-ratelimit-reset', 0))
                wait_time = reset_time - int(time.time()) + 1 if reset_time > 0 else 60
                logger.warning(f"{'  ' * depth}Rate limit error for {url}. Waiting {wait_time} seconds.")
                time.sleep(wait_time)
                scan_directory(url, docs, depth)
            else:
                logger.error(f"{'  ' * depth}Error scanning {url}: {str(e)}")
        except Exception as e:
            logger.error(f"{'  ' * depth}Error scanning {url}: {str(e)}")

    # 扫描GitHub目录
    api_url = repo_url.replace(
        "https://github.com/", "https://api.github.com/repos/"
    ).replace("/tree/main/", "/contents/")
    logger.info(f"Starting scan of {repo_url}")
    scan_directory(api_url, docs)

    # 保存到JSON文件
    try:
        save_docs(docs)
        logger.info(f"JSON file created: {json_path} with {len(docs)} documents")
        if len(docs) < 142:
            logger.warning(f"Expected Markdown files, but found {len(docs)}")
    except Exception as e:
        logger.error(f"Error writing to JSON file: {str(e)}")

    return docs


if __name__ == "__main__":
    repo_url = "https://github.com/ant-design/x/tree/main/"  # GitHub 文档仓库目录
    base_html_url = "https://ant-design-x.antgroup.com"  # ant design x 文档网站根地址
    github_token = os.environ.get("GITHUB_TOKEN")  # 可选：设置 GITHUB_TOKEN 环境变量提高 API 限额
    scrape_web_docs(repo_url, base_html_url, github_token)


