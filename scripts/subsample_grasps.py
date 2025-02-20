import os
import numpy as np
import trimesh
from tqdm import tqdm
from scipy.spatial.transform import Rotation as scipyR

from acronym_tools import load_mesh, load_grasps, create_gripper_marker


GRIPPER_POS_OFFSET = 0.075

def cvh(mesh: trimesh.Trimesh, max_iter=5):
    cvh = mesh
    for _ in range(max_iter):
        if (cvh := cvh.convex_hull).is_watertight:
            return cvh
    raise ValueError("watertight failed")

def icp_2d(src_mesh: trimesh.Trimesh, target_mesh: trimesh.Trimesh, N=1000, max_iterations=50, tolerance=1e-5):
    src_mesh = src_mesh.copy()
    target_mesh = target_mesh.copy()
    src_mesh.fix_normals()
    target_mesh.fix_normals()
    source_pts = src_mesh.projected(np.array([0, 0, 1])).sample(N)
    target_pts = target_mesh.projected(np.array([0, 0, 1])).sample(N)

    def centroid_align(A, B):
        centroid_A = np.mean(A, axis=0)
        centroid_B = np.mean(B, axis=0)
        return centroid_A, centroid_B

    def scale_normalize(A, B):
        scale_A = np.sqrt(np.mean(np.linalg.norm(A, axis=1) ** 2))
        scale_B = np.sqrt(np.mean(np.linalg.norm(B, axis=1) ** 2))
        scale = scale_B / scale_A
        return scale

    def estimate_pca_rotation(A, B):
        def principal_axis(points):
            cov_matrix = np.cov(points.T)
            eigenvalues, eigenvectors = np.linalg.eig(cov_matrix)
            return eigenvectors[:, np.argmax(eigenvalues)]  # Eigenvector with max variance

        # Compute principal axes
        axis_A = principal_axis(A)
        axis_B = principal_axis(B)

        # Try both signs for the principal axis of A and choose the one with lower cost
        rotations = []
        for sign_A in [1, -1]:
            axis_A_signed = sign_A * axis_A
            ax = np.array([0, 0, np.cross(axis_A_signed, axis_B)])
            theta = np.arctan2(np.linalg.norm(ax), np.dot(axis_A_signed, axis_B))
            rotmat = scipyR.from_rotvec(ax / np.linalg.norm(ax) * theta).as_matrix()
            rotations.append(rotmat[:2, :2])

        best_R = None
        best_cost = float('inf')
        for R in rotations:
            trf = np.eye(4)
            trf[:2, :2] = R
            src_copy = src_mesh.copy()
            src_copy.apply_transform(trf)
            if not src_copy.is_watertight:
                src_copy = cvh(src_copy)
            cost = src_copy.volume + target_mesh.volume - 2 * src_copy.intersection(target_mesh).volume
            if cost < best_cost:
                best_cost = cost
                best_R = R

        return best_R

    def estimate_transform(A, B):
        """Estimate optimal similarity transform (s, R, t) using Procrustes."""
        H = A.T @ B
        U, _, Vt = np.linalg.svd(H)
        R = Vt.T @ U.T
        if np.linalg.det(R) < 0:
            Vt[-1, :] *= -1
            R = Vt.T @ U.T
        s = np.trace(R.T @ H) / np.trace(A.T @ A)
        t = np.mean(B - s * (A @ R.T), axis=0)
        return s, R, t

    # Step 1: Initial Alignment
    centroid_s, centroid_t = centroid_align(source_pts, target_pts)
    source_pts -= centroid_s
    target_pts -= centroid_t
    src_mesh.apply_translation(-np.concatenate([centroid_s, [0]]))
    target_mesh.apply_translation(-np.concatenate([centroid_t, [0]]))

    scale = scale_normalize(source_pts, target_pts)
    source_pts *= scale
    src_mesh.apply_scale(scale)
    
    # Step 2: Coarse Rotation with PCA
    R_pca = estimate_pca_rotation(source_pts, target_pts)
    source_pts = source_pts @ R_pca.T  # Apply PCA-based rotation

    # Step 3: ICP Refinement
    prev_error = float('inf')
    for i in range(max_iterations):
        # Find closest points
        indices = np.array([np.argmin(np.linalg.norm(target_pts - sp, axis=1)) for sp in source_pts])
        matched_pts = target_pts[indices]

        # Compute optimal transform
        s, R, t = estimate_transform(source_pts, matched_pts)
        source_pts = s * (source_pts @ R.T) + t  # Apply transformation

        # Check for convergence
        mean_error = np.mean(np.linalg.norm(matched_pts - source_pts, axis=1))
        if abs(prev_error - mean_error) < tolerance:
            break
        prev_error = mean_error

    # Compute final transformation matrix
    T = np.eye(3)
    T[:2, :2] = s * R @ R_pca  # Include PCA-based rotation in final transform
    T[:2, 2] = t + centroid_t - s * (centroid_s @ R.T @ R_pca)
    return T


def rot_distance(rot_deltas: np.ndarray):
    return scipyR.from_matrix(rot_deltas).magnitude()


