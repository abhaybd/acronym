import os
import json
from typing import Any, Callable

import numpy as np
from scipy.spatial.transform import Rotation as R
import trimesh

from acronym_tools import load_mesh, load_grasps

import sys; sys.path.append("./scripts")
from annotation import Annotation, GraspLabel


class RejectionSampleError(Exception):
    pass

def not_none(x: Any):
    return x is not None

def rejection_sample(sampler_fn: Callable[[], Any], condition_fn: Callable[[Any], bool], max_iters: int = 1000):
    for _ in range(max_iters):
        sample = sampler_fn()
        if condition_fn(sample):
            return sample
    raise RejectionSampleError("Failed to sample")

def kelvin_to_rgb(kelvin: float):
    # taken from: https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html
    temp = kelvin / 100
    if temp <= 66:
        r = 255
        g = np.clip(99.4708025861 * np.log(temp) - 161.1195681661, 0, 255)
        b = np.clip(138.5177312231 * np.log(temp - 10) - 305.0447927307, 0, 255) if temp > 19 else 0
    else:
        r = np.clip(329.698727446 * np.power(temp - 60, -0.1332047592), 0, 255)
        g = np.clip(288.1221695283 * np.power(temp - 60, -0.0755148492), 0, 255)
        b = 255
    return np.array([r, g, b])

def load_annotation(path: str):
    with open(path) as f:
        data = json.load(f)
    if "is_grasp_invalid" in data:
        data["grasp_label"] = GraspLabel.INFEASIBLE if data["is_grasp_invalid"] else GraspLabel.BAD
        del data["is_grasp_invalid"]
    data = Annotation(**data)
    return data

def look_at_rot(p1: np.ndarray, p2: np.ndarray):
    z = -(p2 - p1)
    z /= np.linalg.norm(z)
    x = np.cross(z, np.array([0, 0, -1]))
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    y /= np.linalg.norm(y)
    return np.column_stack((x, y, z))

def construct_cam_K(w: int, h: int, dfov: float):
    f = (np.hypot(w, h) / 2) / np.tan(np.radians(dfov/2))
    cam_info = np.array([
        [f, 0, w/2],
        [0, f, h/2],
        [0, 0, 1]
    ])
    return cam_info

def random_delta_rot(roll_range: float, pitch_range: float, yaw_range: float):
    roll = np.random.uniform(-roll_range, roll_range)
    pitch = np.random.uniform(-pitch_range, pitch_range)
    yaw = np.random.uniform(-yaw_range, yaw_range)
    return R.from_euler("xyz", [roll, pitch, yaw]).as_matrix()

class MeshLibrary(object):
    def __init__(self, library: dict[str, set[str]], load_kwargs: dict | None = None):
        self.library = library
        self.meshes: dict[tuple[str, str], dict[str, trimesh.Trimesh]] = {}
        self.load_kwargs = load_kwargs or {}

    @classmethod
    def from_categories(cls, categories: list[str], load_kwargs: dict | None = None):
        library: dict[str, set[str]] = {}
        for category in categories:
            for fn in os.listdir("data/grasps"):
                if fn.startswith(category + "_"):
                    obj_id = fn[len(category) + 1:-len(".h5")]
                    if category not in library:
                        library[category] = set()
                    library[category].add(obj_id)
        return cls(library, load_kwargs)

    def __getitem__(self, key: tuple[str, str]) -> trimesh.Trimesh:
        if key in self.meshes:
            return self.meshes[key]
        category, obj_id = key
        if category not in self.library:
            raise KeyError(f"Category {category} not found")
        if obj_id not in self.library[category]:
            raise KeyError(f"Object {obj_id} not found in category {category}")
        self.meshes[key] = self._load_mesh(category, obj_id, center=True)
        return self.meshes[key]

    def __len__(self):
        return sum(map(len, self.library.values()))

    def __iter__(self):
        for category, obj_ids in self.library.items():
            for obj_id in obj_ids:
                yield category, obj_id

    def __contains__(self, key: tuple[str, str]):
        return key[0] in self.library and key[1] in self.library[key[0]]

    def categories(self):
        return self.library.keys()

    def objects(self, category: str):
        return self.library[category]

    def sample(self, n_categories: int | None = None, replace=False):
        ret_keys: list[tuple[str, str]] = []
        ret_meshes: list[trimesh.Trimesh] = []
        categories = np.random.choice(list(self.library.keys()), size=n_categories or 1, replace=replace)
        for category in categories:
            obj_id = np.random.choice(list(self.library[category]))
            ret_keys.append((category, obj_id))
            ret_meshes.append(self[category, obj_id])
        return (ret_keys, ret_meshes) if n_categories else (ret_keys[0], ret_meshes[0])

    def _load_mesh(self, category: str, obj_id: str, center: bool = True):
        fn = f"data/grasps/{category}_{obj_id}.h5"
        mesh = load_mesh(fn, mesh_root_dir="data", **self.load_kwargs)
        if center:
            mesh.apply_translation(-mesh.centroid)
        return mesh

    def grasps(self, category: str, obj_id: str):
        T, success = load_grasps(f"data/grasps/{category}_{obj_id}.h5")
        mesh = self._load_mesh(category, obj_id, center=False)
        T[:, :3, 3] -= mesh.centroid
        return T, success
