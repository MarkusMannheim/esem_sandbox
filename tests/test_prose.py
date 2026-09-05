"""The documents must not read as machine writing.

The critiques of machine prose name a consistent set of constructions. The objection
is to using them by reflex, everywhere, with no judgement about when one earns its
place, and a model's documentation is the wrong place for that, because the reader is
being asked to weigh whether a claim was measured.

This is a blunt check on the named constructions. It covers the public documents, the
notebook's prose, and the docstrings and comments in the package, because a reader who
follows ARCHITECTURE.md into the code should not cross a line where the voice changes.

When this fails, rewrite the sentence rather than widening the pattern.
"""

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Each pattern is a construction the critiques name, with the plain alternative.
TICS = {
    "negation-antithesis: say the second half and drop the first":
        r"(?i)\bis not [^.,;]{3,40}[.,;] it is\b|\bnot just\b|\bnot merely\b",
    "'worth stating': if it is worth stating, state it":
        r"(?i)\bworth (stating|naming|knowing|pausing|saying|its own|quoting)\b",
    "sentence opening And/But/So for rhythm":
        r"(?m)^\s{0,4}[*_]{0,2}(And|But|So) [a-z]"
        r"|(?<=[.!?])\s+[*_]{0,2}(And|But|So)\s+[a-z]",
    "'that is the point/finding/lesson'":
        r"(?i)\bthat is (the|not a|what) (point|finding|lesson|tell|thing|answer|mistake)\b",
    "'which is exactly'":
        r"(?i)\bwhich is exactly\b",
    "em dash":
        "—",
    "words the critiques flag":
        r"(?i)\b(glimpse into|delve|dive into|stark|seamless|robust solution|tapestry)\b",
}

DOCS = ["README.md", "ARCHITECTURE.md", "KNOWN_LIMITATIONS.md", "GLOSSARY.md",
        "DATA_SOURCES.md", "outputs/canonical/README.md"]


def _sources():
    for name in DOCS:
        yield name, (ROOT / name).read_text()
    nb = json.loads((ROOT / "notebooks" / "walkthrough.ipynb").read_text())
    yield "walkthrough.ipynb", "\n".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown")
    for path in sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "tools").glob("*.py")):
        yield str(path.relative_to(ROOT)), path.read_text()


@pytest.mark.parametrize("tic,pattern", sorted(TICS.items()))
def test_the_prose_does_not_read_as_machine_writing(tic, pattern):
    found = []
    for name, text in _sources():
        for m in re.finditer(pattern, text):
            line = text.count("\n", 0, m.start()) + 1
            excerpt = " ".join(
                text[max(0, m.start() - 50):m.start() + 60].split())
            found.append(f"{name}:{line}  ...{excerpt}...")
    assert not found, (
        f"{len(found)} instance(s) of {tic}:\n  " + "\n  ".join(found[:12])
    )


def test_nothing_is_explained_by_pointing_at_a_model_the_reader_cannot_see():
    """A teaching model cannot define itself by reference to one nobody has read.

    The README once carried a table whose first three rows read "kept as it is" against
    "the same mechanism", for scarcity pricing, contract settlement and the investment
    rule. Those are the three things the whole model rests on, and a new reader was
    told nothing about any of them. The same habit ran through the docstrings.

    Describe the mechanism. If a comparison is useful, it has to say what differs in
    terms the reader already holds.
    """
    import pathlib

    # NAMING the larger model is fine and useful: the README says up front that this
    # is a simplified open version of one, which is why the simplifications are the
    # shape they are. What is banned is EXPLAINING a mechanism by pointing at it, and
    # the tell for that is a description that describes nothing.
    banned = ("kept as it is", "the same mechanism", "model this one simplifies",
              "model it simplifies", "same as the larger", "unchanged from the full")
    root = pathlib.Path(__file__).resolve().parents[1]
    bad = []
    for path in list(root.glob("*.md")) + list((root / "outputs").rglob("*.md")) \
            + list((root / "src").rglob("*.py")) + list((root / "tests").rglob("*.py")) \
            + list((root / "tools").rglob("*.py")) + list(root.glob("notebooks/*.ipynb")):
        if path.resolve() == pathlib.Path(__file__).resolve():
            continue                      # this file necessarily contains the list
        text = path.read_text()
        for phrase in banned:
            if phrase in text:
                bad.append(f"{path.relative_to(root)}: {phrase!r}")
    assert not bad, (
        "these explain something by pointing at a model the reader cannot see, or "
        "describe a mechanism without describing it:\n  " + "\n  ".join(bad)
    )


