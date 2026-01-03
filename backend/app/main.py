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

def find_exception_swallowing(tree: ast.AST):
    issues = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                # handler.type is None for bare "except:"
                is_bare_except = handler.type is None

                # except Exception:
                is_exception_except = (
                    isinstance(handler.type, ast.Name) and handler.type.id == "Exception"
                )

                # If the except body is only "pass", it's swallowing
                body_is_just_pass = (
                    len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass)
                )

                if body_is_just_pass and (is_bare_except or is_exception_except):
                    issues.append({
                        "type": "exception_swallowing",
                        "severity": "high",
                        "line": handler.lineno,
                        "col": handler.col_offset,
                        "message": "Exception is caught and ignored using 'except: pass' or 'except Exception: pass'.",
                        "suggested_fix": "Handle the error, log it, or re-raise. Avoid silently ignoring exceptions."
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
    issues.extend(find_exception_swallowing(tree))


    return {
        "success": True,
        "message": "Analysis complete",
        "issues": issues
    }