import asyncio
import base64
import io
import json
import queue
import threading
import uuid
import webbrowser
import zipfile
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from crm_uploader import upload_coupons_to_crm
from parser import parse_pdf_coupons

BASE_DIR = Path(__file__).parent
JOBS: dict[str, queue.Queue] = {}


async def index(request: Request):
    return FileResponse(BASE_DIR / "static" / "index.html")


async def api_parse(request: Request):
    pdf_bytes = await request.body()
    if not pdf_bytes:
        return JSONResponse({"error": "Порожній файл"}, status_code=400)

    default_fuel = request.query_params.get("default_fuel", "")
    try:
        coupons = parse_pdf_coupons(pdf_bytes, default_fuel_type=default_fuel)
        return JSONResponse({"coupons": coupons})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def api_export_zip(request: Request):
    data = await request.json()
    coupons = data.get("coupons", [])

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, c in enumerate(coupons, start=1):
            b64 = c.get("image_base64", "")
            if "," in b64:
                b64 = b64.split(",", 1)[1]
            if not b64:
                continue
            serial = c.get("serial_number") or f"talon_{i}"
            zf.writestr(f"{i:02d}_{serial}.png", base64.b64decode(b64))

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="talony_screens.zip"'},
    )


async def api_upload(request: Request):
    data = await request.json()
    coupons = data.get("coupons", [])
    dry_run = bool(data.get("dry_run", False))

    job_id = uuid.uuid4().hex
    q: queue.Queue = queue.Queue()
    JOBS[job_id] = q

    def worker():
        try:
            upload_coupons_to_crm(coupons, on_progress=q.put, dry_run=dry_run)
        except Exception as exc:
            q.put({"status": "fatal_error", "message": f"Критична помилка: {exc}"})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()
    return JSONResponse({"job_id": job_id})


async def api_upload_progress(request: Request):
    job_id = request.path_params["job_id"]
    q = JOBS.get(job_id)
    if not q:
        return JSONResponse({"error": "Job not found"}, status_code=404)

    async def event_stream():
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.15)
                continue

            if item is None:
                JOBS.pop(job_id, None)
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


app = Starlette(
    routes=[
        Route("/", index),
        Route("/api/parse", api_parse, methods=["POST"]),
        Route("/api/export-zip", api_export_zip, methods=["POST"]),
        Route("/api/upload", api_upload, methods=["POST"]),
        Route("/api/upload-progress/{job_id}", api_upload_progress, methods=["GET"]),
    ]
)


if __name__ == "__main__":
    url = "http://127.0.0.1:8765"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=8765)
