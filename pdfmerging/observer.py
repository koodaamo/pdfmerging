import asyncio
import logging
from pathlib import Path
from watchfiles import awatch, Change
import magic
import fitz
import yaml
from datetime import datetime, timedelta
from pdfmerging.config import setup_root, templatefile, definitionsfile, fieldsfile, loglevel
from pdfmerging.merging import extract_fields


logging.basicConfig()
logger = logging.getLogger("observer")
logger.setLevel(loglevel)
logger.info(f"loglevel set to {logger.level}")

cache = {}

async def main():
    logger.info(f"watching for changes in {setup_root}")
    async for changes in awatch(setup_root):
        for change in changes:

            if change in cache and (datetime.now() - cache[change]) < timedelta(seconds=5):
                logger.debug("change already handled, passing")
                continue
            else:
                cache[change] = datetime.now()

            change_type, file_path = change
            doc_file = Path(file_path)
            doc_case = doc_file.parent
            org = doc_case.parent
            if doc_file.is_file() and change_type in (Change.added, Change.modified):
                doc_type = magic.from_file(doc_file)
                if doc_case == setup_root or org == setup_root:
                    logger.warning(f"not processing file at invalid location {file_path}")
                    continue
                if doc_file.name in (templatefile, fieldsfile):
                    continue
                if doc_file.name != definitionsfile:
                    logger.warning(f"file name '{doc_file.name}' is not a definitions file ('{definitionsfile}'), not processing")
                    continue
                if not doc_type.startswith("PDF"):
                    logger.warning(f"invalid {doc_type} file added at {file_path}")
                    continue

                logger.info(f"processing PDF file {doc_file.name} {change_type.name}...")

                with fitz.open(doc_file) as pdf:
                    try:
                        fields = extract_fields(pdf)
                    except Exception as exc:
                        logger.error(f"field extraction from {doc_file.name} failed: ", exc)
                    else:
                        dump_path =  setup_root / org.name / doc_case.name / fieldsfile
                        dump_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(dump_path, "w", encoding="utf-8") as dumpfile:
                            dumpfile.write(yaml.dump(tuple(fields)))
                        logger.info(f"field definitions file successfully generated")


if __name__=="__main__":
   asyncio.run(main())
