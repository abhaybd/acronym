import json
import os
import pickle
from tqdm import tqdm
import numpy as np
import trimesh
from trimesh import transformations as tra
from pydantic import BaseModel
from itertools import compress
import base64

from PIL import Image, ImageColor

from utils import kelvin_to_rgb, load_annotation, MeshLibrary, look_at_rot, random_delta_rot, construct_cam_K, rejection_sample, RejectionSampleError, not_none
from annotation import Annotation

from acronym_tools import create_gripper_marker

import scene_synthesizer as ss
from scene_synthesizer.utils import PositionIteratorUniform


class DatagenConfig(BaseModel):
    min_wall_dist: float = 2.0
    room_width_range: tuple[float, float] = (4.0, 10.0)  # meters
    room_depth_range: tuple[float, float] = (4.0, 10.0)  # meters
    cam_dfov_range: tuple[float, float] = (60.0, 90.0)  # degrees
    cam_dist_range: tuple[float, float] = (0.7, 1.3)  # meters
    cam_pitch_perturb: float = 0.02  # fraction of YFOV
    cam_yaw_perturb: float = 0.05  # fraction of XFOV
    cam_roll_perturb: float = np.pi/8  # radians
    img_size: tuple[int, int] = (480, 640)  # (height, width)
    cam_elevation_range: tuple[float, float] = (np.pi/8, np.pi/3)  # radians
    n_views: int = 10
    n_objects_range: tuple[int, int] = (4, 6)
    n_background_range: tuple[int, int] = (4, 6)
    color_temp_range: tuple[float, float] = (2000, 10000)  # K
    light_intensity_range: tuple[float, float] = (10, 40)  # lux
    light_azimuth_range: tuple[float, float] = (0, 2 * np.pi)  # radians
    light_inclination_range: tuple[float, float] = (0, np.pi/3)  # radians

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

def homogenize(arr: np.ndarray):
    if arr.ndim == 1:
        return np.concatenate([arr, np.ones(1)])
    else:
        return np.concatenate([arr, np.ones((len(arr), 1))], axis=-1)

def create_plane(width: float, depth: float, center: np.ndarray, normal: np.ndarray):
    corners = [
        (-width / 2.0, -depth / 2.0, 0),
        (width / 2.0, -depth / 2.0, 0),
        (-width / 2.0, depth / 2.0, 0),
        (width / 2.0, depth / 2.0, 0),
    ]
    transform = trimesh.geometry.align_vectors((0, 0, 1), normal)
    transform[:3, 3] = center
    vertices = tra.transform_points(corners, transform)
    faces = [[0, 1, 3, 2]]
    plane = trimesh.Trimesh(vertices=vertices, faces=faces)
    return plane

def generate_floor_and_walls(scene: ss.Scene):
    scene_bounds = scene.get_bounds()
    min_width, min_depth = scene_bounds[1, :2] - scene_bounds[0, :2] + datagen_cfg.min_wall_dist
    width = max(min_width, np.random.uniform(*datagen_cfg.room_width_range))
    depth = max(min_depth, np.random.uniform(*datagen_cfg.room_depth_range))

    center_lo = scene_bounds[1,:2] - np.array([width, depth])/2
    center_hi = scene_bounds[0,:2] + np.array([width, depth])/2
    center = np.append(np.random.uniform(center_lo, center_hi), 0)
    print(center)

    floor_plane = create_plane(width+0.2, depth+0.2, center, (0, 0, 1))
    uv = np.array([[0,0], [1,0], [0,1], [1,1]]) * np.array([width, depth])
    texture = Image.open(f"data/floor_textures_large/{np.random.choice(os.listdir('data/floor_textures_large'))}")
    floor_plane.visual = trimesh.visual.TextureVisuals(
        uv=uv,
        image=texture
    )
    scene.add_object(ss.TrimeshAsset(floor_plane), "floor")

    wall_height = scene_bounds[1, 2] + 2.0
    with open("data/wall_colors.json", "r") as f:
        wall_color = ImageColor.getrgb(np.random.choice(json.load(f)))
    if len(wall_color) == 3:
        wall_color = (*wall_color, 255)

    def make_wall(sidelength, center, normal, name):
        plane = create_plane(wall_height, sidelength, center, normal)
        plane.visual.vertex_colors = wall_color
        scene.add_object(ss.TrimeshAsset(plane), name)
    make_wall(depth, center + np.array([-width/2, 0, wall_height/2]), (1, 0, 0), "x_pos_wall")
    make_wall(depth, center + np.array([width/2, 0, wall_height/2]), (-1, 0, 0), "x_neg_wall")
    make_wall(width, center + np.array([0, -depth/2, wall_height/2]), (0, 1, 0), "y_pos_wall")
    make_wall(width, center + np.array([0, depth/2, wall_height/2]), (0, -1, 0), "y_neg_wall")

