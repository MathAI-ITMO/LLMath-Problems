from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from bson import ObjectId
import motor.motor_asyncio
import os
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "https://math-llm.dev.mgsds.com/",  # Адрес вашего фронтенда (Vite HMR работает по HTTPS)
    "http З://math-llm.dev.mgsds.com/",   # Также можно добавить HTTP версию, если используется
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # Список разрешенных источников
    allow_credentials=True,    # Разрешить cookies
    allow_methods=["*"],       # Разрешить все HTTP-методы (GET, POST, PUT и т.д.)
    allow_headers=["*"],       # Разрешить все заголовки
)
# --- Конец блока CORS ---

app = FastAPI()

load_dotenv()
MONGO_DETAILS = os.environ['CONNECTION_STRING']

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DETAILS)
database = client.my_database
problems_collection = database.problems_collection
types_collection = database.types_collection
type_bindings_collection = database.type_bindings_collection


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v: any, info: any) -> ObjectId:
        if not ObjectId.is_valid(v):
            raise ValueError("Неверный ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        return {"type": "string"}


class Step(BaseModel):
    order: int
    prerequisites: Optional[Dict[str, Any]] = Field(default_factory=dict)
    transition: Optional[Dict[str, Any]] = Field(default_factory=dict)
    outcomes: Optional[Dict[str, Any]] = Field(default_factory=dict)

class Solution(BaseModel):
    steps: List[Step] = Field(default_factory=list)

class GeoilonAnsKey(BaseModel):
    hash: str
    seed: int

class Problem(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    title: Optional[str] = None
    statement: str
    geolin_ans_key: GeoilonAnsKey
    result: Optional[str] = ""
    solution: Solution
    llm_solution: Optional[Any] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class ProblemWithType(BaseModel):
    type_name: str
    problem_id: PyObjectId
    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# --- Эндпоинты API ---

# Создание новой задачи (POST /problems)
@app.post("/api/problems", response_model=Problem)
async def create_problem(problem: Problem):
    problem_dict = problem.model_dump(by_alias=True)
    result = await problems_collection.insert_one(problem_dict)
    created_problem = await problems_collection.find_one({"_id": result.inserted_id})
    if created_problem:
        return created_problem
    raise HTTPException(status_code=500, detail="Ошибка при создании задачи")

# Получение задачи по идентификатору (GET /problems/{id})
@app.get("/api/problems/{id}", response_model=Problem)
async def get_problem(id: str):
    try:
        obj_id = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    problem = await problems_collection.find_one({"_id": obj_id})
    if problem is not None:
        return problem
    raise HTTPException(status_code=404, detail="Задача не найдена")


# Обновление задачи по идентификатору (PUT /problems/{id})
@app.put("/api/problems/{id}", response_model=Problem)
async def update_problem(id: str, problem_update_data: Problem):
    try:
        obj_id = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    
    update_data = problem_update_data.model_dump(by_alias=True, exclude={"id"})

    update_result = await problems_collection.update_one({"_id": obj_id}, {"$set": update_data})
    
    if update_result.modified_count == 1:
        updated_problem = await problems_collection.find_one({"_id": obj_id})
        if updated_problem is not None:
            return updated_problem
    
    existing_problem = await problems_collection.find_one({"_id": obj_id})
    if existing_problem is not None:
        return existing_problem
        
    raise HTTPException(status_code=404, detail="Задача не найдена или не удалось обновить")

# Удаление задачи (DELETE /problems/{id})
@app.delete("/api/problems/{id}", response_model=str)
async def delete_problem(id: str):
    try:
        obj_id = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    
    await type_bindings_collection.delete_many({"problem_id": obj_id})

    delete_result = await problems_collection.delete_one({"_id": obj_id})
    if delete_result.deleted_count == 1:
        return f"Задача Id={id} была удалена"
    raise HTTPException(status_code=404, detail="Задача не найдена для удаления")

# Получение всех задач (GET /problems)
@app.get("/api/problems", response_model=List[Problem])
async def get_all_problems():
    problems = await problems_collection.find().to_list(length=1000)
    return problems

# Присвоить тип задаче (POST /api/assign_type)
@app.post("/api/assign_type", response_model=str)
async def assign_type_to_problem(problem_with_type: ProblemWithType):
    type_binding_dump = problem_with_type.model_dump(by_alias=True)
    type_name = type_binding_dump["type_name"]
    problem_id = type_binding_dump["problem_id"]

    try:
        problem_doc = await problems_collection.find_one({"_id": ObjectId(problem_id)})
        if not problem_doc:
            raise HTTPException(status_code=404, detail=f"Задача с ID {problem_id} не найдена")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Некорректный problem_id: {problem_id}. Error: {e}")

    existing_type = await types_collection.find_one({"type_name": type_name})
    if not existing_type:
        insert_result = await types_collection.insert_one({"type_name": type_name})
        type_id = insert_result.inserted_id
    else:
        type_id = existing_type["_id"]

    existing_binding = await type_bindings_collection.find_one({"type_id": type_id, "problem_id": ObjectId(problem_id)})
    if existing_binding:
        return f"Задаче ID: '{problem_id}' уже присвоен тип '{type_name}'"

    await type_bindings_collection.insert_one({"type_id": type_id, "problem_id": ObjectId(problem_id)})
    return f"Задаче ID: '{problem_id}' присвоен тип '{type_name}'"

# Получение всех задач с определенным типом (GET /api/get_problems_by_type)
@app.get("/api/get_problems_by_type", response_model=List[Problem])
async def get_problems_by_type(problem_type: str):
    type_doc = await types_collection.find_one({"type_name": problem_type})
    if not type_doc:
        return [] 
    
    type_id_val = type_doc["_id"]
    
    problems_data = []
    bindings = await type_bindings_collection.find({"type_id": type_id_val}).to_list(length=None) 
    
    for binding in bindings:
        problem_id_val = binding.get("problem_id") 
        if not problem_id_val:
            print(f"Warning: Binding found for type_id {type_id_val} with no problem_id.")
            continue

        problem_doc = await problems_collection.find_one({"_id": problem_id_val})
        if problem_doc:
            problems_data.append(problem_doc)
        else:
            print(f"Warning: Binding found for type_id {type_id_val} to a non-existent problem_id {problem_id_val}")
            
    return problems_data

# Получение всех типов (GET /api/types)
@app.get("/api/types", response_model=List[str])
async def get_all_types():
    if "types_collection" not in await database.list_collection_names():
        return []
        
    type_objects = await types_collection.find({}, {"type_name": 1, "_id": 0}).to_list(length=None)
    types_list = [type_obj["type_name"] for type_obj in type_objects if "type_name" in type_obj]
    return types_list

# Для отладки можно добавить эндпоинт для просмотра всех привязок
@app.get("/api/debug/all_type_bindings", include_in_schema=False)
async def get_all_type_bindings():
    bindings = await type_bindings_collection.find().to_list(length=None)
    return [{"type_id": str(b.get("type_id")), "problem_id": str(b.get("problem_id"))} for b in bindings]

# Для отладки можно добавить эндпоинт для просмотра всех типов с их ID
@app.get("/api/debug/all_types_with_ids", include_in_schema=False)
async def get_all_types_with_ids():
    types = await types_collection.find().to_list(length=None)
    return [{"_id": str(t.get("_id")), "type_name": t.get("type_name")} for t in types]