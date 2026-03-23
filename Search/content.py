import json
import os
import logging
from pathlib import Path

# Configure logging  拼接json文件中分块的内容
_log_dir = Path(__file__).resolve().parent
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(_log_dir / "extract_content.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)


def _build_content_from_blocks(content_blocks: list) -> str:
    """从 content_blocks 结构拼接为单个 content 字符串"""
    parts = []
    for block in content_blocks:
        h1 = block.get('h1', '')
        h2 = block.get('h2') or '无'
        c = block.get('content', '')
        parts.append(f"一级标题：{h1}\n二级标题：{h2}\n内容：\n{c}")
    return '\n\n'.join(parts) if parts else ''


def extract_fields_to_txt(json_file_path: str, output_txt_path: str = "extracted_fields.txt"):
    """
    从JSON文件中提取content、url和path字段到文本文件
    支持两种JSON结构：
    1. documents_analyzer_url 输出：doc 含 content_blocks（优先）
    2. 旧格式：doc 含 content 字段
    格式示例：
    [CONTENT] 这里是内容文本...
    [URL] https://example.com/path
    [html_url] https://...
    #########################
    """
    try:
        json_path = Path(json_file_path)
        if not json_path.is_absolute():
            json_path = _log_dir.parent / json_file_path.lstrip('/')
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        out_path = Path(output_txt_path)
        if not out_path.is_absolute():
            out_path = _log_dir.parent / output_txt_path.lstrip('/')
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, 'w', encoding='utf-8') as f:
            for doc in data.get('documents', []):
                url = doc.get('url', '')
                html_url = doc.get('html_url', '')
                filename = doc.get('filename', 'unknown.md')

                # 支持 content_blocks（documents_analyzer_url 输出）或 content 字段
                if 'content_blocks' in doc:
                    content = _build_content_from_blocks(doc['content_blocks'])
                else:
                    content = doc.get('content', '')

                if not content.strip():
                    logging.warning(f"Empty content in document: {filename}")
                    continue

                f.write(f"[CONTENT] \n{content}\n")
                f.write(f"[URL] {url}\n")
                f.write(f"[html_url] {html_url}\n")
                f.write("#########################\n\n")

                logging.info(f"Processed: {filename} (URL: {url})")

        logging.info(f"Successfully created {out_path}")

    except FileNotFoundError:
        logging.error(f"JSON file not found: {json_file_path}")
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in {json_file_path}")
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")


if __name__ == "__main__":
    # 与 documents_analyzer_url 输出路径对齐
    json_file_path = "Search/test/antdesignx_docs_Internet-1.json"
    output_txt_path = "Search/antdesignx.txt"
    extract_fields_to_txt(json_file_path, output_txt_path)