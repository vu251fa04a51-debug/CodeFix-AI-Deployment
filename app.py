
import ast
import io
import os
import re
import sys
import time
import tempfile
import subprocess

import requests
import streamlit as st

try:
    import pyflakes.api
    import pyflakes.reporter
    PYFLAKES_AVAILABLE = True
except ImportError:
    PYFLAKES_AVAILABLE = False


# =====================================================
# PAGE CONFIGURATION
# =====================================================

st.set_page_config(
    page_title="CodeFix AI",
    page_icon="🐞",
    layout="wide"
)

st.title("🐞 CodeFix AI")
st.subheader("Python Compiler, Error Detector and AI Code Corrector")

st.write(
    "Write Python programs, detect errors, get AI-assisted "
    "corrections and execute your code."
)

st.info(
    "Local development application. Execute only code you trust. "
    "Programs run with your Windows user permissions."
)


# =====================================================
# SAMPLE PROGRAMS
# =====================================================

SAMPLES = {
    "Select Sample": "",

    "Hello World": '''print("Hello World")
print("Welcome to CodeFix AI")
''',

    "Addition Program": '''a = 10
b = 20
result = a + b
print("Sum:", result)
''',

    "Missing Parenthesis": '''name = "Saru"
print("Hello", name
''',

    "Missing Colon": '''age = 20

if age >= 18
    print("Eligible to vote")
''',

    "Indentation Error": '''def greet():
print("Hello Student")
print("Welcome")
''',

    "Name Error": '''name = "Saru"
print(nam)
''',

    "Type Error": '''age = 20
message = "My age is " + age
print(message)
''',

    "Library Management System": '''books = [
    {"title": "Python", "available": True},
    {"title": "Java", "available": True}
]

def display_books():
    print("LIBRARY BOOKS")
    for book in books:
        print(book["title"], book["available"])

def borrow_book(name):
    for book in books:
        if book["title"] == name:
            book["available"] = False
            print("Book borrowed successfully")
            return
    print("Book not found")

def main():
    display_books()
    borrow_book("Python")
    display_books()

if __name__ == "__main__":
    main()
''',

    "Student Management System": '''students = [
    {"name": "Ravi", "marks": 85},
    {"name": "Sita", "marks": 92}
]

def display_students():
    for student in students:
        print(student["name"], student["marks"])

def add_student(name, marks):
    students.append({"name": name, "marks": marks})

def main():
    display_students()
    add_student("Priya", 95)
    print("After adding student:")
    display_students()

if __name__ == "__main__":
    main()
'''
}


# =====================================================
# SESSION STATE
# =====================================================

DEFAULTS = {
    "python_code": "",
    "program_input": "",
    "analysis_result": None,
    "execution_result": None,
    "suggested_code": None,
    "suggested_execution": None,
    "fix_message": "",
    "history": []
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset_results():
    st.session_state.analysis_result = None
    st.session_state.execution_result = None
    st.session_state.suggested_code = None
    st.session_state.suggested_execution = None
    st.session_state.fix_message = ""


def load_sample():
    st.session_state.python_code = SAMPLES[
        st.session_state.sample_choice
    ]
    reset_results()


def clear_editor():
    st.session_state.python_code = ""
    st.session_state.program_input = ""
    reset_results()


def apply_correction():
    candidate = st.session_state.suggested_code

    if candidate:
        st.session_state.python_code = candidate

    reset_results()


# =====================================================
# STATIC ERROR ANALYSIS
# =====================================================

def analyze_code(code):
    result = {
        "syntax_ok": True,
        "syntax": "No syntax errors found.",
        "static": ""
    }

    try:
        ast.parse(code)

    except SyntaxError as error:
        result["syntax_ok"] = False
        result["syntax"] = (
            f"{error.msg} at line {error.lineno}, "
            f"column {error.offset}"
        )

    if PYFLAKES_AVAILABLE:
        output = io.StringIO()
        reporter = pyflakes.reporter.Reporter(output, output)

        try:
            pyflakes.api.check(
                code,
                "<CodeFix AI>",
                reporter
            )
            result["static"] = output.getvalue()

        except Exception as error:
            result["static"] = str(error)

    else:
        result["static"] = (
            "Pyflakes is not installed. "
            "Install it using: pip install pyflakes"
        )

    return result


# =====================================================
# PYTHON PROGRAM EXECUTION
# =====================================================

def execute_code(code, user_input="", timeout=5):
    start = time.perf_counter()

    try:
        with tempfile.TemporaryDirectory(
            prefix="codefix_"
        ) as temp_dir:

            file_path = os.path.join(
                temp_dir,
                "program.py"
            )

            with open(
                file_path,
                "w",
                encoding="utf-8"
            ) as file:
                file.write(code)

            process = subprocess.run(
                [sys.executable, file_path],
                input=user_input,
                capture_output=True,
                text=True,
                cwd=temp_dir,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )

            elapsed = time.perf_counter() - start

            return {
                "success": process.returncode == 0,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "returncode": process.returncode,
                "time": round(elapsed, 4),
                "timeout": False
            }

    except subprocess.TimeoutExpired as error:
        return {
            "success": False,
            "stdout": error.stdout or "",
            "stderr": "Execution stopped: time limit exceeded.",
            "returncode": -1,
            "time": round(time.perf_counter() - start, 4),
            "timeout": True
        }

    except Exception as error:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(error),
            "returncode": -1,
            "time": round(time.perf_counter() - start, 4),
            "timeout": False
        }


