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

def find_is_vs_equals_misuse(tree: ast.AST):
    issues = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            # node.ops: list of comparison operators (Is, Eq, etc.)
            # node.comparators: list of right-hand expressions
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)):
                    # Allow "is None" and "is not None" (best practice)
                    if isinstance(comp, ast.Constant) and comp.value is None:
                        continue

                    # Flag: using "is" with literals like strings/ints/bools
                    if isinstance(comp, ast.Constant):
                        issues.append({
                            "type": "is_vs_equals_misuse",
                            "severity": "medium",
                            "line": node.lineno,
                            "col": node.col_offset,
                            "message": "Possible misuse of 'is'/'is not' for value comparison. Use '==' or '!=' for literals.",
                            "suggested_fix": "Use '==' for equality checks (keep 'is None' only for None checks)."
                        })

    return issues

def find_shadowed_builtins(tree: ast.AST):
    issues = []

    builtins_to_flag = {
        "list", "dict", "set", "tuple", "str", "int", "float", "bool",
        "id", "type", "sum", "min", "max", "len", "map", "filter", "input"
    }

    def add_issue(name: str, lineno: int, col: int):
        issues.append({
            "type": "shadowed_builtin",
            "severity": "medium",
            "line": lineno,
            "col": col,
            "message": f"Variable name '{name}' shadows a Python built-in.",
            "suggested_fix": f"Rename '{name}' to something more specific (e.g., '{name}_value', '{name}_list')."
        })

    for node in ast.walk(tree):
        # Assignments like: list = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in builtins_to_flag:
                    add_issue(target.id, node.lineno, node.col_offset)

        # Function args like: def f(list): ...
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args:
                if arg.arg in builtins_to_flag:
                    add_issue(arg.arg, arg.lineno, arg.col_offset)

    return issues

def find_possible_missing_returns(tree: ast.AST):
    issues = []

    def has_return_with_value(func: ast.AST) -> bool:
        for n in ast.walk(func):
            if isinstance(n, ast.Return) and n.value is not None:
                return True
        return False

    def ends_with_guaranteed_return(body) -> bool:
        if not body:
            return False
        last = body[-1]

        # return ...
        if isinstance(last, ast.Return):
            return True

        # if/else where both sides guarantee return
        if isinstance(last, ast.If):
            return ends_with_guaranteed_return(last.body) and ends_with_guaranteed_return(last.orelse)

        # try where all relevant blocks guarantee return
        if isinstance(last, ast.Try):
            # If try has excepts, all except bodies must guarantee return too
            handlers_ok = all(ends_with_guaranteed_return(h.body) for h in last.handlers) if last.handlers else True
            orelse_ok = ends_with_guaranteed_return(last.orelse) if last.orelse else True
            final_ok = ends_with_guaranteed_return(last.finalbody) if last.finalbody else True
            return ends_with_guaranteed_return(last.body) and handlers_ok and orelse_ok and final_ok

        return False

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if has_return_with_value(node) and not ends_with_guaranteed_return(node.body):
                issues.append({
                    "type": "possible_missing_return",
                    "severity": "medium",
                    "line": node.lineno,
                    "col": node.col_offset,
                    "message": f"Function '{node.name}' may not return a value on all code paths.",
                    "suggested_fix": "Ensure all branches return a value (or return explicitly at the end)."
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
    issues.extend(find_is_vs_equals_misuse(tree))
    issues.extend(find_shadowed_builtins(tree))
    issues.extend(find_possible_missing_returns(tree))

    return {
        "success": True,
        "message": "Analysis complete",
        "issues": issues
    }