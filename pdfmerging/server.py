import asyncio
import sys
import logging
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from fastapi import FastAPI, Form, Request, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import HTTPException, Depends
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from .config import merged_root, setup_root, generated_url_root
from .config import templatefile, fieldsfile, definitionsfile, host, token, loglevel, workers
from .producer import produce_merged, produce_definitions


logging.basicConfig()
logger = logging.getLogger("pdfgen")
logger.setLevel(loglevel)
logger.info(f"loglevel set to {logger.level}")


executor = ProcessPoolExecutor(max_workers=workers)

security = HTTPBearer()

tag_defs = [
    {
        "name": "merging",
        "description": "API for merging PDF templates with data",
    },
]


class MergedPDF(BaseModel):
    url: str


app = FastAPI(title='PDF Merger', version="1.0", openapi_tags=tag_defs)

@app.post("/" + generated_url_root + "/{org_id}/{doc_id}", tags=["merging"], response_model=MergedPDF)
async def generate_pdf(request:Request, org_id:str=Path(title="id of the organization"), doc_id:str=Path(title="id of the document case"), credentials=Depends(security)):
    "Merge the given document with the submitted x-www-urlencoded form data into a new PDF and return a link to it."

    if credentials.credentials != token:
        raise HTTPException(status_code=403, detail="Incorrect token")

    form = await request.form()

    org_root = setup_root / org_id
    doc_root = org_root / doc_id
    source_pdf_path = doc_root / templatefile
    fields_dump_path = doc_root / fieldsfile

    if not org_root.is_dir():
        raise HTTPException(status_code=404, detail=f"No such org '{org_id}' available")
    if not doc_root.is_dir():
        raise HTTPException(status_code=404, detail=f"No such doc '{doc_id}' available")
    if not source_pdf_path.is_file():
        raise HTTPException(status_code=404, detail="template not available")

    if not fields_dump_path.is_file():
        definitions_pdf_path = doc_root / definitionsfile
        if not definitions_pdf_path.is_file():
            raise HTTPException(status_code=404, detail="neither fields config nor field definitions source PDF found")

        loop = asyncio.get_running_loop()
        extractor = loop.run_in_executor(executor, produce_definitions, definitions_pdf_path, fields_dump_path)
        try:
            await extractor
        except Exception as exc:
            logger.error(f"no fields config found and definitions extraction from {definitions_pdf_path} failed: ", exc)
            raise HTTPException(status_code=500, detail="generation of fields config from definitions source PDF failed")

    outfilename = datetime.now().isoformat() + ".pdf"
    merged_file_path = merged_root / f"{org_id}/{doc_id}" / outfilename
    merged_file_path.parent.mkdir(parents=True, exist_ok=True)

    loop = asyncio.get_running_loop()
    merger = loop.run_in_executor(executor, produce_merged, source_pdf_path, fields_dump_path, merged_file_path, dict(form))
    try:
        await merger
    except Exception as exc:
        logger.error(f"PDF merge for {org_id}/{doc_id} failed: ", exc)
        raise HTTPException(status_code=500, detail="PDF merge failed")
    else:
        logger.debug(f"merge operation successfully performed")

    return {"url": f"https://{host}/{generated_url_root}/{org_id}/{doc_id}/{outfilename}"}


# The static route has to be after the merge endpoint, in this case
app.mount(f"/{generated_url_root}", StaticFiles(directory=merged_root), name="merged")
