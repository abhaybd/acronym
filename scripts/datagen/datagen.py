import os
from tqdm import tqdm
import numpy as np
import trimesh
from pydantic import BaseModel

from utils import load_annotation, MeshLibrary, look_at_rot, random_delta_rot, random_cam_params, rejection_sample, RejectionSampleError
from annotation import Annotation

from acronym_tools import create_gripper_marker

import scene_synthesizer as ss


class DatagenConfig(BaseModel):
    cam_dfov_range: tuple[float, float] = (60.0, 120.0)  # degrees
    cam_dist_range: tuple[float, float] = (1.0, 1.5)  # meters
    cam_pitch_perturb: float = 0.3  # fraction of YFOV
    cam_yaw_perturb: float = 0.3  # fraction of XFOV
    cam_roll_perturb: float = np.pi/8  # radians
    img_size: tuple[int, int] = (480, 640)  # (height, width)
    cam_elevation_range: tuple[float, float] = (0, np.pi/3)  # radians

datagen_cfg = DatagenConfig()  # TODO load from disk

def random_range(range):
    return np.random.rand() * np.diff(range).item() + range[0]

SUPPORT_CATEGORIES = [
    # "1Shelves",
    # "2Shelves",
    # "3Shelves",
    # "4Shelves",
    # "5Shelves",
    # "6Shelves",
    # "7Shelves",
    "Bookcase",
    "Table"
]

def sample_camera_pose(
    scene: ss.Scene,
    grasp_pose: np.ndarray,
):
    cam_dfov = random_range(datagen_cfg.cam_dfov_range)
    img_h, img_w = datagen_cfg.img_size
    cam_params = random_cam_params(img_w, img_h, cam_dfov)
    cam_xfov = 2 * np.arctan(img_w / (2 * cam_params[0, 0]))
    cam_yfov = 2 * np.arctan(img_h / (2 * cam_params[1, 1]))

    cam_dist = random_range(datagen_cfg.cam_dist_range)
    inclination = np.pi/2 - random_range(datagen_cfg.cam_elevation_range)
    azimuth = np.random.rand() * 2 * np.pi
    cam_pose = np.eye(4)
    cam_pose[:3, 3] = np.array([
        cam_dist * np.sin(inclination) * np.cos(azimuth),
        cam_dist * np.sin(inclination) * np.sin(azimuth),
        cam_dist * np.cos(inclination)
    ]) + grasp_pose[:3, 3]
    cam_pose[:3, :3] = \
        look_at_rot(cam_pose[:3, 3], grasp_pose[:3, 3]) @ \
        random_delta_rot(
            datagen_cfg.cam_roll_perturb,
            datagen_cfg.cam_pitch_perturb * np.radians(cam_yfov),
            datagen_cfg.cam_yaw_perturb * np.radians(cam_xfov)
        )
    scene.scene.camera_transform = cam_pose
    scene.scene.camera.K = cam_params

    camera_collider = trimesh.primitives.Sphere(radius=0.05)
    if scene.in_collision_single(camera_collider, cam_pose):
        return False

    grasp_local_points = np.array([
        [0.041, 0, 0.066],
        [0.041, 0, 0.112],
        [0, 0, 0.066],
        [-0.041, 0, 0.112],
        [-0.041, 0, 0.066]
    ])
    grasp_points = np.concatenate([grasp_local_points, np.ones((len(grasp_local_points), 1))], axis=1) @ grasp_pose[:-1].T
    ray_origins = np.tile(cam_pose[:3, 3], (len(grasp_points), 1))
    ray_directions = grasp_points - ray_origins
    ray_directions /= np.linalg.norm(ray_directions, axis=1, keepdims=True)

    scene_mesh: trimesh.Trimesh = scene.scene.to_mesh()
    intersect_points, ray_idxs, _ = scene_mesh.ray.intersects_location(ray_origins, ray_directions)
    n_visible = 0
    visible_idxs = []
    for i in range(len(grasp_local_points)):
        mask = ray_idxs == i
        if np.any(mask):
            points = intersect_points[mask]
            closest_idx = np.argmin(np.linalg.norm(points - ray_origins[i], axis=1))
            if np.linalg.norm(points[closest_idx] - grasp_points[i]) < 0.005:
                n_visible += 1
                visible_idxs.append(i)

    print("Visible", n_visible, visible_idxs)

    return n_visible >= 3

def sample_arrangement(
    object_mesh: trimesh.Trimesh,
    background_meshes: list[trimesh.Trimesh],
    support_mesh: trimesh.Trimesh,
    grasp_local: np.ndarray
):
    scene = ss.Scene()
    scene.add_object(ss.TrimeshAsset(support_mesh), "support")
    scene.label_support("support")
    if not scene.place_object("annot_object", ss.TrimeshAsset(object_mesh, origin=("centroid", "centroid", "bottom")), "support"):
        return None
    for i, obj in enumerate(background_meshes):
        asset = ss.TrimeshAsset(obj, origin=("centroid", "centroid", "bottom"))
        scene.place_object(f"background_{i}", asset, "support")

    # grasp is in the mesh centroid frame, so we need to go mesh centroid frame -> mesh frame -> world frame
    annot_obj_geom_names = scene.get_geometry_names("annot_object")
    assert len(annot_obj_geom_names) == 1
    obj_centroid_local = scene.get_centroid(annot_obj_geom_names[0], "annot_object")
    grasp_local = grasp_local.copy()
    grasp_local[:3, 3] += obj_centroid_local
    obj_transform = scene.get_transform("annot_object")
    grasp = obj_transform @ grasp_local

    gripper_collision_mesh = trimesh.load("data/franka_gripper_collision_mesh.stl")
    if scene.in_collision_single(gripper_collision_mesh, grasp):
        return None

    gripper_mesh: trimesh.Trimesh = create_gripper_marker()
    gripper_mesh.apply_transform(grasp)
    scene.add_object(ss.TrimeshAsset(gripper_mesh), "gripper")

    try:
        rejection_sample(lambda: sample_camera_pose(scene, grasp), lambda x: x, 100)
    except RejectionSampleError:
        return None

    return scene
    

def sample_scene(annotations: list[Annotation], object_library: MeshLibrary, support_library: MeshLibrary):
    object_categories = list(object_library.categories())
    (category, obj_id), object_mesh = object_library.sample()

    print("Annot object", category, obj_id)
    annot = next(a for a in annotations if a.obj.object_category == category and a.obj.object_id == obj_id)
    N = np.random.randint(0, 10)

    object_categories.remove(category)
    background_categories = np.random.choice(object_categories, size=N, replace=True)
    background_meshes = []
    for cat in background_categories:
        background_obj_id = np.random.choice(list(object_library.objects(cat)))
        background_meshes.append(object_library[cat, background_obj_id])

    _, support_mesh = support_library.sample()
    print("Support", *_)

    grasps_local, _ = object_library.grasps(category, obj_id)
    grasp_local = grasps_local[annot.grasp_id]

    try:
        return rejection_sample(
            lambda: sample_arrangement(object_mesh, background_meshes, support_mesh, grasp_local),
            lambda x: x is not None,
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

    scene: ss.Scene = rejection_sample(lambda: sample_scene(annotations, object_library, support_library), lambda x: x is not None, 100)
    scene.show()
    # TODO: generate image and depth map, then save to disk

if __name__ == "__main__":
    main()
