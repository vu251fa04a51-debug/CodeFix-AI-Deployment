import ast
import re
import streamlit as st

st.set_page_config(
    page_title="CodeFix AI",
    page_icon="🐞",
    layout="wide"
)

# ---------------- SAMPLE PROGRAMS ----------------

SAMPLES = {
    "Select a sample": "",
    "Correct Python Code": '''name = "Saraswathi"
age = 20

print("Student Details")
print("Name:", name)
print("Age:", age)
''',
    "Missing Parenthesis": '''name = "Saraswathi"
print("Hello", name
''',
    "Missing Colon": '''age = 20

if age >= 18
    print("Eligible to vote")
''',
    "Incorrect Indentation": '''def greet():
print("Hello Student")
print("Welcome to CodeFix AI")
''',
    "Missing Quotation Mark": '''name = "Saraswathi
print("Hello", name)
''',
    "Extra Parenthesis": '''print("Hello Student"))
''',
    "Student Management System": '''students = [
    {"name": "Ravi", "marks": 85},
    {"name": "Sita", "marks": 92},
    {"name": "John", "marks": 78}
]

def display_students():
    print("STUDENT DETAILS")
    for student in students:
        print("Name:", student["name"])
        print("Marks:", student["marks"])

def add_student(name, marks):
    students.append({"name": name, "marks": marks)

def main():
    display_students()
    add_student("Priya", 95)
    display_students()

if __name__ == "__main__":
    main()
'''
}

# ---------------- ERROR EXPLANATION ----------------

def explain_error(error):
    message = error.msg.lower()

    if "was never closed" in message:
        return "A bracket or parenthesis is missing. Add the required closing symbol."

    if "expected ':'" in message:
        return "A colon is missing after an if, else, for, while, class, or function statement."

    if "expected an indented block" in message:
        return "The statement inside this block must be indented."

    if "unexpected indent" in message:
        return "This line has unnecessary indentation."

    if "unindent does not match" in message:
        return "The indentation level does not match the previous block."

    if "unterminated string" in message:
        return "A string is missing its closing quotation mark."

    if "unmatched ')'" in message:
        return "There is an extra closing parenthesis."

    if "invalid syntax" in message:
        return "Python syntax is incorrect on or near this line."

    return error.msg


# ---------------- AUTOMATIC CORRECTION ----------------

def fix_one_error(code, error):
    lines = code.splitlines()

    line_number = error.lineno

    if not line_number or line_number > len(lines):
        return None

    index = line_number - 1
    line = lines[index]
    message = error.msg.lower()

    # Fix malformed function definition: def display(: -> def display():
    if re.match(r'^\s*def\s+\w+\s*\(\s*:\s*$', line):
        indentation = re.match(r'^\s*', line).group()
        name = re.search(r'def\s+(\w+)', line).group(1)
        lines[index] = indentation + "def " + name + "():"
        return "\n".join(lines)

    # Fix missing colon
    if "expected ':'" in message:
        if line.rstrip().endswith(":"):
            return None

        lines[index] = line.rstrip() + ":"
        return "\n".join(lines)

    # Fix missing closing parenthesis
    if "was never closed" in message:
        if line.count("(") > line.count(")"):
            lines[index] = line + ")"
            return "\n".join(lines)

        if line.count("[") > line.count("]"):
            lines[index] = line + "]"
            return "\n".join(lines)

        if line.count("{") > line.count("}"):
            lines[index] = line + "}"
            return "\n".join(lines)

    # Fix extra closing parenthesis
    if "unmatched ')'" in message:
        if ")" in line:
            position = line.rfind(")")
            lines[index] = line[:position] + line[position + 1:]
            return "\n".join(lines)

    # Fix missing quotation mark
    if "unterminated string" in message:
        quote = '"'
        if line.count('"') % 2 == 1:
            lines[index] = line + '"'
            return "\n".join(lines)

        if line.count("'") % 2 == 1:
            lines[index] = line + "'"
            return "\n".join(lines)

    # Fix incorrect indentation
    if "expected an indented block" in message:
        if index + 1 < len(lines):
            if lines[index + 1].strip():
                lines[index + 1] = "    " + lines[index + 1].lstrip()
                return "\n".join(lines)

    if "unexpected indent" in message:
        indentation = len(line) - len(line.lstrip())
        if indentation >= 4:
            lines[index] = line[4:]
            return "\n".join(lines)

    if "unindent does not match" in message:
        indentation = len(line) - len(line.lstrip())
        if indentation > 0:
            lines[index] = " " * (indentation - indentation % 4) + line.lstrip()
            return "\n".join(lines)

    return None


