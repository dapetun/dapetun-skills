"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from skill_optimizer.config import load_config
from skill_optimizer.pipeline import analyze, load_skills

FIXTURES = Path(__file__).parent / "fixtures" / "skill_library"


@pytest.fixture
def fixture_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    shutil.copytree(FIXTURES / "user" / ".agents", home / ".agents")
    return home


@pytest.fixture
def fixture_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    shutil.copytree(FIXTURES / "project", project)
    return project


@pytest.fixture
def cfg(fixture_project: Path, fixture_home: Path):
    return load_config(
        project_root=fixture_project,
        home=fixture_home,
        platforms=["agents"],
        scopes=["user", "project"],
    )


@pytest.fixture
def skills(cfg):
    return load_skills(cfg)


@pytest.fixture
def analyzed(cfg):
    return analyze(cfg)
