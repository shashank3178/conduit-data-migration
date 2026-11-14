from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate


def create_project(
    db: Session,
    user: User,
    payload: ProjectCreate,
) -> Project:
    project = Project(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
    )

    db.add(project)
    db.commit()
    db.refresh(project)

    return project


def list_projects(db: Session, user: User) -> list[Project]:
    return (
        db.query(Project)
        .filter(Project.owner_id == user.id)
        .order_by(Project.created_at.desc())
        .all()
    )


def get_project(
    db: Session,
    user: User,
    project_id,
) -> Project | None:
    return (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.owner_id == user.id,
        )
        .first()
    )


def update_project(
    db: Session,
    project: Project,
    payload: ProjectUpdate,
) -> Project:
    changes = payload.model_dump(exclude_unset=True)

    for field, value in changes.items():
        setattr(project, field, value)

    db.commit()
    db.refresh(project)

    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.commit()