def test_headings_and_stock_phrases_stay_out_of_the_register():
    """Headings escaped the first sweep, and three tics lived there.

    "The three ideas worth carrying away" is the rule of three and "worth X-ing" in
    one line. "One word of warning about the code's vocabulary" announces a warning
    instead of giving it. "With measurements rather than assertions" is the
    balance-by-template construction. All three read as care and carry nothing.
    """
    import json
    import pathlib
    import re

    banned = [
        (r"(?i)\bworth (carrying|taking) away\b", "just say what it is"),
        (r"(?i)\b(one |a )word of (warning|caution)\b", "give the warning"),
        (r"(?i)\bmeasurements rather than assertions\b", "say the claims are measured"),
        (r"(?i)\bthe (three|four|five) (ideas|things|points|lessons)\b", "rule of three"),
        (r"(?i)\b(three|four|five) \w+ carry (every|the whole|all)\b", "grandiose"),
        (r"(?i)\bcarr(y|ies) every argument\b", "grandiose"),
        (r"(?i)\bit is worth (noting|remembering|saying|pausing)\b", "then note it"),
        (r"(?i)\bat the end of the day\b", "filler"),
        (r"(?i)\binstead of believing\b", "balance template"),
        (r"(?i)\byourself instead of\b", "balance template"),
    ]
    root = pathlib.Path(__file__).resolve().parents[1]
    texts = {}
    for path in list(root.glob("*.md")) + list((root / "outputs").rglob("*.md")):
        texts[path.name] = path.read_text()
    nb = json.loads((root / "notebooks" / "walkthrough.ipynb").read_text())
    texts["walkthrough.ipynb"] = "\n".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown")

    bad = []
    for name, text in texts.items():
        for pattern, why in banned:
            for m in re.finditer(pattern, text):
                line = text[:m.start()].count("\n") + 1
                bad.append(f"{name}:{line} {m.group(0)!r} ({why})")
    assert not bad, "stock phrasing:\n  " + "\n  ".join(bad)


def test_the_limitations_file_counts_its_own_labels_correctly():
    """The opening said "five kinds" while six were defined.

    A count written in prose beside a list it describes is the same defect as a
    measured result hardcoded in source: nothing makes the two move together. This
    reads the labels and checks the sentence against them.
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    text = (root / "KNOWN_LIMITATIONS.md").read_text()
    defined = set(re.findall(r"^- \*\*([a-z]+)\*\* means", text, re.M))
    words = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
    claimed = re.search(r"one of (\w+) kinds", text)
    assert claimed, "the opening no longer says how many kinds there are"
    n = words.get(claimed.group(1))
    assert n == len(defined), (
        f"the opening claims {claimed.group(1)} kinds and {len(defined)} are "
        f"defined: {sorted(defined)}"
    )


def test_no_sentence_announces_a_quality_instead_of_showing_it():
    """The pattern under all the others.

    A sentence that announces a quality instead of demonstrating it says nothing about
    the model. "Every claim in it is measured and the measurement is shown" is a boast
    about rigour. "So you can check the reasoning yourself instead of believing a
    result" flatters the reader about what they are being handed.

    The check is whether deleting the sentence loses anything. Showing the measurement
    demonstrates rigour; saying so asks for credit.
    """
    import json
    import pathlib
    import re

    pattern = re.compile(
        r"(?i)[^.\n]*\b("
        r"every (claim|entry|number|figure|term)[^.\n]*\b(is|are) (measured|shown|defined)|"
        r"rather than (asserted|assumed|authored|invented|named)|"
        r"so (a reader|you) can (check|judge|tell)|"
        r"a reader (should|can) be able to|"
        r"without taking anything on trust|"
        r"which is what you are here to see|"
        r"teaches the wrong lesson|hides its own"
        r")\b[^.\n]*\.")
    root = pathlib.Path(__file__).resolve().parents[1]
    texts = {p.name: p.read_text()
             for p in list(root.glob("*.md")) + list((root / "outputs").rglob("*.md"))}
    nb = json.loads((root / "notebooks" / "walkthrough.ipynb").read_text())
    texts["walkthrough.ipynb"] = "\n".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown")

    bad = []
    for name, text in texts.items():
        if name == pathlib.Path(__file__).name:
            continue
        for m in pattern.finditer(text):
            line = text[:m.start()].count("\n") + 1
            bad.append(f"{name}:{line} {' '.join(m.group(0).split())[:110]}")
    assert not bad, (
        "these announce a quality rather than showing it; delete them and see what "
        "is lost:\n  " + "\n  ".join(bad))
