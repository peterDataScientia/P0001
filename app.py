"""P0001 manuscript PDF viewer for Streamlit Community Cloud.

The app builds the checked-in LaTeX documents with a local pdfLaTeX executable.
No GitHub token, shell escape, user code execution, or external PDF service is used.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent
DOCUMENTS = {
    "Manuscript": "main.tex",
    "Supplementary information": "supp.tex",
}

st.set_page_config(
    page_title="P0001 | Manuscript PDF",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


def source_fingerprint(source_file: str) -> str:
    """Change the compilation cache whenever source or figure content changes."""
    tex_path = ROOT / source_file
    digest = hashlib.sha256()
    digest.update(tex_path.read_bytes())
    if source_file == "main.tex":
        figures_dir = ROOT / "prism-uploads"
        if figures_dir.exists():
            for path in sorted(figures_dir.rglob("*")):
                if path.is_file():
                    digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
                    digest.update(path.read_bytes())
    return digest.hexdigest()


@st.cache_data(show_spinner=False)
def compile_pdf(source_file: str, source_signature: str) -> tuple[bytes | None, str]:
    """Compile a trusted repository document, isolated from the source tree."""
    # source_signature intentionally invalidates st.cache_data on GitHub updates.
    _ = source_signature
    pdflatex = shutil.which("pdflatex")
    if pdflatex is None:
        return None, (
            "pdfLaTeX was not found on this server. Install the TeX Live "
            "packages listed in packages.txt and restart the Streamlit app."
        )

    if source_file not in DOCUMENTS.values() or not (ROOT / source_file).is_file():
        return None, "The selected LaTeX source file does not exist."

    # Use a temporary output directory so auxiliary files do not change the repo.
    with tempfile.TemporaryDirectory(prefix="p0001_latex_") as temporary:
        output_dir = Path(temporary)
        command = [
            pdflatex,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            "-no-shell-escape",
            f"-output-directory={output_dir}",
            source_file,
        ]
        logs: list[str] = []
        for pass_number in (1, 2):
            try:
                finished = subprocess.run(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=120,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                return None, "LaTeX compilation exceeded 120 seconds."
            except OSError as exc:
                return None, f"Unable to start pdfLaTeX: {exc}"

            logs.append(f"--- pdfLaTeX pass {pass_number} ---\n{finished.stdout}\n{finished.stderr}")
            if finished.returncode != 0:
                # The last lines generally show the actionable TeX error.
                return None, "\n\n".join(logs)[-18000:]

        pdf_path = output_dir / (Path(source_file).stem + ".pdf")
        if not pdf_path.is_file() or pdf_path.stat().st_size == 0:
            return None, "pdfLaTeX completed, but did not produce a PDF.\n" + logs[-1][-6000:]
        return pdf_path.read_bytes(), logs[-1][-12000:]


st.title("P0001 · Manuscript PDF")
st.caption("Preview and download PDFs compiled directly from the GitHub LaTeX source.")

with st.sidebar:
    st.header("Document")
    document_label = st.radio("Choose PDF", options=list(DOCUMENTS), index=0)
    source_file = DOCUMENTS[document_label]
    st.caption(f"Source: `{source_file}`")
    if st.button("Recompile PDF", use_container_width=True, type="secondary"):
        compile_pdf.clear()
        st.rerun()
    st.divider()
    st.markdown("**Repository:** [peterDataScientia/P0001](https://github.com/peterDataScientia/P0001)")
    st.caption("Read-only PDF viewer. Edit the LaTeX source in GitHub, then recompile here.")

try:
    signature = source_fingerprint(source_file)
except OSError as exc:
    st.error(f"Cannot read the repository source: {exc}")
    st.stop()

with st.spinner(f"Compiling {source_file} to PDF…"):
    pdf_bytes, compile_log = compile_pdf(source_file, signature)

if pdf_bytes is None:
    st.error("PDF compilation failed. The LaTeX source remains unchanged.")
    with st.expander("Show compiler error", expanded=True):
        st.code(compile_log, language="text")
    st.stop()

left, right = st.columns([3, 1], vertical_alignment="center")
with left:
    st.success(f"{document_label} PDF is ready.")
with right:
    st.download_button(
        "Download PDF",
        data=pdf_bytes,
        file_name=f"P0001_{Path(source_file).stem}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )

# Native built-in Streamlit PDF viewer, not an external tab or third-party iframe.
st.pdf(pdf_bytes, height=1000)

with st.expander("Compilation log"):
    st.code(compile_log, language="text")