def grasp_dist(grasp: np.ndarray, all_grasps: np.ndarray):
    """Distance between a grasp and a set of grasps."""
    assert grasp.ndim == 2
    if all_grasps.ndim == 2:
        all_grasps = all_grasps[None]
    grasp_pos = grasp[:3, 3] + GRIPPER_POS_OFFSET * grasp[:3, 2]
    all_grasps_pos = all_grasps[:, :3, 3] + GRIPPER_POS_OFFSET * all_grasps[:, :3, 2]
    pos_dist = np.linalg.norm(grasp_pos[None] - all_grasps_pos, axis=1)

    rd1 = rot_distance(all_grasps[:, :3, :3].transpose(0,2,1) @ grasp[None, :3, :3])
    rd2 = rot_distance(all_grasps[:, :3, :3].transpose(0,2,1) @ grasp[None, :3, :3] @ scipyR.from_euler("z", [np.pi]).as_matrix())
    rot_dist = np.minimum(rd1, rd2)

    return pos_dist + 0.01 * rot_dist

def load_mesh_and_grasps(category: str, obj_ids: list[str]):
    meshes = []
    grasps = []
    grasp_succ_idxs = []
    first_cvh: trimesh.Trimesh = None
    for obj_id in tqdm(obj_ids):
        fn = f"{category}_{obj_id}.h5"
        mesh = load_mesh(f"data/grasps/{fn}", mesh_root_dir="data")
        mesh_grasps, succ = load_grasps(f"data/grasps/{fn}")
        succ_idxs = np.nonzero(succ)[0]
        mesh_grasps[..., :3, 3] -= mesh.centroid
        mesh.apply_translation(-mesh.centroid)

        if len(meshes) > 0:
            trf_2d = icp_2d(cvh(mesh), first_cvh)
            trf = np.eye(4)
            trf[:2, :2] = trf_2d[:2, :2]
            trf[:2, 3] = trf_2d[:2, 2]
            mesh.apply_transform(trf)
            mesh_grasps = trf @ mesh_grasps
        else:
            first_cvh = cvh(mesh)

        meshes.append(mesh)
        grasps.append(mesh_grasps)
        grasp_succ_idxs.append(succ_idxs)
    return meshes, grasps, grasp_succ_idxs

def sample_grasps(category: str, obj_ids: list[str], n_grasps: int) -> list[list[int]]:
    meshes, grasps, grasp_succ_idxs = load_mesh_and_grasps(category, obj_ids)
    n_instances = len(grasps)

    all_grasps = np.concatenate([g[idxs] for g, idxs in zip(grasps, grasp_succ_idxs)], axis=0)
    grasp_obj_idxs = np.concatenate([np.full(len(grasp_succ_idxs[i]), i) for i in range(len(grasp_succ_idxs))], axis=0)
    points_left = np.arange(len(all_grasps))
    sample_inds = []
    dists = np.full_like(points_left, np.inf, dtype=float)

    selected = 0
    sample_inds.append(selected)
    points_left = np.delete(points_left, selected)

    for i in range(1, n_grasps):
        instance_idx = i % n_instances
        last_added_idx = sample_inds[-1]
        dists_to_last_added = grasp_dist(all_grasps[last_added_idx], all_grasps[points_left])
        dists[points_left] = np.minimum(dists[points_left], dists_to_last_added)

        # indices in points_left that correspond to the object being considered
        eligible_points = np.argwhere(grasp_obj_idxs[points_left] == instance_idx).flatten()
        # index of points_left being added
        selected = eligible_points[np.argmax(dists[points_left[eligible_points]])]
        sample_inds.append(points_left[selected])
        points_left = np.delete(points_left, selected)


    # maps instance index to the start index of its grasps in all_grasps
    obj_idx_cumsum = np.cumsum([0] + [len(grasp_succ_idxs[i]) for i in range(len(grasp_succ_idxs))])
    ret = [[] for _ in range(n_instances)]
    for i in sample_inds:
        instance_idx = grasp_obj_idxs[i]
        ret[instance_idx].append(grasp_succ_idxs[instance_idx][i - obj_idx_cumsum[instance_idx]])

    # TODO: remove
    scene = trimesh.Scene()
    for i, (m, gids) in enumerate(zip(meshes, ret)):
        scene.add_geometry(m)
        for grasp_id in gids:
            gripper_marker = create_gripper_marker()
            gripper_marker.apply_transform(grasps[i][grasp_id])
            scene.add_geometry(gripper_marker)
    scene.show()

    return ret


def main1():
    category = "Bowl"
    obj_ids = []
    for fn in os.listdir("data/grasps"):
        if fn.startswith(category + "_"):
            obj_ids.append(fn[len(category) + 1:-len(".h5")])
    ret = sample_grasps(category, obj_ids, 100)
    print(list(map(len, ret)))

def main2():
    category = "Pan"
    obj_ids = []
    for fn in os.listdir("data/grasps"):
        if fn.startswith(category + "_"):
            obj_ids.append(fn[len(category) + 1:-len(".h5")])

    scene = trimesh.Scene()
    meshes, grasps, _ = load_mesh_and_grasps(category, obj_ids)
    print(sum(map(len, grasps)))
    scene = trimesh.Scene()
    for i, m in enumerate(meshes):
        scene.add_geometry(m)
        for grasp_id in range(len(grasps[i])):
            gripper_marker = create_gripper_marker()
            gripper_marker.apply_transform(grasps[i][grasp_id])
            scene.add_geometry(gripper_marker)
    scene.show()

if __name__ == "__main__":
    main1()
