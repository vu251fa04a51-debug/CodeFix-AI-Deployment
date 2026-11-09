import ast
import io
import os
import re
import subprocess
import sys
import tempfile
import time
import tokenize

import requests
import streamlit as st

try:
    import pyflakes.api
    import pyflakes.reporter
except ImportError:
    pyflakes = None


st.set_page_config(
    page_title="CodeFix AI",
    page_icon="🐞",
    layout="wide",
)

st.title("🐞 CodeFix AI")
st.subheader("Beginner Code Error Detection and Explanation System")
st.write(
    "Write or paste Python code, review clear explanations, run it, "
    "and validate a proposed correction before using it."
)
st.warning(
    "Code execution is not sandboxed. Programs run with your Windows "
    "user permissions. Run only code you trust."
)


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
''',
}


DEFAULTS = {
    "python_code": "",
    "program_input": "",
    "analysis_result": None,
    "execution_result": None,
    "suggested_code": None,
    "suggested_execution": None,
    "fix_message": "",
    "history": [],
}

for state_key, default_value in DEFAULTS.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = (
            list(default_value) if isinstance(default_value, list) else default_value
        )


def reset_results():
    st.session_state.analysis_result = None
    st.session_state.execution_result = None
    st.session_state.suggested_code = None
    st.session_state.suggested_execution = None
    st.session_state.fix_message = ""


def clear_editor():
    st.session_state.python_code = ""
    st.session_state.program_input = ""
    reset_results()


def load_sample():
    st.session_state.python_code = SAMPLES[st.session_state.sample_choice]
    reset_results()


def apply_correction():
    candidate = st.session_state.suggested_code
    if candidate:
        st.session_state.python_code = candidate
    reset_results()


def explain_syntax_error(error):
    message = (error.msg or "Invalid Python syntax").lower()
    explanations = (
        ("expected ':'", "Add a colon (:) at the end of the if, for, while, "
         "def, class, or other block header."),
        ("was never closed", "A parenthesis, square bracket, or brace was "
         "opened but not closed."),
        ("unexpected indent", "This line is indented more than Python expects. "
         "Align it with the surrounding block."),
        ("expected an indented block", "Python expects the next statement to "
         "be indented beneath this block header."),
        ("unterminated string", "A string is missing its matching closing "
         "quote."),
        ("unmatched", "A closing bracket or parenthesis has no matching opener."),
    )
    for fragment, explanation in explanations:
        if fragment in message:
            return explanation
    return (
        "Python could not parse this statement. Check the indicated line for "
        "misspelled keywords, missing punctuation, or incorrectly placed "
        "quotes and brackets."
    )


def explain_static_warning(message):
    lowered = message.lower()
    if "undefined name" in lowered:
        return (
            "This name is used but was not defined in the current scope. "
            "Check its spelling and make sure it is assigned or imported first."
        )
    if "assigned to but never used" in lowered:
        return (
            "A value is assigned but never read. This may be harmless, but "
            "check whether a later statement is missing."
        )
    if "imported but unused" in lowered:
        return (
            "This import is not used. Remove it if it is unnecessary, or check "
            "whether the intended code is missing."
        )
    if "redefinition" in lowered:
        return (
            "A name is defined more than once in this scope. Check whether "
            "the later definition replaces the earlier one unintentionally."
        )
    return "Review this static-analysis warning; it may indicate a beginner mistake."


def explain_runtime_error(stderr):
    exception_line = ""
    for line in reversed(stderr.splitlines()):
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*(Error|Exception):", line.strip()):
            exception_line = line.strip()
            break
    if not exception_line:
        return "The program ended unsuccessfully. Review the traceback for details."

    exception_name = exception_line.split(":", 1)[0]
    explanations = {
        "NameError": "A variable or function name was not found. Check spelling "
        "and define it before use.",
        "TypeError": "An operation received a value of an incompatible type. "
        "Check the types before combining or calling values.",
        "IndexError": "A sequence index is outside the available range. Check "
        "the sequence length before indexing it.",
        "KeyError": "A dictionary key does not exist. Check the key spelling or "
        "use a safe lookup when the key is optional.",
        "ValueError": "A value has the right general type but is not accepted "
        "here. Check conversions and allowed values.",
        "ZeroDivisionError": "The program tried to divide by zero. Check the "
        "denominator before dividing.",
        "ModuleNotFoundError": "A module could not be imported. Check its name "
        "and whether it is installed in this Python environment.",
        "FileNotFoundError": "A requested file or folder could not be found. "
        "Check the path and current working directory.",
        "EOFError": "The program requested input, but no input value was "
        "available. Enter the required values in the Program Input box.",
        "IndentationError": "A block is not indented consistently. Check the "
        "lines beneath if, for, while, def, and similar statements.",
    }
    return explanations.get(
        exception_name,
        f"{exception_name}: {exception_line.partition(':')[2].strip()}",
    )


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def execute_code(code, user_input="", timeout=5):
    started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="codefix_") as temp_dir:
            file_path = os.path.join(temp_dir, "program.py")
            with open(file_path, "w", encoding="utf-8") as source_file:
                source_file.write(code)

            process = subprocess.run(
                [sys.executable, "-I", file_path],
                input=user_input,
                capture_output=True,
                text=True,
                cwd=temp_dir,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return {
                "success": process.returncode == 0,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "returncode": process.returncode,
                "time": round(time.perf_counter() - started, 4),
                "timeout": False,
            }
    except subprocess.TimeoutExpired as error:
        return {
            "success": False,
            "stdout": _as_text(error.stdout),
            "stderr": "Execution stopped because it exceeded the time limit.",
            "returncode": -1,
            "time": round(time.perf_counter() - started, 4),
            "timeout": True,
        }
    except OSError as error:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Could not start or write the Python program: {error}",
            "returncode": -1,
            "time": round(time.perf_counter() - started, 4),
            "timeout": False,
        }


def analyze_code(code, user_input="", timeout=5):
    result = {
        "syntax_ok": True,
        "syntax": "No syntax errors found.",
        "syntax_explanation": "",
        "static": [],
        "execution": None,
    }
    try:
        ast.parse(code)
    except SyntaxError as error:
        result["syntax_ok"] = False
        result["syntax"] = (
            f"{error.msg} at line {error.lineno or '?'}, "
            f"column {error.offset or '?'}"
        )
        result["syntax_explanation"] = explain_syntax_error(error)
        return result

    if pyflakes is not None:
        output = io.StringIO()
        reporter = pyflakes.reporter.Reporter(output, output)
        pyflakes.api.check(code, "<CodeFix AI>", reporter)
        result["static"] = [
            line for line in output.getvalue().splitlines() if line.strip()
        ]

    result["execution"] = execute_code(code, user_input, timeout)
    return result


def find_open_brackets(code):
    opening_to_closing = {"(": ")", "[": "]", "{": "}"}
    stack = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        for token in tokens:
            if token.type != tokenize.OP:
                continue
            if token.string in opening_to_closing:
                stack.append(token.string)
            elif token.string in (")", "]", "}"):
                if stack and opening_to_closing[stack[-1]] == token.string:
                    stack.pop()
    except (tokenize.TokenError, IndentationError):
        pass
    return stack, opening_to_closing


def basic_syntax_fix(code):
    candidate = code
    for _ in range(10):
        try:
            ast.parse(candidate)
            return candidate
        except SyntaxError as error:
            message = (error.msg or "").lower()
            lines = candidate.splitlines()
            if "expected ':'" in message and error.lineno:
                index = error.lineno - 1
                if index >= len(lines) or lines[index].rstrip().endswith(":"):
                    return None
                lines[index] = lines[index].rstrip() + ":"
                candidate = "\n".join(lines)
                continue
            if "was never closed" in message:
                stack, opening_to_closing = find_open_brackets(candidate)
                if not stack:
                    return None
                missing = "".join(
                    opening_to_closing[bracket] for bracket in reversed(stack)
                )
                candidate = candidate.rstrip() + missing + "\n"
                continue
            return None
    try:
        ast.parse(candidate)
        return candidate
    except SyntaxError:
        return None


def extract_code(response):
    match = re.search(
        r"```(?:python|py)?\s*(.*?)```",
        response.strip(),
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else response.strip()


def ask_local_ai(code, problem, model, ollama_url):
    prompt = f"""You are a Python debugging assistant.
Return the complete corrected Python program only.
Preserve the program's purpose and existing features. Fix the reported problem
without replacing the program with an unrelated example. Do not invent output.

Problem:
{problem}

Original program:
{code}
"""
    response = requests.post(
        ollama_url.rstrip("/") + "/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("response"), str):
        raise ValueError("Ollama returned an unexpected response.")
    return extract_code(data["response"])


def validate_candidate(candidate, original_code, user_input, timeout):
    if not candidate.strip():
        return None, "The correction was empty."
    if candidate.strip() == original_code.strip():
        return None, "The proposed correction did not change the original code."
    try:
        compile(candidate, "<CodeFix AI corrected code>", "exec")
    except SyntaxError as error:
        return None, (
            f"The proposed code has a syntax error on line {error.lineno}: "
            f"{error.msg}"
        )

    execution = execute_code(candidate, user_input, timeout)
    if not execution["success"]:
        reason = (
            "The proposed code did not finish successfully with the current "
            "Program Input."
        )
        if execution["timeout"]:
            reason = "The proposed code exceeded the execution time limit."
        elif execution["stderr"]:
            reason += " " + explain_runtime_error(execution["stderr"])
        return None, reason
    return execution, ""


def describe_problem(analysis):
    problems = []
    if not analysis["syntax_ok"]:
        problems.append(
            "Syntax error: "
            + analysis["syntax"]
            + " "
            + analysis["syntax_explanation"]
        )
        return "\n".join(problems)

    execution = analysis["execution"]
    if execution and not execution["success"]:
        runtime_description = (
            "The original program exceeded the time limit."
            if execution["timeout"]
            else explain_runtime_error(execution["stderr"])
        )
        problems.append(
            "Runtime failure: "
            + runtime_description
            + "\nTraceback/output:\n"
            + execution["stderr"]
        )
    if analysis["static"]:
        problems.append(
            "Static-analysis warnings:\n" + "\n".join(analysis["static"])
        )
    return "\n\n".join(problems)


def correct_program(code, problem, model, ollama_url, user_input, timeout):
    basic_candidate = basic_syntax_fix(code)
    if basic_candidate and basic_candidate.strip() != code.strip():
        execution, reason = validate_candidate(
            basic_candidate, code, user_input, timeout
        )
        if execution:
            return (
                basic_candidate,
                execution,
                "A safe syntax correction passed syntax and execution "
                "validation with the current input.",
                "",
            )

    try:
        candidate = ask_local_ai(code, problem, model, ollama_url)
    except (requests.RequestException, ValueError) as error:
        details = f"Local AI correction was unavailable: {error}"
        if basic_candidate and basic_candidate.strip() != code.strip():
            return None, None, (
                details
                + " The basic syntax suggestion did not pass execution "
                "validation."
            ), details
        return None, None, details, details

    execution, reason = validate_candidate(
        candidate, code, user_input, timeout
    )
    if not execution:
        return (
            None,
            None,
            "A correction was generated but not shown because validation "
            f"failed: {reason}",
            reason,
        )
    return (
        candidate,
        execution,
        "The proposed correction passed syntax validation and executed "
        "successfully with the current Program Input. Review it before use; "
        "this does not prove that its logic matches every intended outcome.",
        "",
    )


def add_history(action, success):
    st.session_state.history.append(
        {
            "action": action,
            "success": success,
            "time": time.strftime("%H:%M:%S"),
        }
    )
    st.session_state.history = st.session_state.history[-50:]


st.sidebar.title("⚙️ Settings")
ollama_url = st.sidebar.text_input(
    "Ollama address",
    value="http://localhost:11434",
)
model = st.sidebar.text_input(
    "Local AI model",
    value="qwen2.5-coder:3b",
)
timeout = st.sidebar.slider(
    "Execution time limit (seconds)",
    min_value=1,
    max_value=30,
    value=5,
)
st.sidebar.divider()
st.sidebar.write("**CodeFix AI tools**")
st.sidebar.write("🐍 Python execution")
st.sidebar.write("🔍 Syntax, Pyflakes, and runtime checks")
st.sidebar.write("🧠 Optional Ollama-assisted correction")
st.sidebar.caption(
    "AI Auto Fix sends the code to the Ollama address above. Use an endpoint "
    "you trust. A local Ollama installation is recommended."
)


st.divider()
st.subheader("1. Load a Sample Program")
st.selectbox(
    "Choose a Python program",
    list(SAMPLES),
    key="sample_choice",
)
st.button(
    "📂 Load Sample",
    on_click=load_sample,
    use_container_width=True,
)

st.divider()
st.subheader("2. Python Code Editor")
st.text_area(
    "Write or paste your Python code:",
    key="python_code",
    height=400,
    placeholder="Enter your Python program here...",
    on_change=reset_results,
)
st.download_button(
    "⬇️ Download Original Code",
    data=st.session_state.python_code,
    file_name="program.py",
    mime="text/x-python",
    use_container_width=True,
)

st.subheader("3. Program Input")
st.write(
    "Enter values requested by input(), with one value on each line. "
    "Use the same input for the original and proposed corrected program."
)
st.text_area(
    "Input values",
    key="program_input",
    height=100,
    placeholder="Example:\nSaru\n20",
    on_change=reset_results,
)

st.divider()
run_column, detect_column, fix_column = st.columns(3)
with run_column:
    run_button = st.button("▶️ Run Code", use_container_width=True)
with detect_column:
    detect_button = st.button("🔍 Detect Errors", use_container_width=True)
with fix_column:
    fix_button = st.button("🧠 AI Auto Fix", use_container_width=True)
st.button(
    "🗑️ Clear Code",
    on_click=clear_editor,
    use_container_width=True,
)


if run_button:
    reset_results()
    code = st.session_state.python_code
    if not code.strip():
        st.warning("Please enter Python code first.")
    else:
        st.session_state.execution_result = execute_code(
            code, st.session_state.program_input, timeout
        )
        add_history("Run Code", st.session_state.execution_result["success"])

if detect_button:
    reset_results()
    code = st.session_state.python_code
    if not code.strip():
        st.warning("Please enter Python code first.")
    else:
        with st.spinner("Checking syntax, common mistakes, and runtime behavior..."):
            st.session_state.analysis_result = analyze_code(
                code, st.session_state.program_input, timeout
            )
        analysis = st.session_state.analysis_result
        add_history(
            "Detect Errors",
            analysis["syntax_ok"]
            and analysis["execution"] is not None
            and analysis["execution"]["success"]
            and not analysis["static"],
        )

if fix_button:
    reset_results()
    code = st.session_state.python_code
    if not code.strip():
        st.warning("Please enter Python code first.")
    else:
        with st.spinner("Analyzing the program and validating a correction..."):
            analysis = analyze_code(
                code, st.session_state.program_input, timeout
            )
            st.session_state.analysis_result = analysis
            st.session_state.execution_result = analysis["execution"]
            problem = describe_problem(analysis)
            if not problem:
                st.session_state.fix_message = (
                    "No syntax or runtime error was detected for the current "
                    "input. The code has not been changed."
                )
            else:
                (
                    candidate,
                    candidate_execution,
                    message,
                    _,
                ) = correct_program(
                    code,
                    problem,
                    model,
                    ollama_url,
                    st.session_state.program_input,
                    timeout,
                )
                st.session_state.suggested_code = candidate
                st.session_state.suggested_execution = candidate_execution
                st.session_state.fix_message = message
        add_history(
            "AI Auto Fix",
            bool(st.session_state.suggested_code),
        )


analysis = st.session_state.analysis_result
if analysis:
    st.divider()
    st.subheader("4. Error Detection Results")
    if analysis["syntax_ok"]:
        st.success(analysis["syntax"])
    else:
        st.error(analysis["syntax"])
        st.info(analysis["syntax_explanation"])

    if analysis["static"]:
        st.write("**Static-analysis findings**")
        for warning in analysis["static"]:
            st.warning(warning)
            st.caption(explain_static_warning(warning))
    elif pyflakes is None:
        st.info(
            "Pyflakes is unavailable in this Python environment. Syntax and "
            "runtime checks are still available."
        )
    elif analysis["syntax_ok"]:
        st.success("No Pyflakes warnings found.")

    if analysis["execution"] and not analysis["execution"]["success"]:
        execution = analysis["execution"]
        if execution["timeout"]:
            st.warning("Runtime check stopped at the time limit.")
        else:
            st.error("Runtime error detected.")
            st.info(explain_runtime_error(execution["stderr"]))
        if execution["stderr"]:
            st.code(execution["stderr"])


if st.session_state.execution_result:
    result = st.session_state.execution_result
    st.divider()
    st.subheader("5. Original Program Output")
    if result["success"]:
        st.success("Original program executed successfully.")
    elif result["timeout"]:
        st.warning("Original program stopped at the time limit.")
    else:
        st.error("Original program execution failed.")
    if result["stdout"]:
        st.code(result["stdout"])
    else:
        st.info("The original program produced no output.")
    if result["stderr"]:
        st.write("**Original error / traceback**")
        st.code(result["stderr"])
    st.caption(
        f"Return code: {result['returncode']} | "
        f"Execution time: {result['time']} seconds"
    )


if st.session_state.fix_message:
    st.divider()
    st.subheader("6. Proposed Corrected Code")
    st.write(st.session_state.fix_message)
    candidate = st.session_state.suggested_code
    if candidate:
        st.success(
            "This code passed Python syntax validation and execution with the "
            "current input."
        )
        st.code(candidate, language="python")
        st.download_button(
            "⬇️ Download Corrected Code",
            data=candidate,
            file_name="corrected_program.py",
            mime="text/x-python",
            use_container_width=True,
        )
        st.button(
            "✅ Replace Original Code with Correction",
            on_click=apply_correction,
            use_container_width=True,
        )

        corrected_result = st.session_state.suggested_execution
        if corrected_result:
            st.divider()
            st.subheader("7. Corrected Program Output")
            st.success(
                "Corrected program executed successfully with the current input."
            )
            if corrected_result["stdout"]:
                st.code(corrected_result["stdout"])
            else:
                st.info("The corrected program produced no output.")
            if corrected_result["stderr"]:
                st.code(corrected_result["stderr"])
            st.caption(
                f"Execution time: {corrected_result['time']} seconds"
            )


st.divider()
with st.expander("📜 Recent Activity"):
    if st.session_state.history:
        for item in reversed(st.session_state.history[-10:]):
            status = "Success" if item["success"] else "Needs attention"
            st.write(f"{item['time']} | {item['action']} | {status}")
    else:
        st.write("No activity yet.")

st.divider()
st.subheader("About CodeFix AI")
language_column, analysis_column, ai_column = st.columns(3)
language_column.metric("Language", "Python")
analysis_column.metric("Analysis", "AST + Pyflakes + runtime")
ai_column.metric("Optional AI", "Ollama")
st.caption(
    "CodeFix AI — Beginner Code Error Detection and Explanation System"
)