# =====================================================
# LOCAL AI CORRECTION USING OLLAMA
# =====================================================

def extract_code(response):
    response = response.strip()

    match = re.search(
        r"```(?:python|py)?\s*(.*?)```",
        response,
        re.DOTALL | re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    return response


def ask_local_ai(
    code,
    problem,
    model,
    ollama_url
):
    prompt = f"""
You are an expert Python debugging assistant.

Your task is to repair the supplied Python program.

IMPORTANT RULES:
1. Return the COMPLETE corrected Python program.
2. Preserve the original program's purpose and features.
3. Fix syntax errors, runtime errors and clear coding mistakes.
4. Do not replace the program with an unrelated example.
5. Do not remove functions or important code.
6. Preserve existing variable names where possible.
7. Do not include explanations outside the code.
8. Do not invent program output.
9. Do not claim a correction is guaranteed.
10. Return only a Python code block.

PROBLEM REPORTED:
{problem}

ORIGINAL PYTHON CODE:
{code}

Return the complete corrected program.
"""

    response = requests.post(
        ollama_url.rstrip("/") + "/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        },
        timeout=240
    )

    response.raise_for_status()

    data = response.json()

    return extract_code(data.get("response", ""))


# =====================================================
# BASIC FALLBACK CORRECTION
# =====================================================

def basic_syntax_fix(code):
    for attempt in range(10):

        try:
            ast.parse(code)
            return code

        except SyntaxError as error:
            lines = code.splitlines()

            if not error.lineno:
                return None

            index = error.lineno - 1

            if index < 0 or index >= len(lines):
                return None

            line = lines[index]
            message = error.msg.lower()

            if "expected ':'" in message:
                lines[index] = line.rstrip() + ":"

            elif "unmatched ')'" in message:
                position = line.rfind(")")
                if position < 0:
                    return None

                lines[index] = (
                    line[:position] + line[position + 1:]
                )

            elif "unmatched ']'" in message:
                position = line.rfind("]")
                if position < 0:
                    return None

                lines[index] = (
                    line[:position] + line[position + 1:]
                )

            elif "was never closed" in message:
                if "[" in message:
                    lines.append("]")
                elif "(" in message:
                    lines.append(")")
                elif "{" in message:
                    lines.append("}")
                else:
                    return None

            elif "expected an indented block" in message:
                next_index = index + 1

                if next_index >= len(lines):
                    return None

                if not lines[next_index].strip():
                    return None

                lines[next_index] = (
                    "    " + lines[next_index].lstrip()
                )

            elif "unexpected indent" in message:
                if line.startswith("    "):
                    lines[index] = line[4:]
                else:
                    return None

            else:
                return None

            code = "\n".join(lines)

    try:
        ast.parse(code)
        return code
    except SyntaxError:
        return None


# =====================================================
# COMPLETE CORRECTION PROCESS
# =====================================================

def correct_program(
    code,
    problem,
    model,
    ollama_url
):
    ai_error = ""

    # First attempt: local AI model
    for attempt in range(2):
        try:
            candidate = ask_local_ai(
                code,
                problem,
                model,
                ollama_url
            )

            if not candidate.strip():
                raise ValueError("AI returned empty code.")

            # Validate complete corrected program.
            ast.parse(candidate)

            if candidate.strip() == code.strip():
                raise ValueError(
                    "AI returned the original code without correcting it."
                )

            return (
                candidate,
                "AI correction generated and passed syntax validation."
            )

        except Exception as error:
            ai_error = str(error)

    # Second attempt: basic syntax rules
    candidate = basic_syntax_fix(code)

    if candidate and candidate.strip() != code.strip():
        try:
            ast.parse(candidate)

            return (
                candidate,
                "Basic correction passed syntax validation. "
                "The local AI model could not provide a usable correction."
            )

        except SyntaxError:
            pass

    return (
        None,
        "A safe correction could not be generated. "
        "AI details: " + ai_error[:500]
    )


# =====================================================
# SIDEBAR SETTINGS
# =====================================================

st.sidebar.title("⚙️ Settings")

ollama_url = st.sidebar.text_input(
    "Ollama address",
    value="http://localhost:11434"
)

model = st.sidebar.text_input(
    "Local AI model",
    value="qwen2.5-coder:3b"
)

timeout = st.sidebar.slider(
    "Execution time limit (seconds)",
    min_value=1,
    max_value=30,
    value=5
)

st.sidebar.divider()

st.sidebar.write("**CodeFix AI tools**")
st.sidebar.write("🐍 Python execution")
st.sidebar.write("🔍 AST syntax analysis")
st.sidebar.write("📋 Pyflakes static analysis")
st.sidebar.write("🧠 Local AI correction")
st.sidebar.write("📤 Program output and traceback")

st.sidebar.caption(
    "AI correction requires Ollama and a downloaded coding model."
)


# =====================================================
# SAMPLE SELECTION
# =====================================================

st.divider()
st.subheader("1. Load Sample Program")

st.selectbox(
    "Choose a Python program",
    list(SAMPLES.keys()),
    key="sample_choice"
)

st.button(
    "📂 Load Sample",
    on_click=load_sample,
    use_container_width=True
)


# =====================================================
# PYTHON EDITOR
# =====================================================

st.divider()
st.subheader("2. Python Code Editor")

st.text_area(
    "Write or paste your Python code:",
    key="python_code",
    height=400,
    placeholder="Enter your Python program here..."
)

st.download_button(
    "⬇️ Download Original Code",
    data=st.session_state.python_code,
    file_name="program.py",
    mime="text/x-python",
    use_container_width=True
)


# =====================================================
# PROGRAM INPUT
# =====================================================

st.subheader("3. Program Input")

st.write(
    "Enter values needed by input(). "
    "Put each input value on a separate line."
)

st.text_area(
    "Input values",
    key="program_input",
    height=100,
    placeholder="Example:\nSaru\n20"
)


# =====================================================
# MAIN ACTION BUTTONS
# =====================================================

st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    run_button = st.button(
        "▶️ Run Code",
        use_container_width=True
    )

with col2:
    analyze_button = st.button(
        "🔍 Detect Errors",
        use_container_width=True
    )

with col3:
    fix_button = st.button(
        "🧠 AI Auto Fix",
        use_container_width=True
    )

st.button(
    "🗑️ Clear Editor",
    on_click=clear_editor,
    use_container_width=True
)


# =====================================================
# RUN ORIGINAL CODE
# =====================================================

if run_button:
    code = st.session_state.python_code

    if not code.strip():
        st.warning("Please enter Python code first.")

    else:
        st.session_state.execution_result = execute_code(
            code,
            st.session_state.program_input,
            timeout
        )

        st.session_state.history.append({
            "action": "Run Code",
            "success": st.session_state.execution_result["success"],
            "time": time.strftime("%H:%M:%S")
        })


# =====================================================
# DETECT ERRORS
# =====================================================

if analyze_button:
    code = st.session_state.python_code

    if not code.strip():
        st.warning("Please enter Python code first.")

    else:
        st.session_state.analysis_result = analyze_code(code)


# =====================================================
# AI AUTO FIX
# =====================================================

if fix_button:
    code = st.session_state.python_code

    if not code.strip():
        st.warning("Please enter Python code first.")

    else:
        with st.spinner(
            "AI is analyzing your program and generating corrections..."
        ):

            analysis = analyze_code(code)

            if not analysis["syntax_ok"]:
                problem = (
                    "Python syntax error: " + analysis["syntax"]
                )

            else:
                original_run = execute_code(
                    code,
                    st.session_state.program_input,
                    timeout
                )

                if original_run["success"]:
                    problem = (
                        "The program passed syntax analysis and "
                        "executed successfully. Preserve its behavior. "
                        "Only fix clear errors if any exist."
                    )

                else:
                    problem = (
                        "Program execution failed.\n"
                        + original_run["stderr"]
                    )

            candidate, message = correct_program(
                code,
                problem,
                model,
                ollama_url
            )

            st.session_state.suggested_code = candidate
            st.session_state.fix_message = message
            st.session_state.suggested_execution = None

            if candidate:
                st.session_state.suggested_execution = execute_code(
                    candidate,
                    st.session_state.program_input,
                    timeout
                )

        st.session_state.history.append({
            "action": "AI Auto Fix",
            "success": bool(candidate),
            "time": time.strftime("%H:%M:%S")
        })


# =====================================================
# ERROR ANALYSIS RESULTS
# =====================================================

if st.session_state.analysis_result:

    result = st.session_state.analysis_result

    st.divider()
    st.subheader("4. Error Detection Results")

    if result["syntax_ok"]:
        st.success(result["syntax"])
    else:
        st.error(result["syntax"])

    st.write("**Additional static analysis**")

    if result["static"].strip():
        st.code(result["static"])
    else:
        st.success("No additional Pyflakes warnings found.")

    if not PYFLAKES_AVAILABLE:
        st.warning(
            "Pyflakes is not installed. Run: "
            "python -m pip install pyflakes"
        )


# =====================================================
# ORIGINAL PROGRAM OUTPUT
# =====================================================

if st.session_state.execution_result:

    result = st.session_state.execution_result

    st.divider()
    st.subheader("5. Original Program Execution")

    if result["success"]:
        st.success("Program executed successfully!")

    elif result["timeout"]:
        st.warning("Program stopped because the time limit was reached.")

    else:
        st.error("Program execution failed.")

    st.write("**Program Output**")

    if result["stdout"]:
        st.code(result["stdout"])
    else:
        st.info("No output was produced.")

    if result["stderr"]:
        st.write("**Error Message / Traceback**")
        st.code(result["stderr"])

    st.caption(
        f"Return code: {result['returncode']} | "
        f"Execution time: {result['time']} seconds"
    )


# =====================================================
# SUGGESTED CORRECTED CODE
# =====================================================

if st.session_state.fix_message:

    st.divider()
    st.subheader("6. Suggested Corrected Code")

    st.write(st.session_state.fix_message)

    candidate = st.session_state.suggested_code

    if candidate:

        try:
            # Validate before showing as corrected.
            ast.parse(candidate)

            st.success(
                "Suggested code passed Python syntax validation."
            )

            st.code(
                candidate,
                language="python"
            )

            st.download_button(
                "⬇️ Download Corrected Code",
                data=candidate,
                file_name="corrected_program.py",
                mime="text/x-python",
                use_container_width=True
            )

            st.button(
                "✅ Replace Original Code with Correction",
                on_click=apply_correction,
                use_container_width=True
            )

        except SyntaxError:
            st.error(
                "The suggested code failed syntax validation. "
                "It will not be accepted as a valid correction."
            )

        # Show execution of suggested program
        suggested_run = st.session_state.suggested_execution

        if suggested_run:

            st.divider()
            st.subheader("7. Corrected Program Execution")

            if suggested_run["success"]:
                st.success(
                    "Corrected program executed successfully!"
                )
            else:
                st.warning(
                    "The suggested program still has an execution "
                    "error. Check the traceback below."
                )

            st.write("**Corrected Program Output**")

            if suggested_run["stdout"]:
                st.code(suggested_run["stdout"])
            else:
                st.info("No output was produced.")

            if suggested_run["stderr"]:
                st.write("**Remaining Error / Traceback**")
                st.code(suggested_run["stderr"])

            st.caption(
                f"Execution time: {suggested_run['time']} seconds"
            )

    else:
        st.warning(
            "A validated correction could not be generated. "
            "Your original code has not been changed."
        )


# =====================================================
# RECENT ACTIVITY
# =====================================================

st.divider()

with st.expander("📜 Recent Activity"):

    if st.session_state.history:

        for item in reversed(st.session_state.history[-10:]):

            status = (
                "Success"
                if item["success"]
                else "Needs attention"
            )

            st.write(
                f"{item['time']} | {item['action']} | {status}"
            )

    else:
        st.write("No activity yet.")


# =====================================================
# FOOTER
# =====================================================

st.divider()

st.subheader("About CodeFix AI")

col1, col2, col3 = st.columns(3)

col1.metric("Language", "Python")
col2.metric("Code Analysis", "AST + Pyflakes")
col3.metric("AI Engine", "Ollama")

st.caption(
    "CodeFix AI — Beginner Code Error Detection and Explanation System"
)

