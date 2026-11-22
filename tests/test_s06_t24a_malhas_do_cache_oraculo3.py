# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24a rodada 3 (ADR-010, P3): UTF-8 invalido em TEXT e duble sem ler_forma_estado.

Modulos alvo (o implementador NAO edita este arquivo nem os oraculos 1 e 2):
- `geometria/obim_geometria/cache_geometria.py`
- `geometria/obim_geometria/cache_leitura.py`

Contratos adicionais (mantendo 100% dos oraculos 1 e 2):
1. Coluna TEXT com UTF-8 invalido (`CAST(X'80FF' AS TEXT)` em `dtype_v`, `vertices`, `triangulos` ou
   `checksum`) e classificada como CORROMPIDA (`ler_forma_estado` -> `("corrompida", None)`),
   `apagar_forma(chave, somente_corrompida=True)` apaga e devolve `True` sem `OperationalError`, e
   `malhas_do_cache` devolve faltante + apaga a linha (`formas_presentes` deixa de listar); erro
   transitorio real (locked/busy/I/O ou lock SQLite real) continua NAO apagando.
2. `malhas_do_cache` com cache duble SEM `ler_forma_estado`: forma ausente NUNCA chama `apagar_forma`
   nem abre escrita; so apaga com prova de corrupcao via API disponivel (ou nunca no fallback).
