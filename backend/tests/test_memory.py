"""Tests unitaires SA-26 (sans base de données) : pytest tests/test_memory.py"""
from datetime import UTC, datetime, timedelta

import pytest

from app.services.memory.base import MemoryLimits, MemoryMessage, trim_context
from app.services.memory.in_memory import InMemoryConversationMemory


class FakeClock:
    def __init__(self):
        self.now = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def msg(content: str, role="user") -> MemoryMessage:
    return MemoryMessage(role=role, content=content, created_at=datetime.now(UTC))


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def memory(clock):
    return InMemoryConversationMemory(MemoryLimits(ttl_minutes=30, max_messages=4, max_chars=50, max_stored=6), clock)


# ---------- trim_context ----------
def test_trim_garde_les_plus_recents_dans_l_ordre():
    messages = [msg(f"m{i}") for i in range(10)]
    assert [m.content for m in trim_context(messages, 3, 1000)] == ["m7", "m8", "m9"]


def test_trim_respecte_le_budget_de_caracteres_sans_trou():
    messages = [msg("a" * 30), msg("b" * 30), msg("c" * 10)]
    # c (10) + b (30) = 40 <= 50 ; + a (30) dépasserait -> on s'arrête
    assert [m.content[0] for m in trim_context(messages, 10, 50)] == ["b", "c"]


def test_trim_tronque_un_dernier_message_trop_long():
    result = trim_context([msg("x" * 10), msg("debut" + "y" * 100)], 10, 20)
    assert len(result) == 1
    assert result[0].content == "y" * 20


def test_trim_liste_vide():
    assert trim_context([], 5, 100) == []


# ---------- mémoire en RAM ----------
def test_ajout_et_historique(memory):
    memory.add("s1", "user", "  Bonjour  ")
    memory.add("s1", "assistant", "Salut !")
    assert [(m.role, m.content) for m in memory.history("s1")] == [("user", "Bonjour"), ("assistant", "Salut !")]
    assert memory.history("autre") == []


def test_sessions_isolees(memory):
    memory.add("s1", "user", "question A")
    memory.add("s2", "user", "question B")
    assert [m.content for m in memory.history("s1")] == ["question A"]


def test_contexte_pour_llm(memory):
    for i in range(6):
        memory.add("s1", "user", f"q{i}")
    assert memory.context_for_llm("s1") == [{"role": "user", "content": f"q{i}"} for i in range(2, 6)]


def test_max_stored(memory):
    for i in range(10):
        memory.add("s1", "user", f"q{i}")
    assert [m.content for m in memory.history("s1")] == [f"q{i}" for i in range(4, 10)]


def test_expiration_apres_inactivite(memory, clock):
    memory.add("s1", "user", "bonjour")
    clock.advance(minutes=29)
    assert len(memory.history("s1")) == 1
    clock.advance(minutes=1)
    assert memory.history("s1") == []


def test_fenetre_glissante(memory, clock):
    memory.add("s1", "user", "un")
    clock.advance(minutes=20)
    memory.add("s1", "user", "deux")  # prolonge toute la session
    clock.advance(minutes=20)
    assert [m.content for m in memory.history("s1")] == ["un", "deux"]


def test_nouvelle_conversation_apres_expiration(memory, clock):
    memory.add("s1", "user", "ancien")
    clock.advance(hours=1)
    memory.add("s1", "user", "nouveau")
    assert [m.content for m in memory.history("s1")] == ["nouveau"]


def test_clear_et_purge(memory, clock):
    memory.add("s1", "user", "a")
    memory.add("s1", "user", "b")
    memory.add("s2", "user", "c")
    assert memory.clear("s1") == 2
    assert memory.clear("s1") == 0
    clock.advance(hours=1)
    assert memory.purge_expired() == 1
    assert memory.history("s2") == []


@pytest.mark.parametrize("role,content", [("pirate", "x"), ("user", "   ")])
def test_entrees_invalides(memory, role, content):
    with pytest.raises(ValueError):
        memory.add("s1", role, content)


def test_limites_invalides():
    with pytest.raises(ValueError):
        MemoryLimits(max_messages=0)
