import numpy as np

from alth.teacher3d.camera import CameraSpec, build_transforms_json, orbit_camera_matrix
from alth.teacher3d.fusion import visibility_aware_fusion
from alth.teacher3d.consensus import TeacherMesh, consensus_confidence
from alth.teacher3d.audit3d import chamfer_distance
from alth.teacher3d.instantmesh_direct import instantmesh_camera_vector


def test_camera_front_is_on_negative_y():
    c=orbit_camera_matrix(0,0,8)
    assert np.allclose(c[:3,3],[0,-8,0],atol=1e-6)


def test_transforms_json_has_four_views():
    views=[
        CameraSpec("front","front.png",0,distance=8,fov_deg=10),
        CameraSpec("side","side.png",90,distance=8,fov_deg=10),
        CameraSpec("back","back.png",180,distance=8,fov_deg=10),
        CameraSpec("three_quarter","three.png",45,distance=8,fov_deg=10),
    ]
    meta=build_transforms_json(views)
    assert len(meta["frames"])==4
    assert meta["frames"][0]["name"]=="front"


def test_visibility_aware_fusion_ignores_invalid_view():
    # one point, two views, one feature channel
    features=np.array([[[2.0],[100.0]]],dtype=np.float32)  # [P,V,C]
    valid=np.array([[1.0,0.0]],dtype=np.float32)
    fused=visibility_aware_fusion(features,valid)
    assert np.allclose(fused,[[2.0]])


def test_consensus_confidence_drops_with_disagreement():
    a=TeacherMesh("a",np.array([[0,0,0],[1,0,0],[0,1,0]],float))
    b=TeacherMesh("b",np.array([[0,0,0],[1,0,0],[0,1,0.01]],float))
    c=TeacherMesh("c",np.array([[0,0,0],[10,0,0],[0,10,0]],float))
    near=consensus_confidence([a,b],sample_points=100)
    far=consensus_confidence([a,c],sample_points=100)
    assert near["global_confidence"] > far["global_confidence"]


def test_chamfer_identical_zero():
    pts=np.array([[0,0,0],[1,0,0],[0,1,0]],float)
    d=chamfer_distance(pts,pts,sample_points=100)
    assert d["symmetric_mean"]==0.0


def test_instantmesh_camera_vector_shape():
    v=CameraSpec("front","front.png",0,distance=4,fov_deg=30)
    vec=instantmesh_camera_vector(v)
    assert vec.shape==(16,)
