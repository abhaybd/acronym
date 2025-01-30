import argparse
import uuid

import trimesh
import numpy as np
from scipy.spatial.transform import Rotation as R
import open3d as o3d
from PIL import Image

from acronym_tools import load_mesh, load_grasps, create_gripper_marker


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("object_files", nargs="+", help="HDF5 or JSON Grasp file(s).")
    parser.add_argument("--mesh_root", default="data")
    return parser.parse_args()

def trimesh_to_o3d(tmesh: trimesh.Trimesh):
    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(tmesh.vertices)
    mesh.triangles = o3d.utility.Vector3iVector(tmesh.faces)
    if not isinstance(tmesh.visual, trimesh.visual.color.ColorVisuals):
        color = tmesh.visual.to_color()
    else:
        color = tmesh.visual
    mesh.vertex_colors = o3d.utility.Vector3dVector(color.vertex_colors[:, :3] / 255.0)
    mesh.vertex_normals = o3d.utility.Vector3dVector(tmesh.vertex_normals)
    mesh.compute_vertex_normals()

    mat = o3d.visualization.rendering.MaterialRecord()
    mat.shader = "defaultLit"
    mat.base_color = [1, 1, 1, 1]
    return {"geometry": mesh, "material": mat}

def to_geom_dict(geom) -> dict:
    if not isinstance(geom, dict):
        assert isinstance(geom, o3d.geometry.Geometry)
        geom = {"geometry": geom}

    if "name" not in geom:
        geom["name"] = f"unnamed_{str(uuid.uuid4())}"
    if "material" not in geom:
        default_material = o3d.visualization.rendering.MaterialRecord()
        default_material.shader = "defaultUnlit"
        geom["material"] = default_material
    assert all(k in geom for k in ["name", "geometry", "material"])
    return geom

class GeomRenderer(object):
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.renderer = o3d.visualization.rendering.OffscreenRenderer(width, height)
        self.renderer.scene.set_background(np.array([1, 1, 1, 1]))
        self.renderer.scene.view.set_post_processing(True)
        self.renderer.scene.scene.enable_indirect_light(True)

    def render(self, geometries: list, cam_info: np.ndarray, extrinsics: np.ndarray, depth=False):
        self.renderer.scene.clear_geometry()
        for geom in geometries:
            self.renderer.scene.add_geometry(**to_geom_dict(geom))
        intrinsics = o3d.camera.PinholeCameraIntrinsic(self.width, self.height, cam_info)
        self.renderer.setup_camera(intrinsics, extrinsics)
        if depth:
            img = np.asarray(self.renderer.render_to_depth_image(z_in_view_space=True))
        else:
            img = np.asarray(self.renderer.render_to_image()).astype(np.uint8)
        return img

def main():
    args = get_args()
    w, h = 960, 720
    fov_x, fov_y = 60, 45
    cam_info = np.array([
        [(w/2) / np.tan(np.radians(fov_x/2)), 0, w/2],
        [0, (h/2) / np.tan(np.radians(fov_y/2)), h/2],
        [0, 0, 1]
    ])
    print(cam_info)

    renderer = GeomRenderer(w, h)

    for f in args.object_files:
        obj_mesh = load_mesh(f, args.mesh_root)
        T, _ = load_grasps(f)

        idx = np.random.choice(len(T))
        print(f"Showing grasp {idx} from {f}")
        gripper_marker: trimesh.Trimesh = create_gripper_marker(color=[0, 255, 0]).apply_transform(T[idx])

        gripper_marker.vertices -= obj_mesh.centroid
        obj_mesh.vertices -= obj_mesh.centroid

        scene = trimesh.Scene([obj_mesh, gripper_marker])
        geom = trimesh_to_o3d(scene.to_mesh())

        N = 5
        for i, theta in enumerate(np.linspace(0, 2*np.pi, N, endpoint=False)):
            elevation = np.random.uniform(-np.pi/3, np.pi/3)
            cam_pos = R.from_euler("xz", [elevation, theta]).apply(np.array([0, scene.bounding_sphere.primitive.radius * 5, 0]))
            z_ax = -cam_pos / np.linalg.norm(cam_pos)
            x_ax = np.cross(z_ax, np.array([0, 0, 1]))
            x_ax /= np.linalg.norm(x_ax)
            y_ax = np.cross(z_ax, x_ax)
            cam_pose = np.eye(4)
            cam_pose[:3,:3] = np.column_stack((x_ax, y_ax, z_ax))
            cam_pose[:3,3] = cam_pos

            img = renderer.render([geom], cam_info, np.linalg.inv(cam_pose))
            Image.fromarray(img).save(f"render_{i}.png")

if __name__ == "__main__":
    main()
