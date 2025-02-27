import os
if os.environ.get("PYOPENGL_PLATFORM") is None:
    os.environ["PYOPENGL_PLATFORM"] = "egl"

import pyrender
import numpy as np
import trimesh
import json
import base64
import io
from PIL import Image
import pyrender.light


result = Image.new("RGB", (640 * 3, 480 * 3))

for i in range(9):
    with open(f"tmp/scene_{i}.json", "r") as f:
        data = json.load(f)

    glb_bytes = base64.b64decode(data["glb"].encode("utf-8"))
    glb_bytes_io = io.BytesIO(glb_bytes)
    tr_scene = trimesh.load(glb_bytes_io, file_type="glb")
    scene = pyrender.Scene.from_trimesh_scene(tr_scene)

    for light in data["lighting"]:
        light_type = getattr(pyrender.light, light["type"])
        light_args = light["args"]
        light_args["color"] = np.array(light_args["color"]) / 255.0
        light_node = pyrender.Node(light["args"]["name"], matrix=light["transform"], light=light_type(**light_args))
        scene.add_node(light_node)

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

    r = pyrender.OffscreenRenderer(640, 480)
    from pyrender import RenderFlags
    import time
    start = time.perf_counter()
    color, depth = r.render(scene, flags=RenderFlags.SHADOWS_ALL)
    end = time.perf_counter()
    print(f"Render time: {1000 * (end - start):.2f} ms")
    r, c = i // 3, i % 3
    result.paste(Image.fromarray(color), (640 * c, 480 * r))

result.save("renders.png")
