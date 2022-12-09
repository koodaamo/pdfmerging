import asyncio
import sys
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from fastapi import FastAPI, Form, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import HTTPException, Depends

from fastapi.staticfiles import StaticFiles
from .producer import produce_pdf
from .config import merged_root, setup_root, generated_url_root
from .config import templatefile, fieldsfile, host, token


num_jobs = 10
executor = ProcessPoolExecutor(max_workers=num_jobs)

security = HTTPBearer()

app = FastAPI(title='PDF Merger')
app.mount(f"/{generated_url_root}", StaticFiles(directory=merged_root), name="merged")

@app.post("/{org_id}/{doc_id}")
async def merge(org_id, doc_id, request:Request, credentials=Depends(security)):
    "POST a merge request for particular document case of an organization"

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
        raise HTTPException(status_code=404, detail="field definitions not available")

    outfilename = datetime.now().isoformat() + ".pdf"
    merged_file_path = merged_root / f"{org_id}/{doc_id}" / outfilename

    loop = asyncio.get_running_loop()
    merger = loop.run_in_executor(executor, produce_pdf, source_pdf_path, fields_dump_path, merged_file_path, dict(form))
    try:
        await merger
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Merge failed: {exc}")

    return {"url": f"https://{host}/{generated_url_root}/{org_id}/{doc_id}/{outfilename}"}

