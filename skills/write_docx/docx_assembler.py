"""
Repackage modified XML back into a DOCX ZIP archive.

A DOCX file is just a ZIP containing XML parts (document.xml,
header1.xml, styles.xml, …), images, fonts, and relationship files.
This module opens the original DOCX, replaces the modified XML parts,
and writes everything to a new ZIP file — preserving every other file
(styles, fonts, media, etc.) byte-for-byte.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

from lxml import etree


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def assemble_docx(
    template_path: str,
    output_path: str,
    modified_parts: dict[str, etree._Element],
) -> str:
    """
    Build a new DOCX from a template, replacing specific XML parts.

    Args:
        template_path:   Path to the original DOCX file.
        output_path:     Path where the new DOCX will be written.
        modified_parts:  Mapping of ZIP-internal path → lxml root element,
                         e.g. ``{"word/document.xml": <Element>}``.

    Returns:
        The *output_path* for convenience.
    """
    # Ensure output directory exists
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    # Serialize modified parts to bytes
    serialized: dict[str, bytes] = {}
    for part_name, root_elem in modified_parts.items():
        xml_bytes = etree.tostring(
            root_elem,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )
        serialized[part_name] = xml_bytes

    # Rewrite the ZIP, replacing only the modified parts
    with zipfile.ZipFile(template_path, "r") as zin:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in serialized:
                    zout.writestr(item, serialized[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))

    return output_path