def generate_lighting(scene: ss.Scene) -> list[dict]:
    light_temp = np.random.uniform(*datagen_cfg.color_temp_range)
    light_intensity = np.random.uniform(*datagen_cfg.light_intensity_range)
    light_azimuth = np.random.uniform(*datagen_cfg.light_azimuth_range)
    light_inclination = np.random.uniform(*datagen_cfg.light_inclination_range)
    light_trf = np.eye(4)
    light_direction = np.array([
        np.sin(light_inclination) * np.cos(light_azimuth),
        np.sin(light_inclination) * np.sin(light_azimuth),
        np.cos(light_inclination)
    ])  # opposite of direction light is pointing
    light_trf[:3, :3] = look_at_rot(light_direction, np.zeros(3))
    lights = [
        {
            "type": "DirectionalLight",
            "args": {
                "name": "light",
                "color": kelvin_to_rgb(light_temp),
                "intensity": light_intensity,
            },
            "transform": light_trf
        }
    ]
    return lights

def on_screen_annotations(cam_K: np.ndarray, cam_pose: np.ndarray, grasps: np.ndarray):
    # grasps is (N, 4, 4) poses in scene frame
    trf = np.eye(4)
    trf[[1,2], [1,2]] = -1  # flip y and z axes, since for trimesh camera -z is forward
    grasps_cam_frame = trf @ np.linalg.inv(cam_pose)[None] @ grasps
    grasp_points_cam_frame = homogenize(GRASP_LOCAL_POINTS)[None] @ grasps_cam_frame[:, :-1].transpose(0, 2, 1)
    grasp_points_img = grasp_points_cam_frame @ cam_K.T
    grasp_points_img = grasp_points_img[..., :2] / grasp_points_img[..., 2:]

    in_front_mask = np.all(grasp_points_cam_frame[..., 2] > 0, axis=-1)

    img_h, img_w = datagen_cfg.img_size
    in_bounds_mask = np.all((grasp_points_img[..., 0] >= 0) & \
        (grasp_points_img[..., 0] < img_w) & \
        (grasp_points_img[..., 1] >= 0) & \
        (grasp_points_img[..., 1] < img_h), axis=-1)

    return in_front_mask & in_bounds_mask

