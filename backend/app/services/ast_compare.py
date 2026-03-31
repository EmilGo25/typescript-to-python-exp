"""AST-based structural similarity comparison between two Python code snippets."""
from __future__ import annotations

import ast
from collections import Counter


def _extract_structure(code: str) -> dict | None:
    """Parse Python code and extract structural features from the AST."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None

    features: dict[str, Counter] = {
        "node_types": Counter(),
        "constructs": Counter(),
        "builtins_used": Counter(),
    }

    pythonic_constructs = {
        ast.ListComp: "list_comprehension",
        ast.DictComp: "dict_comprehension",
        ast.SetComp: "set_comprehension",
        ast.GeneratorExp: "generator_expression",
    }

    builtin_names = {
        "enumerate", "zip", "map", "filter", "sorted", "reversed",
        "any", "all", "sum", "min", "max", "len", "range", "isinstance",
        "dict", "list", "set", "tuple", "int", "float", "str", "bool",
    }

    for node in ast.walk(tree):
        node_type = type(node).__name__
        features["node_types"][node_type] += 1

        if type(node) in pythonic_constructs:
            features["constructs"][pythonic_constructs[type(node)]] += 1

        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in builtin_names:
                features["builtins_used"][node.func.id] += 1

        if isinstance(node, ast.For):
            features["constructs"]["for_loop"] += 1
        elif isinstance(node, ast.While):
            features["constructs"]["while_loop"] += 1
        elif isinstance(node, ast.If):
            features["constructs"]["if_statement"] += 1
        elif isinstance(node, ast.FunctionDef):
            features["constructs"]["function_def"] += 1
        elif isinstance(node, ast.Return):
            features["constructs"]["return"] += 1
        elif isinstance(node, ast.Starred):
            features["constructs"]["unpacking"] += 1
        elif isinstance(node, ast.ClassDef):
            features["constructs"]["class_def"] += 1
        elif isinstance(node, ast.Try):
            features["constructs"]["try_except"] += 1
        elif isinstance(node, ast.With):
            features["constructs"]["with_statement"] += 1

    return features


def _counter_similarity(a: Counter, b: Counter) -> float:
    """Compute similarity between two Counters using cosine-like metric."""
    all_keys = set(a) | set(b)
    if not all_keys:
        return 1.0
    intersection = sum(min(a.get(k, 0), b.get(k, 0)) for k in all_keys)
    union = sum(max(a.get(k, 0), b.get(k, 0)) for k in all_keys)
    return intersection / union if union > 0 else 1.0


def compute_ast_similarity(user_code: str, reference_code: str) -> float:
    """Compute structural similarity score (0–100) between user and reference code.

    Compares:
    - Node type distribution (40% weight)
    - Construct usage (40% weight)
    - Builtin function usage (20% weight)
    """
    user_features = _extract_structure(user_code)
    ref_features = _extract_structure(reference_code)

    if user_features is None or ref_features is None:
        return 0.0

    weights = {"node_types": 0.4, "constructs": 0.4, "builtins_used": 0.2}
    total = 0.0

    for key, weight in weights.items():
        sim = _counter_similarity(user_features[key], ref_features[key])
        total += sim * weight

    return round(total * 100, 1)
