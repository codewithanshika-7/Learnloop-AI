from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf import PdfReader

from datetime import date, datetime, timedelta
from dotenv import load_dotenv

from openai import OpenAI

import os
import json
import sqlite3
import bcrypt
import jwt


# =========================================================
# 1. LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SECRET_KEY = os.getenv("SECRET_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing from .env file")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is missing from .env file")


# =========================================================
# 2. FASTAPI APP
# =========================================================

app = FastAPI(
    title="LearnLoop API",
    description="AI-powered personalized learning platform",
    version="1.0.0"
)


# =========================================================
# 3. CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# 4. GROQ CLIENT
# =========================================================

groq_client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)


# =========================================================
# 5. SETTINGS
# =========================================================

ALGORITHM = "HS256"

AI_MODEL = "openai/gpt-oss-20b"


# =========================================================
# 6. DATABASE
# =========================================================

def init_db():

    conn = sqlite3.connect("learnloop.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# 7. PYDANTIC MODELS
# =========================================================

class UserSignUp(BaseModel):
    name: str
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class QuizRequest(BaseModel):
    syllabus: str
    level: str = "Beginner"
    topic: str = "Full Syllabus"
    difficulty: str = "Mixed"


# =========================================================
# 8. HOME
# =========================================================

@app.get("/")
def home():

    return {
        "message": "LearnLoop backend is running 🚀",
        "ai_provider": "Groq",
        "model": AI_MODEL
    }


# =========================================================
# 9. SIGN UP
# =========================================================

@app.post("/signup")
def signup(user: UserSignUp):

    conn = sqlite3.connect("learnloop.db")
    cursor = conn.cursor()

    try:

        hashed = bcrypt.hashpw(
            user.password.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        cursor.execute(
            """
            INSERT INTO users
            (name, email, hashed_password)
            VALUES (?, ?, ?)
            """,
            (
                user.name,
                user.email,
                hashed
            )
        )

        conn.commit()

        return {
            "success": True,
            "message": "Account created successfully!"
        }

    except sqlite3.IntegrityError:

        raise HTTPException(
            status_code=400,
            detail="Email already registered."
        )

    finally:

        conn.close()


# =========================================================
# 10. LOGIN
# =========================================================

@app.post("/login")
def login(user: UserLogin):

    conn = sqlite3.connect("learnloop.db")
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, hashed_password
        FROM users
        WHERE email = ?
        """,
        (user.email,)
    )

    record = cursor.fetchone()

    conn.close()

    if not record:

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    if not bcrypt.checkpw(
        user.password.encode("utf-8"),
        record[2].encode("utf-8")
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid email or password."
        )

    token_data = {
        "sub": str(record[0]),
        "name": record[1],
        "exp": datetime.utcnow() + timedelta(days=7)
    }

    token = jwt.encode(
        token_data,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_name": record[1]
    }


# =========================================================
# 11. EXTRACT PDF TEXT
# =========================================================

def extract_pdf_text(file):

    try:

        reader = PdfReader(file)

        text = ""

        for page in reader.pages:

            text += page.extract_text() or ""

        return text

    except Exception as e:

        print("PDF ERROR:", e)

        raise HTTPException(
            status_code=400,
            detail="Could not read the uploaded PDF."
        )


# =========================================================
# 12. GENERATE ROADMAP
# =========================================================

@app.post("/generate-roadmap")
async def generate_roadmap(
    syllabus: UploadFile = File(...),
    exam_date: str = Form(...),
    study_hours: int = Form(...),
    level: str = Form(...)
):

    # -----------------------------------------------------
    # Validate PDF
    # -----------------------------------------------------

    if not syllabus.filename.lower().endswith(".pdf"):

        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF syllabus."
        )


    # -----------------------------------------------------
    # Extract syllabus
    # -----------------------------------------------------

    text = extract_pdf_text(syllabus.file)

    if not text.strip():

        raise HTTPException(
            status_code=400,
            detail="No readable text found in the PDF."
        )


    # -----------------------------------------------------
    # Validate exam date
    # -----------------------------------------------------

    try:

        exam = date.fromisoformat(exam_date)

    except ValueError:

        raise HTTPException(
            status_code=400,
            detail="Invalid exam date. Use YYYY-MM-DD."
        )


    today = date.today()

    days_left = (exam - today).days


    if days_left <= 0:

        raise HTTPException(
            status_code=400,
            detail="Please select a future exam date."
        )


    # -----------------------------------------------------
    # Validate study hours
    # -----------------------------------------------------

    if study_hours < 1 or study_hours > 12:

        raise HTTPException(
            status_code=400,
            detail="Study hours must be between 1 and 12."
        )


    # -----------------------------------------------------
    # Limit extremely large PDF text
    # -----------------------------------------------------

    syllabus_text = text[:12000]


    # =====================================================
    # GROQ ROADMAP PROMPT
    # =====================================================

    prompt = f"""
You are LearnLoop AI, an adaptive learning planner.

Create a realistic personalized study roadmap for a college
student preparing for an exam.

TODAY'S DATE:
{today}

EXAM DATE:
{exam}

DAYS AVAILABLE:
{days_left}

DAILY STUDY TIME:
{study_hours} hours

STUDENT LEVEL:
{level}

SYLLABUS:
{syllabus_text}

IMPORTANT RULES:

1. The roadmap MUST fit completely within the available
   {days_left} days.

2. Do NOT create a roadmap beyond the exam date.

3. Do NOT assume actual exam weightage unless it is
   explicitly provided in the syllabus.

4. Use topic complexity, prerequisite relationships,
   and conceptual importance to prioritize topics.

5. Break large topics into smaller actionable tasks.

6. Give more time to difficult topics.

7. Keep the workload realistic for {study_hours}
   hours per day.

8. Include revision and practice.

9. Prioritize topics using:
   HIGH PRIORITY
   MEDIUM PRIORITY
   LOW PRIORITY

10. Create a DAY-BY-DAY roadmap.

11. Do not simply repeat the syllabus.

12. Convert the syllabus into an actionable study plan.

13. Make sure total estimated hours for each day
    do not exceed {study_hours} hours.

For every day include:

- Day number
- Date
- Topic/title
- Priority
- Estimated study hours
- Subtopics
- Practice task

Also provide:

- Most important topics to master
- Topics that can be studied at a basic level
- Final revision strategy

Return ONLY valid JSON.

Use exactly this structure:

{{
    "days_left": {days_left},
    "total_hours_per_day": {study_hours},

    "roadmap": [
        {{
            "day": 1,
            "date": "YYYY-MM-DD",
            "title": "Topic name",
            "priority": "HIGH PRIORITY",
            "estimated_hours": 2,
            "subtopics": [
                "Subtopic 1",
                "Subtopic 2"
            ],
            "practice_task": "Practice task"
        }}
    ],

    "most_important_topics": [
        "Topic 1",
        "Topic 2"
    ],

    "basic_level_topics": [
        "Topic 1",
        "Topic 2"
    ],

    "final_revision_strategy": [
        "Revision step 1",
        "Revision step 2"
    ]
}}
"""


    # =====================================================
    # CALL GROQ
    # =====================================================

    try:

        response = groq_client.chat.completions.create(

            model=AI_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are LearnLoop AI. "
                        "Return ONLY valid JSON. "
                        "Never add markdown or extra text."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            response_format={
                "type": "json_object"
            }
        )


        result = response.choices[0].message.content

        # Convert Groq response into Python dictionary
        roadmap_data = json.loads(result)

        # -------------------------------------------------
        # IMPORTANT:
        # Send syllabus text back to frontend so that the
        # same syllabus can later be used for quiz generation.
        # -------------------------------------------------

        roadmap_data["syllabus_text"] = syllabus_text

        return roadmap_data


    except json.JSONDecodeError:

        raise HTTPException(
            status_code=500,
            detail="AI returned invalid JSON."
        )


    except Exception as e:

        print("GROQ ROADMAP ERROR:", e)

        raise HTTPException(
            status_code=500,
            detail="Unable to generate roadmap using Groq."
        )


# =========================================================
# 13. GENERATE QUIZ
# =========================================================

@app.post("/generate-quiz")
def generate_quiz(req: QuizRequest):

    # -----------------------------------------------------
    # Validate syllabus
    # -----------------------------------------------------

    if not req.syllabus.strip():

        raise HTTPException(
            status_code=400,
            detail="Syllabus is required to generate a quiz."
        )


    syllabus_text = req.syllabus[:12000]


    # =====================================================
    # GROQ QUIZ PROMPT
    # =====================================================

    prompt = f"""
You are LearnLoop AI, an AI-powered education assistant.

Create a quiz based ONLY on the provided syllabus.

SYLLABUS:
{syllabus_text}

TOPIC:
{req.topic}

STUDENT LEVEL:
{req.level}

DIFFICULTY:
{req.difficulty}

Create exactly 5 multiple-choice questions.

Each question must contain:

- id
- question
- topic
- difficulty
- exactly 4 options
- correct_answer
- explanation

Difficulty must be one of:

Easy
Medium
Hard

Rules:

1. Questions must be based ONLY on the provided syllabus.
2. Do not invent topics outside the syllabus.
3. Mix Easy, Medium and Hard questions when difficulty is Mixed.
4. Every question must have exactly four options.
5. Only one option must be correct.
6. Keep explanations short and educational.
7. Return ONLY valid JSON.

Use exactly this structure:

{{
    "topic": "{req.topic}",

    "questions": [
        {{
            "id": 1,
            "question": "Question text",
            "topic": "Topic name",
            "difficulty": "Easy",

            "options": [
                "Option A",
                "Option B",
                "Option C",
                "Option D"
            ],

            "correct_answer": "Option A",

            "explanation": "Short explanation"
        }}
    ]
}}
"""


    # =====================================================
    # CALL GROQ
    # =====================================================

    try:

        response = groq_client.chat.completions.create(

            model=AI_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are LearnLoop AI. "
                        "Return ONLY valid JSON."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            response_format={
                "type": "json_object"
            }
        )


        result = response.choices[0].message.content

        quiz_data = json.loads(result)

        return quiz_data


    except json.JSONDecodeError:

        raise HTTPException(
            status_code=500,
            detail="AI returned invalid quiz JSON."
        )


    except Exception as e:

        print("GROQ QUIZ ERROR:", e)

        raise HTTPException(
            status_code=500,
            detail="Unable to generate quiz using Groq."
        )