def visible_annotations(scene: ss.Scene, cam_pose: np.ndarray, grasps: np.ndarray):
    # grasps is (N, 4, 4) poses in scene frame
    grasp_points = homogenize(GRASP_LOCAL_POINTS)[None] @ grasps[:, :-1].transpose(0, 2, 1)
    grasp_points = grasp_points.reshape(-1, 3)  # (N*5, 3)
    
    ray_origins = np.tile(cam_pose[:3, 3], (len(grasp_points), 1))
    ray_directions = grasp_points - ray_origins
    ray_directions /= np.linalg.norm(ray_directions, axis=1, keepdims=True)

    scene_mesh: trimesh.Trimesh = scene.scene.to_mesh()
    intersect_points, ray_idxs, _ = scene_mesh.ray.intersects_location(ray_origins, ray_directions)
    ray_hit_grasp = np.ones(len(grasp_points), dtype=bool)
    for i in range(len(ray_hit_grasp)):
        mask = ray_idxs == i
        if np.any(mask):
            points = intersect_points[mask]
            closest_hit_dist = np.min(np.linalg.norm(points - ray_origins[i], axis=1))
            grasp_point_dist = np.linalg.norm(grasp_points[i] - ray_origins[i])
            if closest_hit_dist < grasp_point_dist:
                ray_hit_grasp[i] = False
    visible = np.sum(ray_hit_grasp.reshape(len(grasps), len(GRASP_LOCAL_POINTS)), axis=1) >= 3
    return visible

def noncolliding_annotations(scene: ss.Scene, annots: list[Annotation], grasps: np.ndarray, collision_cache: dict[tuple[str, str], bool]):
    # grasps is (N, 4, 4) poses in scene frame
    gripper_manager = trimesh.collision.CollisionManager()
    noncolliding = np.ones(len(grasps), dtype=bool)
    cache_miss_idxs = []
    for i, (annot, grasp) in enumerate(zip(annots, grasps)):
        if (annot.obj.object_category, annot.obj.object_id) in collision_cache:
            noncolliding[i] = collision_cache[(annot.obj.object_category, annot.obj.object_id)]
            continue
        gripper_manager.add_object(f"gripper_{i}", create_gripper_marker(), transform=grasp)
        cache_miss_idxs.append(i)

    if len(cache_miss_idxs) > 0:
        _, pairs = scene.in_collision_other(gripper_manager, return_names=True)
        for pair in pairs:
            if (name := next(filter(lambda x: x.startswith("gripper_"), pair), None)) is not None:
                idx = int(name.split("_")[-1])
                noncolliding[idx] = False

        for i in cache_miss_idxs:
            collision_cache[(annots[i].obj.object_category, annots[i].obj.object_id)] = noncolliding[i]
    return noncolliding

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
    object_keys: list[tuple[str, str]],
    object_meshes: list[trimesh.Trimesh],
    background_meshes: list[trimesh.Trimesh],
    support_mesh: trimesh.Trimesh
):
    scene = ss.Scene()
    scene.add_object(ss.TrimeshAsset(support_mesh, origin=("centroid", "centroid", "bottom")), "support")
    support_surfaces = scene.label_support("support", min_area=0.05)
    if len(support_surfaces) == 0:
        return None

    objs_placed = 0
    for (category, obj_id), obj in zip(object_keys, object_meshes):
        asset = ss.TrimeshAsset(obj, origin=("centroid", "centroid", "bottom"))
        objs_placed += scene.place_object(f"object_{category}_{obj_id}", asset, "support")
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
    n_objects = min(np.random.randint(*datagen_cfg.n_objects_range), len(object_library.categories()))
    n_background = min(np.random.randint(*datagen_cfg.n_background_range), len(background_library.categories()))

    object_keys, object_meshes = object_library.sample(n_objects)
    background_keys, background_meshes = background_library.sample(n_background, replace=True)
    support_key, support_mesh = support_library.sample()

    try:
        return rejection_sample(
            lambda: sample_arrangement(object_keys, object_meshes, background_meshes, support_mesh),
            not_none,
            10
        )
    except RejectionSampleError:
        return None

