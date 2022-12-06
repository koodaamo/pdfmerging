import sys
from pathlib import Path
from .merging import merge_file


def produce_pdf(source_pdf_path:Path, fields_dump_path:Path, merged_file_path:Path, data:dict):
    doc = merge_file(source_pdf_path, fields_dump_path, data)
    with open(merged_file_path, mode='wb') as out:
        out.write(doc.tobytes())






