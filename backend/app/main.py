from fastapi import FastAPI
from pydantic import BaseModel
import ast

app = FastAPI()

class AnalyzeRequest(BaseModel):
    code: str

@app.get("/")
def read_root():
    return {"status": "AI Code Reviewer backend running"}

def find_mutable_default_args(tree: ast.AST):
    issues = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # defaults correspond to the last N positional args
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    issues.append({
                        "type": "mutable_default_argument",
                        "severity": "high",
                        "line": node.lineno,
                        "col": node.col_offset,
                        "message": f"Function '{node.name}' has a mutable default argument (list/dict/set).",
                        "suggested_fix": "Use None as the default and create a new list/dict/set inside the function."
                    })

    return issues

@app.post("/analyze")
def analyze_code(request: AnalyzeRequest):
    try:
        tree = ast.parse(request.code)
    except SyntaxError as e:
        return {
            "success": False,
            "message": "Syntax error",
            "issues": [
                {
                    "type": "syntax_error",
                    "severity": "high",
                    "line": e.lineno,
                    "col": e.offset,
                    "details": e.msg
                }
            ]
        }

    issues = []
    issues.extend(find_mutable_default_args(tree))

    return {
        "success": True,
        "message": "Analysis complete",
        "issues": issues
    }