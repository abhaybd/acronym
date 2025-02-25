import os
from tqdm import tqdm
import numpy as np
import trimesh
from pydantic import BaseModel

from utils import load_annotation, MeshLibrary, look_at_rot, random_delta_rot, construct_cam_K, rejection_sample, RejectionSampleError, not_none
from annotation import Annotation

from acronym_tools import create_gripper_marker

import scene_synthesizer as ss
from scene_synthesizer.utils import PositionIteratorUniform


class DatagenConfig(BaseModel):
    cam_dfov_range: tuple[float, float] = (60.0, 90.0)  # degrees
    cam_dist_range: tuple[float, float] = (0.7, 1.3)  # meters
    cam_pitch_perturb: float = 0.02  # fraction of YFOV
    cam_yaw_perturb: float = 0.05  # fraction of XFOV
    cam_roll_perturb: float = np.pi/8  # radians
    img_size: tuple[int, int] = (480, 640)  # (height, width)
    cam_elevation_range: tuple[float, float] = (np.pi/8, np.pi/3)  # radians
    n_views: int = 10

datagen_cfg = DatagenConfig()  # TODO load from disk

SUPPORT_CATEGORIES = [
    # "Bookcase",
    "Table"
]

ALL_OBJECT_CATEGORIES = open("all_categories.txt").read().splitlines()

GRASP_LOCAL_POINTS = np.array([
    [0.041, 0, 0.066],
    [0.041, 0, 0.112],
    [0, 0, 0.066],
    [-0.041, 0, 0.112],
    [-0.041, 0, 0.066]
])

def point_on_support(scene: ss.Scene):
    surfaces = scene.support_generator(sampling_fn=lambda x: x)
    weights = [s.polygon.area for s in surfaces]
    weights = np.array(weights) / np.sum(weights)
    surface = surfaces[np.random.choice(len(surfaces), p=weights)]

    it = PositionIteratorUniform()
    x, y = next(it(surface))[0]

    obj_pose = scene.get_transform(surface.node_name)
    return obj_pose[:-1] @ surface.transform @ np.array([x, y, 0, 1])

def sample_camera_pose(scene: ss.Scene, cam_dfov: float):
    img_h, img_w = datagen_cfg.img_size
    # TODO: perturb principal point
    cam_params = construct_cam_K(img_w, img_h, cam_dfov)
    cam_xfov = 2 * np.arctan(img_w / (2 * cam_params[0, 0]))
    cam_yfov = 2 * np.arctan(img_h / (2 * cam_params[1, 1]))

    lookat_pos = point_on_support(scene)
    # scene.add_object(ss.SphereAsset(0.02), translation=lookat_pos)

    cam_dist = np.random.uniform(*datagen_cfg.cam_dist_range)
    inclination = np.pi/2 - np.random.uniform(*datagen_cfg.cam_elevation_range)
    azimuth = np.random.rand() * 2 * np.pi
    cam_pose = np.eye(4)
    cam_pose[:3, 3] = np.array([
        cam_dist * np.sin(inclination) * np.cos(azimuth),
        cam_dist * np.sin(inclination) * np.sin(azimuth),
        cam_dist * np.cos(inclination)
    ]) + lookat_pos
    cam_pose[:3, :3] = \
        look_at_rot(cam_pose[:3, 3], lookat_pos) @ \
        random_delta_rot(
            datagen_cfg.cam_roll_perturb,
            datagen_cfg.cam_pitch_perturb * np.radians(cam_yfov),
            datagen_cfg.cam_yaw_perturb * np.radians(cam_xfov)
        )
    return cam_params, cam_pose


def sample_arrangement(
    object_meshes: list[trimesh.Trimesh],
    background_meshes: list[trimesh.Trimesh],
    support_mesh: trimesh.Trimesh
):
    scene = ss.Scene()
    scene.add_object(ss.TrimeshAsset(support_mesh, origin=("centroid", "centroid", "bottom")), "support")
    support_surfaces = scene.label_support("support", min_area=0.05)
    if len(support_surfaces) == 0:
        return None

    scene.add_object(ss.PlaneAsset(20, 20), "floor")
    scene.geometry["floor/geometry_0"].visual.vertex_colors = [0, 0, 0, 255]

    objs_placed = 0
    for i, obj in enumerate(object_meshes):
        asset = ss.TrimeshAsset(obj, origin=("centroid", "centroid", "bottom"))
        objs_placed += scene.place_object(f"object_{i}", asset, "support")
    if objs_placed <= 1:
        return None
    for i, obj in enumerate(background_meshes):
        asset = ss.TrimeshAsset(obj, origin=("centroid", "centroid", "bottom"))
        scene.place_object(f"background_{i}", asset, "support")

    cam_params: list[tuple[np.ndarray, np.ndarray]] = []
    try:
        for i in range(datagen_cfg.n_views):
            cam_dfov = np.random.uniform(*datagen_cfg.cam_dfov_range)
            params = rejection_sample(lambda: sample_camera_pose(scene, cam_dfov), not_none, 100)
            cam_params.append(params)
    except RejectionSampleError:
        return None

    return scene, cam_params

def sample_scene(object_library: MeshLibrary, background_library: MeshLibrary, support_library: MeshLibrary):
    n_objects = np.random.randint(2, min(6, len(object_library.categories())))
    n_background = np.random.randint(3, min(10, len(background_library.categories())))

    object_keys, object_meshes = object_library.sample(n_objects)
    background_keys, background_meshes = background_library.sample(n_background, replace=True)
    support_key, support_mesh = support_library.sample()

    try:
        return rejection_sample(
            lambda: sample_arrangement(object_meshes, background_meshes, support_mesh),
            not_none,
            10
        )
    except RejectionSampleError:
        return None


def main():
    annotations: list[Annotation] = []
    for annot_fn in tqdm(os.listdir("annotations"), desc="Loading annotations"):
        annotations.append(load_annotation(f"annotations/{annot_fn}"))

    annotated_instances: dict[str, set[str]] = {}
    for annot in annotations:
        if annot.obj.object_category not in annotated_instances:
            annotated_instances[annot.obj.object_category] = set()
        annotated_instances[annot.obj.object_category].add(annot.obj.object_id)

    object_library = MeshLibrary(annotated_instances)
    support_library = MeshLibrary.from_categories(SUPPORT_CATEGORIES, load_kwargs={"scale": 0.025})
    background_library = MeshLibrary.from_categories(ALL_OBJECT_CATEGORIES)

    scene, cam_params = rejection_sample(lambda: sample_scene(object_library, background_library, support_library), lambda x: x is not None, 100)
    scene: ss.Scene
    scene.export("scene.glb")
    # for cam_K, cam_pose in cam_params:
    #     scene.scene.camera.K = cam_K
    #     scene.scene.camera_transform = cam_pose
    scene.show()

    # TODO: for each view, find all visible annotations

if __name__ == "__main__":
    main()
