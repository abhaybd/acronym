import argparse

import trimesh
import numpy as np
from scipy.spatial.transform import Rotation as R

from acronym_tools import load_mesh, load_grasps, create_gripper_marker

from pyglet.app.base import EventLoop
import pyglet.app
pyglet.app.event_loop = EventLoop()

def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("object_files", nargs="+", help="HDF5 or JSON Grasp file(s).")
    parser.add_argument("--mesh_root", default="data")
    return parser.parse_args()

def main():
    args = get_args()

    for f in args.object_files:
        obj_mesh = load_mesh(f, args.mesh_root)
        T, _ = load_grasps(f)

        idx = np.random.choice(len(T))
        print(f"Showing grasp {idx} from {f}")
        gripper_marker: trimesh.Trimesh = create_gripper_marker(color=[0, 255, 0]).apply_transform(T[idx])

        gripper_marker.vertices -= obj_mesh.centroid
        obj_mesh.vertices -= obj_mesh.centroid

        scene = trimesh.Scene([obj_mesh, gripper_marker])
        scene.set_camera(fov=(60, 45))

        N = 5
        for i, theta in enumerate(np.linspace(0, 2*np.pi, N, endpoint=False)):
            elevation = np.random.uniform(-np.pi/3, np.pi/3)
            cam_pos = R.from_euler("xz", [elevation, theta]).apply(np.array([0, scene.bounding_sphere.primitive.radius * 5, 0]))
            z_ax = cam_pos / np.linalg.norm(cam_pos)
            x_ax = np.cross(z_ax, np.array([0, 0, -1]))
            x_ax /= np.linalg.norm(x_ax)
            y_ax = np.cross(z_ax, x_ax)
            cam_pose = np.eye(4)
            cam_pose[:3,:3] = np.column_stack((x_ax, y_ax, z_ax))
            cam_pose[:3, 3] = cam_pos
            scene.camera_transform = cam_pose

            try:
                file_name = f"render_{i}.png"
                png = scene.save_image(resolution=[960, 720], visible=True)
                with open(file_name, "wb") as f:
                    f.write(png)
                    f.close()
            except BaseException as E:
                print("unable to save image", i, str(E))

if __name__ == "__main__":
    main()
