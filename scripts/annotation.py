from pydantic import BaseModel

class Object(BaseModel, frozen=True):
    object_category: str
    object_id: str

class Annotation(BaseModel, frozen=True):
    obj: Object
    grasp_id: int
    description: str
    is_mesh_malformed: bool = False
    is_grasp_invalid: bool = False
    user_id: str
