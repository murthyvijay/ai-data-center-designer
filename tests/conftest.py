from pathlib import Path

import pytest
import yaml

from dcdesigner import DesignSpec, load_catalog

ROOT = Path(__file__).resolve().parents[1]
PRESETS = sorted((ROOT / "presets").glob("*.yaml"))


def spec_from(name: str, **overrides) -> DesignSpec:
    raw = yaml.safe_load((ROOT / "presets" / f"{name}.yaml").read_text())
    for dotted, value in overrides.items():
        node = raw
        *path, last = dotted.split("__")
        for key in path:
            node = node[key]
        node[last] = value
    return DesignSpec.model_validate(raw)


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture(scope="session")
def arch_a():
    return spec_from("arch-a-nvl72-300k")


@pytest.fixture(scope="session")
def arch_b():
    return spec_from("arch-b-ocp8-300k")