def generate_obs(scene: ss.Scene, views: list[tuple[np.ndarray, np.ndarray]], object_library: MeshLibrary, annotations: list[Annotation]):
    """
    Returns:
        all_annotations: dict[str, tuple[Annotation, np.ndarray]]  # annotation_id -> (annotation, grasp)
        annots_per_view: list[list[str]]  # annotation_id list for each view
    """
    grasps_dict: dict[tuple[str, str], np.ndarray] = {}  # maps object in scene to its grasps
    for name in scene.get_object_names():
        assert isinstance(name, str)
        if not name.startswith("object_"):
            continue
        _, cat, obj_id = name.split("_", 2)
        grasps_dict[(cat, obj_id)] = object_library.grasps(cat, obj_id)[0]

    in_scene_annotations: list[Annotation] = []
    annotation_grasps = []  # grasps in scene frame
    for annot in annotations:
        if (annot.obj.object_category, annot.obj.object_id) in grasps_dict:
            obj_name = f"object_{annot.obj.object_category}_{annot.obj.object_id}"
            in_scene_annotations.append(annot)
            grasp_local = grasps_dict[(annot.obj.object_category, annot.obj.object_id)][annot.grasp_id].copy()
            geom_names = scene.get_geometry_names(obj_name)
            assert len(geom_names) == 1
            grasp_local[:3, 3] += scene.get_centroid(geom_names[0], obj_name)
            obj_trf = scene.get_transform(obj_name)
            grasp = obj_trf @ grasp_local
            annotation_grasps.append(grasp)

    annotation_grasps = np.array(annotation_grasps)
    collision_cache: dict[tuple[str, str], bool] = {}  # (category, id) -> is colliding
    print(f"Before filtering: {len(annotation_grasps)}")

    all_annotations: dict[str, tuple[Annotation, np.ndarray]] = {}  # annotation_id -> (annotation, grasp)
    annots_per_view: list[list[str]] = []
    for cam_K, cam_pose in views:
        in_view_annots = in_scene_annotations
        in_view_grasps = annotation_grasps
        for mask_fn in [
            lambda grasps: on_screen_annotations(cam_K, cam_pose, grasps),
            lambda grasps: noncolliding_annotations(scene, in_scene_annotations, grasps, collision_cache),
            lambda grasps: visible_annotations(scene, cam_pose, grasps)
        ]:
            # TODO: also filter out grasps that are too far from the camera
            mask = mask_fn(in_view_grasps)
            in_view_annots = list(compress(in_view_annots, mask))
            in_view_grasps = in_view_grasps[mask]
            if not np.any(mask):
                break
        annots_in_view = []
        for annot, grasp in zip(in_view_annots, in_view_grasps):
            annot_id = f"{annot.obj.object_category}_{annot.obj.object_id}_{annot.grasp_id}"
            all_annotations[annot_id] = (annot, grasp)
            annots_in_view.append(annot_id)
        print(f"Number of annotations in view: {len(annots_in_view)}")
        annots_per_view.append(annots_in_view)

    return all_annotations, annots_per_view

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

    scene, cam_params = rejection_sample(lambda: sample_scene(object_library, background_library, support_library), not_none, 100)
    scene: ss.Scene
    generate_floor_and_walls(scene)
    lighting = generate_lighting(scene)

    all_annotations, annots_per_view = generate_obs(scene, cam_params, object_library, annotations)


    glb_bytes: bytes = scene.export(file_type="glb")

    try:
        scene.show()
    except:
        pass

    data = {
        "annotations": all_annotations,
        "views": [],
        "lighting": lighting,
        "glb": base64.b64encode(glb_bytes).decode("utf-8")
    }
    for (cam_K, cam_pose), annots in zip(cam_params, annots_per_view):
        data["views"].append({
            "cam_K": cam_K,
            "cam_pose": cam_pose,
            "annotations_in_view": annots
        })

    with open("tmp/scene.pkl", "wb") as f:
        pickle.dump(data, f)

    # for i, (cam_K, cam_pose) in enumerate(cam_params):
    #     data = {
    #         "cam_K": cam_K.tolist(),
    #         "cam_pose": cam_pose.tolist(),
    #         "lighting": lighting,
    #         "glb": base64.b64encode(glb_bytes).decode("utf-8")
    #     }
    #     with open(f"tmp/scene_{i}.json", "w") as f:
    #         json.dump(data, f)

if __name__ == "__main__":
    main()