def auto_correct(code):
    corrected = code
    changes = 0

    # Correct one syntax error at a time.
    for attempt in range(10):
        try:
            ast.parse(corrected)
            return corrected, changes, True

        except SyntaxError as error:
            new_code = fix_one_error(corrected, error)

            if not new_code or new_code == corrected:
                return corrected, changes, False

            corrected = new_code
            changes += 1

    try:
        ast.parse(corrected)
        return corrected, changes, True
    except SyntaxError:
        return corrected, changes, False


# ---------------- SESSION STATE ----------------

if "python_code" not in st.session_state:
    st.session_state.python_code = ""

if "result" not in st.session_state:
    st.session_state.result = None

if "corrected_code" not in st.session_state:
    st.session_state.corrected_code = None

if "correction_valid" not in st.session_state:
    st.session_state.correction_valid = False


def load_sample():
    selected = st.session_state.sample_choice
    st.session_state.python_code = SAMPLES[selected]
    st.session_state.result = None
    st.session_state.corrected_code = None


def clear_code():
    st.session_state.python_code = ""
    st.session_state.result = None
    st.session_state.corrected_code = None
    st.session_state.correction_valid = False


def use_correction():
    if st.session_state.correction_valid:
        st.session_state.python_code = st.session_state.corrected_code
        st.session_state.result = None
        st.session_state.corrected_code = None
        st.session_state.correction_valid = False


# ---------------- MAIN INTERFACE ----------------

st.title("🐞 CodeFix AI")
st.subheader("Beginner Code Error Detection and Explanation System")

st.write(
    "Enter your Python code below. CodeFix AI detects common "
    "syntax errors, explains them, and suggests validated corrections."
)

st.info(
    "This version checks Python syntax using AST and predefined "
    "correction rules. It does not guarantee correction of every error."
)

# Sample selection
st.subheader("Load Sample Code")

st.selectbox(
    "Choose a sample program",
    list(SAMPLES.keys()),
    key="sample_choice"
)

st.button(
    "Load Sample",
    on_click=load_sample,
    use_container_width=True
)

# Code editor
st.subheader("Python Code Editor")

st.text_area(
    "Enter or edit your Python code:",
    key="python_code",
    height=350,
    placeholder="Write your Python code here..."
)

# Buttons
col1, col2 = st.columns(2)

with col1:
    detect_button = st.button(
        "🔍 Detect Errors",
        use_container_width=True
    )

with col2:
    st.button(
        "🗑️ Clear Code",
        on_click=clear_code,
        use_container_width=True
    )

# ---------------- DETECTION ----------------

if detect_button:
    code = st.session_state.python_code

    st.session_state.result = None
    st.session_state.corrected_code = None
    st.session_state.correction_valid = False

    if not code.strip():
        st.warning("Please enter Python code first.")

    else:
        try:
            ast.parse(code)

            st.session_state.result = {
                "status": "success"
            }

        except SyntaxError as error:
            corrected, changes, valid = auto_correct(code)

            st.session_state.result = {
                "status": "error",
                "line": error.lineno,
                "message": error.msg,
                "explanation": explain_error(error),
                "changes": changes,
                "valid": valid
            }

            if valid and corrected != code:
                st.session_state.corrected_code = corrected
                st.session_state.correction_valid = True


# ---------------- DISPLAY RESULTS ----------------

if st.session_state.result:

    result = st.session_state.result

    if result["status"] == "success":

        st.success("✅ No Python syntax errors found!")

        st.write(
            "Your code passed Python's syntax check. "
            "This does not guarantee that the program's logic is correct."
        )

    else:

        st.error("❌ Syntax Error Detected")

        st.write("**Error line:**", result["line"])

        st.write("**Error message:**", result["message"])

        st.write("**Explanation:**", result["explanation"])

        st.divider()

        st.subheader("🛠️ Suggested Correction")

        if result["valid"]:

            st.success(
                "A corrected version was generated and passed "
                "Python syntax validation."
            )

            st.write(
                "Number of automatic correction steps:",
                result["changes"]
            )

            st.code(
                st.session_state.corrected_code,
                language="python"
            )

            st.button(
                "✅ Use Corrected Code",
                on_click=use_correction,
                use_container_width=True
            )

        else:

            st.warning(
                "A complete safe correction could not be generated. "
                "The original code has been preserved."
            )

            if result["changes"] > 0:
                st.write(
                    "Some correction steps were attempted, "
                    "but the resulting code did not pass validation."
                )

            st.write(
                "Please correct the remaining error manually "
                "and click Detect Errors again."
            )


# ---------------- PROJECT INFORMATION ----------------

st.divider()

st.subheader("About CodeFix AI")

col1, col2, col3 = st.columns(3)

col1.metric("Language", "Python")
col2.metric("Syntax Analysis", "AST")
col3.metric("Interface", "Streamlit")

st.caption(
    "CodeFix AI is a beginner-friendly syntax error detection "
    "and correction support tool."
)