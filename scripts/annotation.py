from pydantic import BaseModel

class Object(BaseModel):
    object_category: str
    object_id: str

class Annotation(BaseModel):
    obj: Object
    grasp_id: int
    description: str
    user_id: str

class MalformedAnnotation(BaseModel):
    obj: Object
    user_id: str
