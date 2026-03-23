"""
DSD file extractor.
DSD files are ZIP archives containing contents.xml and meta.xml.
"""

import os
import tempfile
import zipfile
from lxml import etree


def extract_dsd(file_path: str) -> dict:
    """
    Extract a DSD ZIP file and parse its XML contents.

    Returns:
        dict with keys:
            - 'contents_tree': lxml ElementTree for contents.xml
            - 'meta_tree': lxml ElementTree for meta.xml (or None)
            - 'temp_dir': path to temp directory (caller should clean up)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"DSD file not found: {file_path}")

    if not zipfile.is_zipfile(file_path):
        raise ValueError(f"Not a valid ZIP/DSD file: {file_path}")

    temp_dir = tempfile.mkdtemp(prefix="dsd_extract_")

    with zipfile.ZipFile(file_path, 'r') as zf:
        zf.extractall(temp_dir)

    contents_path = os.path.join(temp_dir, "contents.xml")
    meta_path = os.path.join(temp_dir, "meta.xml")

    if not os.path.exists(contents_path):
        raise FileNotFoundError(f"contents.xml not found in DSD archive: {file_path}")

    # Parse contents.xml with lxml
    # DSD files may contain &amp;cr; (literal text) and &cr; (entity reference).
    # The &amp;cr; in raw XML becomes &cr; after XML parsing (as text content).
    # We use a custom parser that recovers from errors.
    parser = etree.XMLParser(recover=True, encoding='utf-8')
    contents_tree = etree.parse(contents_path, parser)

    meta_tree = None
    if os.path.exists(meta_path):
        meta_tree = etree.parse(meta_path, parser)

    return {
        'contents_tree': contents_tree,
        'meta_tree': meta_tree,
        'temp_dir': temp_dir,
    }
