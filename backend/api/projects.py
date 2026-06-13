import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.project import Project
from backend.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _validate_client_secret(path_str: str) -> None:
    """Validate that client_secret_path points to a valid Google OAuth JSON file."""
    path = Path(path_str)

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Client secret file not found: {path_str}",
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client secret file is not valid JSON.",
        )

    app_type = None
    if "installed" in data:
        app_type = "installed"
    elif "web" in data:
        app_type = "web"

    if app_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Client secret JSON must contain an 'installed' or 'web' key.",
        )

    section = data[app_type]
    if "client_id" not in section or "client_secret" not in section:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The '{app_type}' section must contain 'client_id' and 'client_secret'.",
        )


@router.post("/upload-secret")
async def upload_secret(file: UploadFile = File(...)):
    """Upload a client_secret.json file, validate it, save to data/secrets/."""
    contents = await file.read()

    try:
        data = json.loads(contents)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="File is not valid JSON.")

    app_type = None
    if "installed" in data:
        app_type = "installed"
    elif "web" in data:
        app_type = "web"

    if app_type is None:
        raise HTTPException(status_code=400, detail="JSON must contain 'installed' or 'web' key.")

    section = data[app_type]
    if "client_id" not in section or "client_secret" not in section:
        raise HTTPException(
            status_code=400,
            detail=f"Missing 'client_id' or 'client_secret' in '{app_type}' section.",
        )

    secrets_dir = settings.data_dir / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "client_secret.json"
    dest = secrets_dir / filename
    dest.write_bytes(contents)

    return {"path": str(dest.resolve())}


@router.get("", response_model=list[ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    """List all registered GCP projects."""
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    """Register a new GCP project with its client secret file."""
    existing = db.query(Project).filter(Project.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A project named '{body.name}' already exists.",
        )

    _validate_client_secret(body.client_secret_path)

    project = Project(
        name=body.name,
        client_secret_path=body.client_secret_path,
        daily_quota_limit=body.daily_quota_limit,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    """Delete a registered GCP project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    db.delete(project)
    db.commit()
