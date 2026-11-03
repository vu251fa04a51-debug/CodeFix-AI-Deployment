
import ast
import io
import re
import sys
import tokenize
import subprocess
import difflib
import streamlit as st


# ---------------------------------------
# PAGE SETTINGS
# ---------------------------------------

st.set_page_config(
    page_title="CodeFix AI",
    page_icon="🐞",
    layout="wide"
)


# ---------------------------------------
# SESSION STATE
# ---------------------------------------

if "python_code" not in st.session_state:
    st.session_state.python_code = ""

if "corrected_code" not in st.session_state:
    st.session_state.corrected_code = ""

if "corrections" not in st.session_state:
    st.session_state.corrections = []

if "remaining_error" not in st.session_state:
    st.session_state.remaining_error = None

if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False


# ---------------------------------------
# CHECK PYTHON SYNTAX
# ---------------------------------------

def check_code(code):
    try:
        ast.parse(code)
        return None
    except SyntaxError as error:
        return error


# ---------------------------------------
# FIND UNMATCHED BRACKETS
# ---------------------------------------

def find_open_brackets(code):

    opening = {
        "(": ")",
        "[": "]",
        "{": "}"
    }

    stack = []

    try:
        tokens = tokenize.generate_tokens(
            io.StringIO(code).readline
        )

        for token in tokens:
            if token.type == tokenize.OP:

                if token.string in opening:
                    stack.append(
                        (token.string, token.start)
                    )

                elif token.string in [")", "]", "}"]:

                    if stack:
                        last = stack[-1][0]

                        if opening[last] == token.string:
                            stack.pop()

    except (tokenize.TokenError, IndentationError):
        pass

    return stack, opening


# ---------------------------------------
# AUTOMATIC SYNTAX CORRECTION
# ---------------------------------------

def auto_correct(code):

    corrected = code
    corrections = []

    for attempt in range(30):

        error = check_code(corrected)

        if error is None:
            return corrected, corrections, None

        lines = corrected.splitlines()
        message = (error.msg or "").lower()
        line_number = error.lineno or 1

        candidate = None
        correction_message = ""

        # 1. FIX MISSING COLON FIRST

        if "expected ':'" in message:

            index = line_number - 1

            if 0 <= index < len(lines):

                line = lines[index]

                if not line.rstrip().endswith(":"):

                    lines[index] = line.rstrip() + ":"
                    candidate = "\n".join(lines)

                    correction_message = (
                        f"Added missing colon at line {line_number}."
                    )

        # 2. FIX MISSING CLOSING BRACKETS

        if candidate is None:

            stack, closing = find_open_brackets(corrected)

            if stack:

                missing_brackets = [
                    closing[item[0]]
                    for item in reversed(stack)
                ]

                candidate = (
                    corrected.rstrip()
                    + "".join(missing_brackets)
                    + "\n"
                )

                correction_message = (
                    "Added missing closing bracket(s)."
                )

        # 3. STOP IF NO SAFE FIX IS FOUND

        if candidate is None or candidate == corrected:
            break

        new_error = check_code(candidate)

        # Accept a correction if syntax is fixed.

        if new_error is None:

            corrected = candidate
            corrections.append(correction_message)

            return corrected, corrections, None

        # Continue if the parser has moved to another error.

        if (
            new_error.msg != error.msg
            or new_error.lineno != error.lineno
        ):

            corrected = candidate
            corrections.append(correction_message)
            continue

        break

    final_error = check_code(corrected)

    return corrected, corrections, final_error


# ---------------------------------------
# CHECK UNDEFINED NAMES USING PYFLAKES
# ---------------------------------------

def check_name_errors(code):

    try:
        from pyflakes.api import check
        from pyflakes.reporter import Reporter

        output = io.StringIO()
        reporter = Reporter(output, output)

        check(code, "<user_code>", reporter)

        return output.getvalue().strip()

    except ImportError:
        return "Pyflakes is not installed. Install it to check undefined names."

    except Exception as error:
        return f"Name checking could not be completed: {error}"


# ---------------------------------------
# ANALYZE CODE
# ---------------------------------------

def analyze_code(code):

    corrected, corrections, remaining_error = auto_correct(code)

    return corrected, corrections, remaining_error


# ---------------------------------------
# CLEAR BUTTON CALLBACK
# ---------------------------------------

def clear_code():

    st.session_state.python_code = ""
    st.session_state.corrected_code = ""
    st.session_state.corrections = []
    st.session_state.remaining_error = None
    st.session_state.analysis_done = False


# ---------------------------------------
# LOAD SAMPLE CALLBACK
# ---------------------------------------

def load_sample():

    st.session_state.python_code = '''students = [
    {"name": "Ravi", "marks": 85},
    {"name": "Sita", "marks": 92},
    {"name": "Ram", "marks": 78}
]

def display_students():
    for student in students:
        print("Name:", student["name"])
        print("Marks:", student["marks"])

if __name__ == "__main__":
    display_students()
    print("Total Students:", len(students)
'''

    st.session_state.corrected_code = ""
    st.session_state.corrections = []
    st.session_state.remaining_error = None
    st.session_state.analysis_done = False


