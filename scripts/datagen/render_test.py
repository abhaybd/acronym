from matplotlib import pyplot as plt
import pyrender
import numpy as np
import trimesh
import trimesh.exchange
import trimesh.exchange.gltf
import json
import base64
import io
from PIL import Image
import pyrender.light

fig, ax = plt.subplots(3, 3)

for i in range(9):
    with open(f"tmp/scene_{i}.json", "r") as f:
        data = json.load(f)

    glb_bytes = base64.b64decode(data["glb"])
    glb_bytes_io = io.BytesIO(glb_bytes)
    tr_scene = trimesh.load(glb_bytes_io, file_type="glb")
    scene = pyrender.Scene.from_trimesh_scene(tr_scene)

    for light in data["lighting"]:
        light_type = getattr(pyrender.light, light["type"])
        light_args = light["args"]
        light_args["intensity"] = 50
        light_args["color"] = np.array(light_args["color"]) / 255.0
        print(light_args)
        print(np.array(light["transform"])[:3, 3])
        light_node = pyrender.Node(light["args"]["name"], matrix=light["transform"], light=light_type(**light_args))
        scene.add_node(light_node)

    # pyrender.Viewer(scene, use_raymond_lighting=False, use_direct_lighting=False, shadows=True)

    cam_K = np.array(data["cam_K"])
    cam_pose = np.array(data["cam_pose"])

    cam = pyrender.camera.IntrinsicsCamera(
        fx=cam_K[0, 0],
        fy=cam_K[1, 1],
        cx=cam_K[0, 2],
        cy=cam_K[1, 2],
        name="camera",
    )
    cam_node = pyrender.Node(name="camera", camera=cam, matrix=cam_pose)
    scene.add_node(cam_node)

    # viewer = pyrender.Viewer(scene, use_raymond_lighting=False, use_direct_lighting=False, shadows=True)

    r = pyrender.OffscreenRenderer(640, 480)
    from pyrender import RenderFlags
    color, depth = r.render(scene, flags=RenderFlags.SHADOWS_POINT)
    r, c = i // 3, i % 3
    ax[r, c].set_xticks([])
    ax[r, c].set_yticks([])
    ax[r, c].imshow(color)
fig.tight_layout()
plt.show()


# tr_scene = trimesh.load("test.glb")
# scene = pyrender.Scene.from_trimesh_scene(tr_scene)

# kw = trimesh.exchange.gltf.load_glb(open("test.glb", "rb"))

# breakpoint()

# light_trf = np.eye(4)
# light_trf[:3, 3] = [1, 0, 4]
# ln = pyrender.Node("light", matrix=light_trf, light=pyrender.PointLight(color=[1.,1.,1.], intensity=100))
# scene.add_node(ln)

# viewer = pyrender.Viewer(scene, use_raymond_lighting=False, use_direct_lighting=False, shadows=True)
