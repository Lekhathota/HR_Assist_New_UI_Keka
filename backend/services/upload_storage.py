"""Writable processing files and durable uploads for serverless deployments."""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
import tempfile

import gridfs
from flask import abort, g, has_request_context, send_file, send_from_directory
from io import BytesIO
from werkzeug.utils import secure_filename

import database as db


def upload_directory() -> str:
    if os.environ.get("VERCEL"):
        return str(Path(tempfile.gettempdir()) / "hr-assist-uploads")
    return os.environ.get("UPLOAD_FOLDER") or str(Path(__file__).resolve().parents[1] / "static" / "uploads")


def save_upload(file, folder: str, filename: str) -> str:
    """Save a processing copy; persist the original outside the function filesystem."""
    filename = secure_filename(filename)
    if not filename:
        raise ValueError("A valid upload filename is required.")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, filename)
    file.save(path)
    if os.environ.get("VERCEL"):
        if has_request_context():
            g.upload_processing_paths = [*getattr(g, "upload_processing_paths", []), path]
        try:
            with open(path, "rb") as contents:
                gridfs.GridFS(db.get_database(), collection="uploaded_documents").put(
                    contents, filename=filename,
                    content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream",
                )
        except Exception:
            Path(path).unlink(missing_ok=True)
            raise
    return path


def cleanup_processing_uploads() -> None:
    for path in getattr(g, "upload_processing_paths", []):
        Path(path).unlink(missing_ok=True)


def uploaded_file_response(name: str, folder: str):
    if name != secure_filename(name):
        abort(404)
    if not os.environ.get("VERCEL"):
        return send_from_directory(folder, name, as_attachment=False)
    stored = gridfs.GridFS(db.get_database(), collection="uploaded_documents").find_one({"filename": name})
    if stored is None:
        abort(404)
    response = send_file(BytesIO(stored.read()), download_name=name,
                         mimetype=mimetypes.guess_type(name)[0] or "application/octet-stream")
    response.headers["Cache-Control"] = "private, no-store"
    return response