"""
from __future__ import annotations

import importlib, sqlite3
from pathlib import Path
import numpy as np
import pytest

import obim_geometria.cache_geometria as C
from obim_geometria.cache_geometria import CacheGeometria, Ocorrencia, abrir_cache, documento_de

DOC_A = documento_de("modelo_a.ifc")
_ESCRITA_SQL = ("begin", "commit", "rollback", "insert", "update", "delete", "replace")


def _malhas_do_cache(): return importlib.import_module("obim_geometria.cache_leitura").malhas_do_cache
def _db_path(pasta: Path) -> Path: return Path(pasta) / C.NOME_BANCO
def _mundo(v, m): return np.asarray(v, dtype=np.float64) @ m[:3, :3].T + m[:3, 3]


def _forma_local(escala: float = 1.0, dtype=np.float64):
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.5, 0.0], [0.25, 3.0, 0.0], [0.5, 0.75, 4.0]], dtype=dtype) * escala
    return np.ascontiguousarray(v, dtype=dtype), np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int32)


def _mat(tx: float = 0.0, ty: float = 0.0, tz: float = 0.0):
    m = np.eye(4, dtype=np.float64); m[:3, 3] = [tx, ty, tz]; return m


def _oc(gid: str, chave: str = "k1", mat=None, pav: str = "P1", classe: str = "IfcWall"):
    m = _mat() if mat is None else np.asarray(mat, dtype=np.float64)
    caixa = np.array([[m[0, 3], m[1, 3], m[2, 3]], [m[0, 3] + 1.0, m[1, 3] + 1.0, m[2, 3] + 1.0]])
    return Ocorrencia(gid, chave, m, caixa, pav, classe)


def _sql(pasta: Path, consulta: str, args=()):
    con = sqlite3.connect(str(_db_path(pasta)))
    try:
        r = con.execute(consulta, args).fetchall(); con.commit(); return r
    finally:
        con.close()


def _eh_leitura_forma(sql: str) -> bool:
    s = " ".join(sql.lower().split())
    return s.startswith("select") and "from formas" in s and any(c in s for c in ("vertices", "dtype_v", "*"))


class _EspiaoCon:
    def __init__(self, real, *, antes=None):
        self.real, self.sqls, self._antes = real, [], antes

    def execute(self, sql, params=()):
        self.sqls.append(sql)
        if self._antes is not None and (hook := self._antes(sql, params)) is not None:
            return hook(self.real, sql, params)
        return self.real.execute(sql, params)

    def executemany(self, sql, seq):
        self.sqls.append(sql); return self.real.executemany(sql, seq)

    def escritas(self) -> list[str]:
        return [s for s in self.sqls if s.lstrip().lower().startswith(_ESCRITA_SQL)]

    def __getattr__(self, nome): return getattr(self.real, nome)


def _espiar(cache: CacheGeometria, *, antes=None) -> _EspiaoCon:
    esp = _EspiaoCon(cache._con, antes=antes); cache._con = esp; return esp


class _ProxySemEstado:
    def __init__(self, real: CacheGeometria, *, com_formas_presentes: bool = False, apagar_um_arg: bool = False):
        self._real, self._apagar_um_arg, self.apagadas = real, apagar_um_arg, []
        if com_formas_presentes:
            self.formas_presentes = real.formas_presentes

    def ocorrencias_por_ids(self, global_ids, documento: str = ""):
        return self._real.ocorrencias_por_ids(global_ids, documento=documento)

    def ler_forma(self, chave: str): return self._real.ler_forma(chave)

    def apagar_forma(self, chave: str, *args, **kwargs):
        if self._apagar_um_arg and (args or kwargs):
            raise TypeError("apagar_forma aceita apenas 1 argumento")
        self.apagadas.append(chave)
        return self._real.apagar_forma(chave, *args, **kwargs)


@pytest.fixture
def pasta(tmp_path): return tmp_path / "cache"


@pytest.fixture
def cache(pasta):
    with abrir_cache(pasta) as c:
        yield c


# ---------------------------------------------------------------- (1) UTF-8 invalido em TEXT vs transitorio
@pytest.mark.parametrize("coluna", ["dtype_v", "vertices", "triangulos", "checksum"])
def test_utf8_invalido_em_coluna_text_vira_faltante_e_apaga_linha(pasta, cache, coluna):
    fn, f_ok, f_bad = _malhas_do_cache(), _forma_local(1.0), _forma_local(2.0)
    m_ok, m1, m2 = _mat(tx=1.0), _mat(tx=2.0), _mat(tx=3.0)
    cache.gravar_lote({"k_ok": f_ok, "k_utf8": f_bad}, [_oc("g_ok", "k_ok", m_ok), _oc("g_u2", "k_utf8", m2), _oc("g_u1", "k_utf8", m1)], documento=DOC_A)
    _sql(pasta, f"UPDATE formas SET {coluna} = CAST(X'80FF' AS TEXT) WHERE chave = 'k_utf8'")
    assert "k_utf8" in cache.formas_presentes(["k_utf8"])
    assert cache.ler_forma_estado("k_utf8") == ("corrompida", None)
    malhas, faltantes = fn(cache, DOC_A, ["g_u2", "g_ok", "g_u1"])
    assert list(malhas) == ["g_ok"] and faltantes == ["g_u1", "g_u2"] and not cache._con.in_transaction
    assert "k_utf8" not in cache.formas_presentes(["k_utf8"])
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k_ok",)]
    assert set(cache.ocorrencias_por_ids(["g_ok", "g_u1", "g_u2"], documento=DOC_A)) == {"g_ok", "g_u1", "g_u2"}
    cache.gravar_forma("k_utf8", *f_bad)
    malhas2, faltantes2 = fn(cache, DOC_A, ["g_u2", "g_ok", "g_u1"])
    assert list(malhas2) == ["g_ok", "g_u1", "g_u2"] and faltantes2 == []
    assert np.allclose(malhas2["g_u1"][0], _mundo(f_bad[0], m1), rtol=0.0, atol=1e-12)


@pytest.mark.parametrize("coluna", ["dtype_v", "vertices"])
def test_apagar_forma_somente_corrompida_apaga_utf8_invalido_sem_operational_error(pasta, cache, coluna):
    cache.gravar_forma("k_ok", *_forma_local(1.0))
    cache.gravar_forma("k_utf8", *_forma_local(2.0))
    _sql(pasta, f"UPDATE formas SET {coluna} = CAST(X'80FF' AS TEXT) WHERE chave = 'k_utf8'")
    assert cache.apagar_forma("k_utf8", somente_corrompida=True) is True
    assert cache.apagar_forma("k_utf8", somente_corrompida=True) is False
    assert not cache._con.in_transaction and "k_utf8" not in cache.formas_presentes(["k_utf8"])
    assert _sql(pasta, "SELECT chave FROM formas") == [("k_ok",)]


@pytest.mark.parametrize(
    "erro",
    [sqlite3.OperationalError("database is locked"), sqlite3.OperationalError("database is busy"), sqlite3.OperationalError("disk I/O error")],
    ids=["locked", "busy", "disk_io"],
)
def test_utf8_invalido_apaga_mas_erro_transitorio_real_nao_apaga(pasta, cache, erro):
    fn, f_ok, f_trans, m_trans = _malhas_do_cache(), _forma_local(1.0), _forma_local(3.0), _mat(tx=5.0)
    cache.gravar_lote({"k_ok": f_ok, "k_utf8": _forma_local(2.0), "k_trans": f_trans}, [_oc("g_ok", "k_ok"), _oc("g_utf8", "k_utf8"), _oc("g_trans", "k_trans", m_trans)], documento=DOC_A)
    _sql(pasta, "UPDATE formas SET dtype_v = CAST(X'80FF' AS TEXT) WHERE chave = 'k_utf8'")
    falhou = {"n": 0}

    def antes(sql, params):
        if _eh_leitura_forma(sql) and "k_trans" in params and falhou["n"] == 0:
            falhou["n"] += 1; raise erro

    _espiar(cache, antes=antes)
    malhas, faltantes = fn(cache, DOC_A, ["g_utf8", "g_trans", "g_ok"])
    assert falhou["n"] == 1 and list(malhas) == ["g_ok"] and faltantes == ["g_trans", "g_utf8"]
    assert "k_utf8" not in cache.formas_presentes(["k_utf8"]) and "k_trans" in cache.formas_presentes(["k_trans"])
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k_ok",), ("k_trans",)]
    malhas2, faltantes2 = fn(cache, DOC_A, ["g_trans", "g_ok"])
    assert list(malhas2) == ["g_ok", "g_trans"] and faltantes2 == []
    assert np.allclose(malhas2["g_trans"][0], _mundo(f_trans[0], m_trans), rtol=0.0, atol=1e-12)


def test_utf8_invalido_apaga_mas_lock_sqlite_real_nao_apaga(pasta, cache):
    fn, f_ok, f_lock, m_lock = _malhas_do_cache(), _forma_local(1.0), _forma_local(2.5), _mat(tx=8.0)
    cache.gravar_lote({"k_ok": f_ok, "k_utf8": _forma_local(2.0), "k_lock": f_lock}, [_oc("g_ok", "k_ok"), _oc("g_utf8", "k_utf8"), _oc("g_lock", "k_lock", m_lock)], documento=DOC_A)
    _sql(pasta, "UPDATE formas SET vertices = CAST(X'80FF' AS TEXT) WHERE chave = 'k_utf8'")
    cache._con.execute("PRAGMA busy_timeout=1")
    disparado = {"v": False}

    def antes(sql, params):
        if _eh_leitura_forma(sql) and "k_lock" in params and not disparado["v"]:
            disparado["v"] = True
            def com_lock_real(real, s, p):
                con2 = sqlite3.connect(str(_db_path(pasta)), isolation_level=None)
                try:
                    con2.execute("BEGIN EXCLUSIVE")
                    return real.execute(s, p)
                finally:
                    if con2.in_transaction: con2.execute("ROLLBACK")
                    con2.close()
            return com_lock_real

    _espiar(cache, antes=antes)
    malhas, faltantes = fn(cache, DOC_A, ["g_utf8", "g_lock", "g_ok"])
    assert disparado["v"] and list(malhas) == ["g_ok"] and faltantes == ["g_lock", "g_utf8"]
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k_lock",), ("k_ok",)]
    malhas2, faltantes2 = fn(cache, DOC_A, ["g_lock", "g_ok"])
    assert list(malhas2) == ["g_lock", "g_ok"] and faltantes2 == []
    assert np.allclose(malhas2["g_lock"][0], _mundo(f_lock[0], m_lock), rtol=0.0, atol=1e-12)


# ---------------------------------------------------------------- (2) cache duble sem ler_forma_estado
@pytest.mark.parametrize("com_presentes,um_arg", [(False, False), (False, True), (True, False), (True, True)], ids=["minimo", "minimo_1arg", "com_presentes", "com_presentes_1arg"])
def test_duble_sem_ler_forma_estado_ausente_nao_apaga_nem_abre_escrita(cache, com_presentes, um_arg):
    fn = _malhas_do_cache()
    cache.gravar_lote({"k_ok": _forma_local(1.0)}, [_oc("g_ok", "k_ok"), _oc("g_aus", "k_aus")], documento=DOC_A)
    proxy = _ProxySemEstado(cache, com_formas_presentes=com_presentes, apagar_um_arg=um_arg)
    assert not hasattr(proxy, "ler_forma_estado")
    esp = _espiar(cache)
    malhas, faltantes = fn(proxy, DOC_A, ["g_aus", "g_ok"])
    assert list(malhas) == ["g_ok"] and faltantes == ["g_aus"] and proxy.apagadas == [] and esp.escritas() == []


def test_duble_sem_ler_forma_estado_com_presentes_so_apaga_corrompida_ou_nunca(pasta, cache):
    fn = _malhas_do_cache()
    cache.gravar_lote({"k_ok": _forma_local(1.0), "k_bad": _forma_local(2.0)}, [_oc("g_ok", "k_ok"), _oc("g_bad", "k_bad"), _oc("g_aus", "k_aus")], documento=DOC_A)
    _sql(pasta, "UPDATE formas SET dtype_v = 'ruim' WHERE chave = 'k_bad'")
    proxy = _ProxySemEstado(cache, com_formas_presentes=True, apagar_um_arg=False)
    malhas, faltantes = fn(proxy, DOC_A, ["g_bad", "g_aus", "g_ok"])
    assert list(malhas) == ["g_ok"] and faltantes == ["g_aus", "g_bad"]
    assert "k_aus" not in proxy.apagadas and "k_ok" not in proxy.apagadas and set(proxy.apagadas) <= {"k_bad"}
    assert "k_ok" in cache.formas_presentes(["k_ok"])


def test_duble_sem_ler_forma_estado_sem_prova_nao_apaga_valida_em_erro_transitorio(pasta, cache):
    fn, f_ok, f_val, m_val = _malhas_do_cache(), _forma_local(1.0), _forma_local(2.0), _mat(tx=4.0)
    cache.gravar_lote({"k_ok": f_ok, "k_valida": f_val}, [_oc("g_ok", "k_ok"), _oc("g_val", "k_valida", m_val)], documento=DOC_A)
    proxy = _ProxySemEstado(cache, com_formas_presentes=False, apagar_um_arg=True)
    falhou = {"n": 0}

    def antes(sql, params):
        if _eh_leitura_forma(sql) and "k_valida" in params and falhou["n"] == 0:
            falhou["n"] += 1; raise sqlite3.OperationalError("database is locked")

    esp = _espiar(cache, antes=antes)
    malhas, faltantes = fn(proxy, DOC_A, ["g_val", "g_ok"])
    assert falhou["n"] == 1 and list(malhas) == ["g_ok"] and faltantes == ["g_val"]
    assert proxy.apagadas == [] and esp.escritas() == []
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k_ok",), ("k_valida",)]
    malhas2, faltantes2 = fn(proxy, DOC_A, ["g_val"])
    assert list(malhas2) == ["g_val"] and faltantes2 == []
    assert np.allclose(malhas2["g_val"][0], _mundo(f_val[0], m_val), rtol=0.0, atol=1e-12)
