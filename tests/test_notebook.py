"""The notebook has to run.

A notebook is code that nobody executes until somebody else opens it, which is the
worst moment to find out it is broken, so it is executed here instead.

The cells are run in one namespace, in order, exactly as a reader would run them.
Two things are stripped: the install line, because the package is already present,
and the display calls, because there is no notebook front end to draw into.
"""

import json
import pathlib
import re

import pytest

NOTEBOOK = pathlib.Path(__file__).resolve().parents[1] / "notebooks" / "walkthrough.ipynb"
_SKIP = re.compile(r"^\s*(!|%|from IPython|Image\()")


def _code(nb) -> list[str]:
    return ["".join(line for line in cell["source"] if not _SKIP.match(line))
            for cell in nb["cells"] if cell["cell_type"] == "code"]


@pytest.fixture(scope="module")
def notebook():
    return json.loads(NOTEBOOK.read_text())


def test_the_notebook_is_a_notebook(notebook):
    assert notebook["nbformat"] == 4
    assert [c["cell_type"] for c in notebook["cells"]].count("code") >= 8


def test_the_notebook_says_what_it_is_and_is_not(notebook):
    """A reader arriving cold has to be told that the figures are illustrative before
    they read any of them."""
    text = "\n".join("".join(c["source"]) for c in notebook["cells"]
                     if c["cell_type"] == "markdown")
    assert "illustrative" in text.lower()
    assert "one region" in text.lower()


@pytest.mark.slow
def test_the_notebook_runs_end_to_end(notebook, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    namespace: dict = {"__name__": "__main__"}
    for i, source in enumerate(_code(notebook)):
        if not source.strip():
            continue
        try:
            exec(compile(source, f"<cell {i}>", "exec"), namespace)
        except Exception as exc:  # pragma: no cover - the failure is the message
            raise AssertionError(
                f"notebook cell {i} failed: {type(exc).__name__}: {exc}\n\n{source}"
            ) from exc
