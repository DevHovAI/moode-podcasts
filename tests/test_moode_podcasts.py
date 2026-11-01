"""The first test, so `just check` is green from the start.

It also checks something real: that the package imports and carries a version
the release workflow can compare against a tag. Replace or extend it as the
project grows — but keep at least one test, because pytest treats an empty
run as a failure.
"""

import re

import moode_podcasts


def test_package_imports():
    assert moode_podcasts.__name__ == "moode_podcasts"


def test_version_is_semver():
    """The release workflow refuses to publish when the tag and this disagree."""
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", moode_podcasts.__version__), (
        f"__version__ is {moode_podcasts.__version__!r}, which is not a SemVer string"
    )
