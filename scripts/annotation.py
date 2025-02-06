from pydantic import BaseModel

class Object(BaseModel, frozen=True):
    object_category: str
    object_id: str

class Annotation(BaseModel, frozen=True):
    obj: Object
    grasp_id: int
    description: str
    user_id: str

class MalformedAnnotation(BaseModel, frozen=True):
    obj: Object
    user_id: str

class InvalidGraspAnnotation(BaseModel, frozen=True):
    obj: Object
    grasp_id: int
    user_id: str
