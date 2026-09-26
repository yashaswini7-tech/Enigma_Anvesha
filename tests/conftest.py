from pathlib import Path

import pytest

from anvesha.synth.persona import build_persona, write_outputs


@pytest.fixture(scope="session")
def demo_paths(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return write_outputs(build_persona(), tmp_path_factory.mktemp("demo"))
