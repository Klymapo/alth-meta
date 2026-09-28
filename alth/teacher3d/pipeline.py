"""Orchestration layer for free/local Teacher3D experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence
import json
import trimesh

from .camera import CameraSpec, save_transforms_json
from .consensus import TeacherMesh, consensus_confidence
from .audit3d import chamfer_distance, signed_surface_error
from .policy import ensure_local_only


@dataclass
class TeacherArtifact:
    provider: str
    mesh_path: Path
    seed: int | None = None
    approved_2d: bool = False
    notes: dict = field(default_factory=dict)

    def load(self) -> TeacherMesh:
        scene=trimesh.load(self.mesh_path, force="scene")
        mesh=scene.to_geometry()
        return TeacherMesh.from_trimesh(
            name=f"{self.provider}:{self.mesh_path.name}",
            mesh=mesh,
            source_path=self.mesh_path,
        )


@dataclass
class Teacher3DExperiment:
    root: Path
    references: dict[str, Path]
    cameras: list[CameraSpec]
    artifacts: list[TeacherArtifact] = field(default_factory=list)

    @classmethod
    def create(cls, root: str | Path, references: dict[str, str | Path], cameras: Sequence[CameraSpec]):
        root=Path(root)
        root.mkdir(parents=True, exist_ok=True)
        refs={k:Path(v) for k,v in references.items()}
        return cls(root=root, references=refs, cameras=list(cameras))

    def prepare_pixal3d_views(self, mesh_scale: float = 1.0) -> Path:
        """Build a Pixal3D-compatible transforms.json next to staged references."""
        views_dir=self.root/"pixal3d_views"
        views_dir.mkdir(parents=True, exist_ok=True)
        staged=[]
        for view in self.cameras:
            src=self.references[view.name]
            dst=views_dir/Path(view.file_path).name
            if src.resolve()!=dst.resolve():
                dst.write_bytes(src.read_bytes())
            staged.append(CameraSpec(
                name=view.name,
                file_path=dst.name,
                azimuth_deg=view.azimuth_deg,
                elevation_deg=view.elevation_deg,
                distance=view.distance,
                fov_deg=view.fov_deg,
            ))
        return save_transforms_json(views_dir/"transforms.json", staged, mesh_scale=mesh_scale)

    def add_artifact(self, provider: str, mesh_path: str | Path, *, seed=None, approved_2d=False, notes=None):
        ensure_local_only(provider)
        artifact=TeacherArtifact(provider,Path(mesh_path),seed,approved_2d,notes or {})
        self.artifacts.append(artifact)
        return artifact

    def approved_teachers(self) -> list[TeacherMesh]:
        return [a.load() for a in self.artifacts if a.approved_2d]

    def consensus_report(self) -> dict:
        teachers=self.approved_teachers()
        if not teachers:
            return {"status":"no_approved_teachers"}
        report=consensus_confidence(teachers)
        report["status"]="ok"
        return report

    def compare_candidate(self, candidate_mesh_path: str | Path) -> dict:
        """Compare one procedural ALTH candidate to every approved teacher."""
        teachers=self.approved_teachers()
        if not teachers:
            return {"status":"no_approved_teachers"}
        candidate=trimesh.load(candidate_mesh_path,force="scene").to_geometry()
        rows=[]
        for teacher in teachers:
            rows.append({
                "teacher":teacher.name,
                "chamfer":chamfer_distance(candidate.vertices,teacher.vertices),
                "signed":signed_surface_error(candidate.vertices,teacher.vertices),
            })
        return {"status":"ok","comparisons":rows,"consensus":self.consensus_report()}

    def save_state(self, path: str | Path | None = None) -> Path:
        if path is None:
            path=self.root/"teacher3d_experiment.json"
        path=Path(path)
        data={
            "root":str(self.root),
            "references":{k:str(v) for k,v in self.references.items()},
            "cameras":[vars(c) for c in self.cameras],
            "artifacts":[{
                "provider":a.provider,
                "mesh_path":str(a.mesh_path),
                "seed":a.seed,
                "approved_2d":a.approved_2d,
                "notes":a.notes,
            } for a in self.artifacts],
        }
        path.write_text(json.dumps(data,indent=2),encoding="utf-8")
        return path
