"""The notebook has to run.

The gate for the workshop is that the three live exercises run end to end on a
clean machine. A notebook is code that nobody executes until they are standing in
front of a room, which is the worst possible moment to find out, so it is executed
here instead.

The cells are run in one namespace, in order, exactly as a reader would run them.
Two things are stripped: the install line, because the package is already present,
and the display calls, because there is no notebook front end to draw into.
"""

import json
import pathlib
import re

import pytest

NOTEBOOK = pathlib.Path(__file__).resolve().parents[1] / "notebooks" / "exercises.ipynb"
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


def test_every_exercise_is_stated_with_what_should_not_move(notebook):
    """Each exercise says what should move and what should not. An exercise that
    only said what to expect would teach a reader to see it whether or not it
    happened."""
    text = "\n".join("".join(c["source"]) for c in notebook["cells"]
                     if c["cell_type"] == "markdown")
    assert text.count("**Should move:**") >= 3
    assert text.count("**Should not move:**") >= 3
    assert "illustrative" in text.lower() and "not a forecast" in text.lower()


@pytest.mark.slow
def test_the_three_exercises_run_end_to_end(notebook, tmp_path, monkeypatch):
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