# ---------------------------------------
# APPLICATION TITLE
# ---------------------------------------

st.title("🐞 CodeFix AI")

st.subheader(
    "Beginner Code Error Detection and Explanation System"
)

st.write(
    "Enter your Python code below. "
    "CodeFix AI checks for syntax errors, "
    "attempts supported automatic corrections, "
    "and lets you run the corrected code."
)

st.divider()


# ---------------------------------------
# CODE INPUT
# ---------------------------------------

st.subheader("📝 Enter Your Python Code")

code = st.text_area(
    "Python Code Editor",
    key="python_code",
    height=300,
    placeholder="Write or paste your Python code here..."
)


# ---------------------------------------
# BUTTONS
# ---------------------------------------

col1, col2, col3 = st.columns(3)

with col1:

    analyze_button = st.button(
        "🔍 Detect & Fix Errors",
        use_container_width=True
    )

with col2:

    st.button(
        "🧹 Clear Code",
        on_click=clear_code,
        use_container_width=True
    )

with col3:

    st.button(
        "📌 Load Sample",
        on_click=load_sample,
        use_container_width=True
    )


# ---------------------------------------
# PROCESS CODE
# ---------------------------------------

if analyze_button:

    entered_code = st.session_state.python_code

    if not entered_code.strip():

        st.warning("Please enter some Python code first.")

    else:

        corrected, corrections, remaining_error = analyze_code(
            entered_code
        )

        st.session_state.corrected_code = corrected
        st.session_state.corrections = corrections
        st.session_state.remaining_error = remaining_error
        st.session_state.analysis_done = True


# ---------------------------------------
# DISPLAY RESULTS
# ---------------------------------------

if st.session_state.analysis_done:

    st.divider()
    st.header("📊 Analysis Results")

    original_code = st.session_state.python_code
    corrected_code = st.session_state.corrected_code
    corrections = st.session_state.corrections
    remaining_error = st.session_state.remaining_error

    if not corrections and remaining_error is None:

        st.success("No syntax errors found! Your code is valid.")

    elif corrections:

        st.success(
            f"Successfully applied {len(corrections)} correction(s)."
        )

        st.subheader("✅ Corrections Made")

        for number, correction in enumerate(corrections, start=1):

            st.write(f"{number}. {correction}")

    if remaining_error is not None:

        st.error("Some syntax errors could not be corrected safely.")

        st.write(
            f"Error type: {type(remaining_error).__name__}"
        )

        st.write(
            f"Line number: {remaining_error.lineno}"
        )

        st.write(
            f"Explanation: {remaining_error.msg}"
        )

        st.info(
            "The original code has been preserved. "
            "This error needs further review."
        )

    # -----------------------------------
    # CORRECTED CODE
    # -----------------------------------

    st.subheader("💡 Corrected Python Code")

    st.code(
        corrected_code,
        language="python"
    )

    st.download_button(
        label="⬇️ Download Corrected Code",
        data=corrected_code,
        file_name="corrected_code.py",
        mime="text/x-python",
        use_container_width=True
    )

    # -----------------------------------
    # NAME ERROR CHECK
    # -----------------------------------

    if remaining_error is None:

        st.subheader("🔎 Additional Code Check")

        name_results = check_name_errors(corrected_code)

        if not name_results:

            st.success(
                "No undefined-name warnings reported by Pyflakes."
            )

        else:

            st.warning("Additional code warnings:")

            st.code(name_results)

    # -----------------------------------
    # RUN CORRECTED CODE
    # -----------------------------------

    st.divider()
    st.subheader("▶️ Run Corrected Code")

    if remaining_error is None:

        if st.button(
            "Run Program",
            use_container_width=True
        ):

            try:

                result = subprocess.run(
                    [sys.executable, "-I", "-c", corrected_code],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if result.stdout:

                    st.success("Program executed.")

                    st.subheader("📤 Program Output")

                    st.code(result.stdout)

                if result.stderr:

                    st.error("Runtime error or warning")

                    st.code(result.stderr)

                if (
                    not result.stdout
                    and not result.stderr
                    and result.returncode == 0
                ):

                    st.info("Program executed successfully with no output.")

            except subprocess.TimeoutExpired:

                st.error(
                    "Program stopped because it exceeded the 5-second limit."
                )

            except Exception as error:

                st.error(f"Execution failed: {error}")

    else:

        st.info(
            "Fix the remaining syntax error before running the program."
        )


# ---------------------------------------
# FOOTER
# ---------------------------------------

st.divider()

st.caption(
    "CodeFix AI | Beginner Python Error Detection and Explanation System"
)

st.caption(
    "Note: Automatic correction supports selected syntax mistakes. "
    "It cannot guarantee correction of every Python error. "
    "Only run code you trust."
)
