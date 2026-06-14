"""Tests for classify_moment_kind — procedure vs showcase heuristic."""
from skills.neurolearn.detection.moment_kind import (
    classify_moment_kind, PROCEDURE, SHOWCASE,
)


def test_showcase_single_item_description():
    text = (
        "The first item I want to highlight is this amulet. It grants the "
        "cast on dodge skill and gives plus four to all spell skills, doubling "
        "my clear for free."
    )
    assert classify_moment_kind(text) == SHOWCASE


def test_procedure_via_sequential_connectives_domain_craft():
    """A crafting walkthrough whose verbs aren't generic UI actions is still a
    procedure thanks to dense step connectives."""
    text = (
        "First, grab an absent base, chaos spamming it until you get plus 50 "
        "spirit, and then fracture that with desecrate. After this, annul it "
        "down. At this point you can quality the amulet."
    )
    assert classify_moment_kind(text) == PROCEDURE


def test_procedure_via_chained_ui_actions():
    text = "Click the Save button, then open settings and select the option."
    assert classify_moment_kind(text) == PROCEDURE


def test_empty_is_showcase():
    assert classify_moment_kind("") == SHOWCASE
    assert classify_moment_kind(None) == SHOWCASE


def test_russian_procedure():
    text = (
        "Сначала открываем таблицу, затем выбираем экспедицию, после этого "
        "нажимаем подтвердить, и теперь смотрим результат."
    )
    assert classify_moment_kind(text) == PROCEDURE
