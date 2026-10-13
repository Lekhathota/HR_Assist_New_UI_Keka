"""Languages candidates may answer coding questions in, with stdin/stdout starter templates."""

from __future__ import annotations

import json
import os

# Judge0 CE language ids (override with JUDGE0_LANGUAGE_IDS='{"python": 92, ...}' for other Judge0 builds).
LANGUAGES: dict[str, dict] = {
    "python": {
        "label": "Python 3",
        "judge0_id": 71,
        "template": (
            "import sys\n\n\n"
            "def main():\n"
            "    data = sys.stdin.read().split()\n"
            "    # Solve using the input format above and print the result.\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    main()\n"
        ),
    },
    "javascript": {
        "label": "JavaScript (Node.js)",
        "judge0_id": 63,
        "template": (
            "const data = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/);\n"
            "// Solve using the input format above and print the result with console.log.\n"
        ),
    },
    "java": {
        "label": "Java",
        "judge0_id": 62,
        "template": (
            "import java.io.*;\n"
            "import java.util.*;\n\n"
            "public class Main {\n"
            "    public static void main(String[] args) throws IOException {\n"
            "        BufferedReader in = new BufferedReader(new InputStreamReader(System.in));\n"
            "        // Solve using the input format above and print the result.\n"
            "    }\n"
            "}\n"
        ),
    },
    "c": {
        "label": "C",
        "judge0_id": 50,
        "template": (
            "#include <stdio.h>\n\n"
            "int main(void) {\n"
            "    /* Solve using the input format above and print the result. */\n"
            "    return 0;\n"
            "}\n"
        ),
    },
    "cpp": {
        "label": "C++",
        "judge0_id": 54,
        "template": (
            "#include <bits/stdc++.h>\n"
            "using namespace std;\n\n"
            "int main() {\n"
            "    ios::sync_with_stdio(false);\n"
            "    cin.tie(nullptr);\n"
            "    // Solve using the input format above and print the result.\n"
            "    return 0;\n"
            "}\n"
        ),
    },
}

DEFAULT_LANGUAGE = "python"

_ALIASES = {
    "python": "python", "python3": "python", "py": "python",
    "javascript": "javascript", "js": "javascript", "node": "javascript", "node.js": "javascript", "nodejs": "javascript",
    "java": "java",
    "c": "c",
    "c++": "cpp", "cpp": "cpp", "cplusplus": "cpp",
}


def normalize_language(value: object) -> str:
    """Map free-text language names to a supported key, or '' when unsupported."""
    return _ALIASES.get(str(value or "").strip().lower(), "")


def judge0_language_id(language: str) -> int:
    overrides = os.environ.get("JUDGE0_LANGUAGE_IDS") or ""
    if overrides:
        try:
            mapping = json.loads(overrides)
            if language in mapping:
                return int(mapping[language])
        except (ValueError, TypeError):
            pass
    return int(LANGUAGES[language]["judge0_id"])


def language_options(allowed: list[str] | None = None) -> list[dict]:
    keys = [k for k in (allowed or list(LANGUAGES)) if k in LANGUAGES] or list(LANGUAGES)
    return [{"key": k, "label": LANGUAGES[k]["label"], "template": LANGUAGES[k]["template"]} for k in keys]
