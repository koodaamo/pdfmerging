import sys
import fitz
import yaml
from pathlib import Path
from .merging import merge_file, extract_fields


def produce_definitions(definitions_pdf_path:Path, fields_dump_path:Path):
    with fitz.open(definitions_pdf_path) as defs:
        fields = extract_fields(defs)
        with open(fields_dump_path, "w", encoding="utf-8") as dumpfile:
            dumpfile.write(yaml.dump(tuple(fields)))

def produce_merged(source_pdf_path:Path, fields_dump_path:Path, merged_file_path:Path, data:dict):
    doc = merge_file(source_pdf_path, fields_dump_path, data)
    with open(merged_file_path, mode='wb') as out:
        out.write(doc.tobytes())






