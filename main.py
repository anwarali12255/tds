
import os
import sys
import traceback
from io import StringIO
from typing import List

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CodeRequest(BaseModel):
    code: str


class ErrorAnalysis(BaseModel):
    error_lines: List[int]


def execute_python_code(code: str) -> dict:
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured_stdout = StringIO()
    captured_stderr = StringIO()

    sys.stdout = captured_stdout
    sys.stderr = captured_stderr

    try:
        exec(compile(code, "<string>", "exec"), {})
        output = captured_stdout.getvalue() + captured_stderr.getvalue()
        return {"success": True, "output": output}

    except Exception:
        output = traceback.format_exc()
        return {"success": False, "output": output}

    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr



def analyze_error_with_ai(code: str, error_traceback: str) -> List[int]:
    client = OpenAI(
        api_key=os.environ["AIPIPE_TOKEN"],
        base_url="https://aipipe.org/openai/v1",
    )

    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[
            {
                "role": "system",
                "content": (
                    "Find the exact Python source line where the exception "
                    "occurred. Use the traceback and code. Return only JSON "
                    "in this format: {\"error_lines\": [3]}. "
                    "Line numbers refer to the supplied code, starting at 1."
                ),
            },
            {
                "role": "user",
                "content": f"CODE:\n{code}\n\nTRACEBACK:\n{error_traceback}",
            },
        ],
        response_format={"type": "json_object"},
    )

    import json

    result = json.loads(response.choices[0].message.content)
    valid_lines = set(range(1, len(code.splitlines()) + 1))

    return sorted({
        line for line in result.get("error_lines", [])
        if isinstance(line, int) and line in valid_lines
    })


@app.post("/code-interpreter")
def code_interpreter(request: CodeRequest):
    execution = execute_python_code(request.code)

    if execution["success"]:
        return {"error": [], "result": execution["output"]}

    try:
        error_lines = analyze_error_with_ai(
            request.code, execution["output"]
        )
    except Exception:
        error_lines = []

    return {
        "error": error_lines,
        "result": execution["output"],
    }
