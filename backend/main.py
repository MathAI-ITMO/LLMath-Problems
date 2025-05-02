from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from bson import ObjectId
import motor.motor_asyncio

app = FastAPI()

MONGO_DETAILS = "mongodb://mongoadmin:mongoadmin@mongo:27017/?authSource=admin"

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DETAILS)
database = client.my_database
collection = database.problems_collection
names_collection = database.names_collection
binding_collection = database.binding_collection


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
    statement: str
    geolin_ans_key: GeoilonAnsKey
    result: Optional[str] = ""
    solution: Solution

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class ProblemWithName(BaseModel):
    name: str
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
    result = await collection.insert_one(problem_dict)
    created_problem = await collection.find_one({"_id": result.inserted_id})
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
    problem = await collection.find_one({"_id": obj_id})
    if problem is not None:
        return problem
    raise HTTPException(status_code=404, detail="Задача не найдена")


# Обновление задачи по идентификатору (PUT /problems/{id})
@app.put("/api/problems/{id}", response_model=Problem)
async def update_problem(id: str, problem: Problem):
    try:
        obj_id = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    problem_data = problem.model_dump(by_alias=True, exclude_unset=True)
    update_result = await collection.update_one({"_id": obj_id}, {"$set": problem_data})
    if update_result.modified_count == 1:
        updated_problem = await collection.find_one({"_id": obj_id})
        if updated_problem is not None:
            return updated_problem
    existing_problem = await collection.find_one({"_id": obj_id})
    if existing_problem is not None:
        return existing_problem
    raise HTTPException(status_code=404, detail="Задача не найдена")

# Удаление задачи (POST /problems)
@app.post("/api/problems/{id}", response_model=str)
async def delete_problem(id: str):
    try:
        obj_id = ObjectId(id)
    except Exception:
        raise HTTPException(status_code=400, detail="Некорректный идентификатор")
    delete_one = await collection.delete_one({"_id": obj_id})
    return f"Задача Id={id} была удалена"

# Получение всех задач (GET /problems)
@app.get("/api/problems", response_model=List[Problem])
async def get_all_problems():
    problems = await collection.find().to_list(length=1000)
    return problems

# Создать имя задачи (POST /problems/give_a_name)
@app.post("/api/give_a_name", response_model=str)
async def give_a_name_a_problem(problem_with_name: ProblemWithName):
    problem_name_dump = problem_with_name.model_dump(by_alias=True)
    name = problem_name_dump["name"]
    problem_id = problem_name_dump["problem_id"]
    print(name, problem_id)
    try:
        problem = await collection.find_one({"_id": problem_id})
    except:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    created_name = None
    if "names_collection" in await database.list_collection_names():
        created_name = await names_collection.find_one({"name": name})
    if created_name is None:
        name_id = await names_collection.insert_one({"name": name})
        created_name = await names_collection.find_one({"_id": name_id.inserted_id})
    binding = await binding_collection.insert_one({"name_id": created_name['_id'], "problem_id": problem_id})    
    return f"Задаче: '{problem_id}' присовено имя '{name}'"


# Получение всех задач с определенным именем(GET /problems)
@app.get("/api/get_problems_by_name", response_model=List[Problem])
async def get_problems_by_name(problem_name: str):
    try: 
        name_id =(await names_collection.find_one({"name": problem_name}))["_id"]
    except:
        raise HTTPException(status_code=404, detail="Имя не найдено")
    problems = [await collection.find_one({"_id": binding["problem_id"]}) 
                for binding in (await binding_collection.find({"name_id": name_id}).to_list())]
    return problems

# Получение всех имен (GET /names)
@app.get("/api/names", response_model=List[str])
async def get_all_names():
    names = [name_obj["name"] for name_obj in await names_collection.find().to_list()]
    return names