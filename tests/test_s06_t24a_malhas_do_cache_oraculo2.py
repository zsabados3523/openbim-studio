# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24a rodada 2 (ADR-010, P3): erros transitorios, corrida TOCTOU e contencao.

Modulos alvo (o implementador NAO edita este arquivo nem o oraculo 1):
- `geometria/obim_geometria/cache_geometria.py`
- `geometria/obim_geometria/cache_leitura.py`

Interface exata e contratos adicionais (mantendo 100% da interface do oraculo 1):
1. `CacheGeometria.apagar_forma(self, chave: str, *, somente_corrompida: bool = False) -> bool`:
   - Uso do oraculo 1 (`cache.apagar_forma(chave)`) segue valido (`somente_corrompida=False` apaga
     incondicionalmente em `with self._tx()` e devolve `True` se existia).
   - Com `somente_corrompida=True`: dentro de `BEGIN IMMEDIATE` (`with self._tx()`), re-le a linha
     de `formas` para `chave` e valida `dtype_v`, tipo/tamanho dos blobs (`vertices`, `triangulos`)
     e `checksum`. So executa `DELETE FROM formas WHERE chave = ?` se existir E continuar corrompida;
     se ausente ou valida (ex.: regravada pelo construtor), NAO executa `DELETE` e devolve `False`.
2. `malhas_do_cache(cache: CacheGeometria, documento: str, global_ids) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], list[str]]`:
   - Mesma assinatura e retorno do oraculo 1; distingue ausencia (`row is None`), corrupcao real
     (blob/dtype/tamanho/checksum invalido) e erro transitorio (`sqlite3.OperationalError`
     locked/busy/I/O, `sqlite3.Error`, `OSError`, `MemoryError` na consulta ou decodificacao).
   - Erro transitorio na leitura NUNCA chama `apagar_forma` nem abre transacao de escrita:
     ocorrencias vao para `faltantes` e a linha valida permanece no banco.
   - Forma ausente na leitura NUNCA aciona `apagar_forma` nem escrita, mesmo com `gravar_lote`
     concorrente logo apos a leitura.
   - Em corrupcao real, chama `cache.apagar_forma(chave, somente_corrompida=True)` (fallback para
     `cache.apagar_forma(chave)` apenas se um substituto de teste aceitar 1 argumento, como no
     oraculo 1). Se o construtor reparou antes do `BEGIN IMMEDIATE`, a forma valida NAO e apagada.
   - `sqlite3.OperationalError` em `apagar_forma` (lock alem do `busy_timeout`, banco somente
     leitura) e capturado por chave e NAO derruba `malhas_do_cache`: devolve `(malhas, faltantes)`
     sem transacao aberta e sem abortar outras chaves.
"""
from __future__ import annotations

import importlib, sqlite3
from pathlib import Path

import numpy as np
import pytest

import obim_geometria.cache_geometria as C
from obim_geometria.cache_geometria import CacheGeometria, Ocorrencia, abrir_cache, documento_de

DOC_A, DOC_B = documento_de("modelo_a.ifc"), documento_de("modelo_b.ifc")
_ESCRITA_SQL = ("begin", "commit", "rollback", "insert", "update", "delete", "replace")


def _malhas_do_cache():
    return importlib.import_module("obim_geometria.cache_leitura").malhas_do_cache


def _forma_local(escala: float = 1.0, dtype=np.float64):
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.5, 0.0], [0.25, 3.0, 0.0], [0.5, 0.75, 4.0]], dtype=dtype) * escala
    return np.ascontiguousarray(v, dtype=dtype), np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int32)


def _mat(tx: float = 0.0, ty: float = 0.0, tz: float = 0.0):
    m = np.eye(4, dtype=np.float64)
    m[:3, 3] = [tx, ty, tz]
    return m


def _mundo(v, m):
    return np.asarray(v, dtype=np.float64) @ m[:3, :3].T + m[:3, 3]


def _oc(gid: str, chave: str = "k1", mat=None, pav: str = "P1", classe: str = "IfcWall"):
    m = _mat() if mat is None else np.asarray(mat, dtype=np.float64)
    caixa = np.array([[m[0, 3], m[1, 3], m[2, 3]], [m[0, 3] + 1.0, m[1, 3] + 1.0, m[2, 3] + 1.0]])
    return Ocorrencia(gid, chave, m, caixa, pav, classe)


def _db_path(pasta: Path) -> Path:
    return Path(pasta) / C.NOME_BANCO


def _sql(pasta: Path, consulta: str, args=()):
    con = sqlite3.connect(str(_db_path(pasta)))
    try:
        r = con.execute(consulta, args).fetchall()
        con.commit()
        return r
    finally:
        con.close()


def _corromper_checksum(pasta: Path, chave: str) -> None:
    [(blob,)] = _sql(pasta, "SELECT vertices FROM formas WHERE chave=?", (chave,))
    b = bytearray(blob)
    b[0] ^= 0xFF
    _sql(pasta, "UPDATE formas SET vertices=? WHERE chave=?", (bytes(b), chave))


def _eh_leitura_forma(sql: str) -> bool:
    s = " ".join(sql.lower().split())
    return s.startswith("select") and "from formas" in s and any(c in s for c in ("vertices", "dtype_v", "*"))


class _CursorEspiao:
    def __init__(self, real, ao_consumir):
        self._real, self._ao_consumir, self._feito = real, ao_consumir, False

    def _disparar(self):
        if not self._feito:
            self._feito = True
            self._ao_consumir()

    def fetchone(self):
        r = self._real.fetchone(); self._disparar(); return r

    def fetchall(self):
        r = self._real.fetchall(); self._disparar(); return r

    def __iter__(self):
        r = self._real.fetchall(); self._disparar(); return iter(r)

    def __getattr__(self, nome):
        return getattr(self._real, nome)


class _EspiaoCon:
    def __init__(self, real, *, antes=None, apos_cursor=None):
        self.real, self.sqls, self._antes, self._apos_cursor = real, [], antes, apos_cursor

    def execute(self, sql, params=()):
        self.sqls.append(sql)
        if self._antes is not None and (hook := self._antes(sql, params)) is not None:
            return hook(self.real, sql, params)
        cur = self.real.execute(sql, params)
        if self._apos_cursor is not None and (ao := self._apos_cursor(sql, params)) is not None:
            return _CursorEspiao(cur, ao)
        return cur

    def executemany(self, sql, seq):
        self.sqls.append(sql); return self.real.executemany(sql, seq)

    def escritas(self) -> list[str]:
        return [s for s in self.sqls if s.lstrip().lower().startswith(_ESCRITA_SQL)]

    def deletes(self) -> list[str]:
        return [s for s in self.sqls if s.lstrip().lower().startswith("delete")]

    def __getattr__(self, nome):
        return getattr(self.real, nome)


def _espiar(cache: CacheGeometria, *, antes=None, apos_cursor=None) -> _EspiaoCon:
    esp = _EspiaoCon(cache._con, antes=antes, apos_cursor=apos_cursor)
    cache._con = esp
    return esp


@pytest.fixture
def pasta(tmp_path): return tmp_path / "cache"


@pytest.fixture
def cache(pasta):
    with abrir_cache(pasta) as c:
        yield c


# ---------------------------------------------------------------- (1) erro transitorio nunca apaga
@pytest.mark.parametrize(
    "erro",
    [
        sqlite3.OperationalError("database is locked"),
        sqlite3.OperationalError("database is busy"),
        sqlite3.OperationalError("disk I/O error"),
        MemoryError("sem memoria ao ler forma"),
    ],
    ids=["locked", "busy", "disk_io", "memory_error"],
)
def test_erro_transitorio_na_leitura_nao_apaga_forma_valida(pasta, cache, erro):
    fn, f_alvo, f_viz = _malhas_do_cache(), _forma_local(1.0), _forma_local(2.0)
    m1, m2, mb = _mat(tx=1.0), _mat(tx=2.0), _mat(tx=5.0)
    cache.gravar_lote({"k_alvo": f_alvo, "k_viz": f_viz}, [_oc("g1", "k_alvo", m1), _oc("g2", "k_alvo", m2), _oc("g_viz", "k_viz")], documento=DOC_A)
    cache.gravar_lote({}, [_oc("g_b", "k_alvo", mb)], documento=DOC_B)
    falhou = {"n": 0}

    def antes(sql, _params):
        if _eh_leitura_forma(sql) and falhou["n"] == 0:
            falhou["n"] += 1
            raise erro

    esp = _espiar(cache, antes=antes)
    malhas, faltantes = fn(cache, DOC_A, ["g2", "g1"])
    assert falhou["n"] == 1 and malhas == {} and faltantes == ["g1", "g2"] and esp.escritas() == []
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k_alvo",), ("k_viz",)]
    malhas2, faltantes2 = fn(cache, DOC_A, ["g1", "g2", "g_viz"])
    assert list(malhas2) == ["g1", "g2", "g_viz"] and faltantes2 == []
    assert np.allclose(malhas2["g1"][0], _mundo(f_alvo[0], m1), rtol=0.0, atol=1e-12)
    malhas_b, faltantes_b = fn(cache, DOC_B, ["g_b"])
    assert list(malhas_b) == ["g_b"] and faltantes_b == []
    assert np.allclose(malhas_b["g_b"][0], _mundo(f_alvo[0], mb), rtol=0.0, atol=1e-12)


def test_lock_sqlite_real_na_leitura_nao_apaga_forma_valida(pasta, cache):
    fn, f1, m1 = _malhas_do_cache(), _forma_local(1.5), _mat(tx=3.0)
    cache.gravar_lote({"k1": f1}, [_oc("g1", "k1", m1)], documento=DOC_A)
    cache._con.execute("PRAGMA busy_timeout=1")
    disparado = {"v": False}

    def antes(sql, _params):
        if _eh_leitura_forma(sql) and not disparado["v"]:
            disparado["v"] = True

            def com_lock_real(real, s, p):
                con2 = sqlite3.connect(str(_db_path(pasta)), isolation_level=None)
                try:
                    con2.execute("BEGIN EXCLUSIVE")
                    return real.execute(s, p)
                finally:
                    if con2.in_transaction:
                        con2.execute("ROLLBACK")
                    con2.close()

            return com_lock_real

    esp = _espiar(cache, antes=antes)
    malhas, faltantes = fn(cache, DOC_A, ["g1"])
    assert disparado["v"] and malhas == {} and faltantes == ["g1"] and esp.escritas() == []
    assert _sql(pasta, "SELECT chave FROM formas") == [("k1",)]
    malhas2, faltantes2 = fn(cache, DOC_A, ["g1"])
    assert list(malhas2) == ["g1"] and faltantes2 == []
    assert np.allclose(malhas2["g1"][0], _mundo(f1[0], m1), rtol=0.0, atol=1e-12)


def test_memory_error_na_decodificacao_nao_apaga_forma_valida(pasta, cache, monkeypatch):
    fn, f1, m1 = _malhas_do_cache(), _forma_local(1.0), _mat(tx=4.0)
    cache.gravar_lote({"k1": f1}, [_oc("g1", "k1", m1)], documento=DOC_A)
    armado, real_fb = {"v": False, "disparou": False}, np.frombuffer

    def frombuffer_oom(*args, **kwargs):
        if armado["v"] and not armado["disparou"]:
            armado["disparou"] = True
            raise MemoryError("OOM na decodificacao de forma")
        return real_fb(*args, **kwargs)

    monkeypatch.setattr(np, "frombuffer", frombuffer_oom)
    esp = _espiar(cache, apos_cursor=lambda sql, _p: (lambda: armado.__setitem__("v", True)) if _eh_leitura_forma(sql) and not armado["v"] else None)
    malhas, faltantes = fn(cache, DOC_A, ["g1"])
    assert armado["disparou"] and malhas == {} and faltantes == ["g1"] and esp.escritas() == []
    assert _sql(pasta, "SELECT chave FROM formas") == [("k1",)]
    malhas2, faltantes2 = fn(cache, DOC_A, ["g1"])
    assert list(malhas2) == ["g1"] and faltantes2 == []
    assert np.allclose(malhas2["g1"][0], _mundo(f1[0], m1), rtol=0.0, atol=1e-12)


# ---------------------------------------------------------------- (2) apagar_forma condicional/atomica + TOCTOU
def test_apagar_forma_somente_corrompida_valida_vs_corrompida(pasta, cache):
    f1 = _forma_local(1.0)
    for k in ("k_ok", "k_tam_v", "k_tam_t", "k_ck", "k_dt", "k_tipo"):
        cache.gravar_forma(k, *f1)
    _sql(pasta, "UPDATE formas SET vertices=? WHERE chave='k_tam_v'", (b"\x01\x02\x03\x04\x05",))
    _sql(pasta, "UPDATE formas SET triangulos=? WHERE chave='k_tam_t'", (b"\x01\x02\x03\x04\x05\x06\x07",))
    _corromper_checksum(pasta, "k_ck")
    _sql(pasta, "UPDATE formas SET dtype_v='int8' WHERE chave='k_dt'")
    _sql(pasta, "UPDATE formas SET vertices='nao_e_blob' WHERE chave='k_tipo'")
    esp = _espiar(cache)
    assert cache.apagar_forma("k_ok", somente_corrompida=True) is False
    assert cache.apagar_forma("k_ausente", somente_corrompida=True) is False
    assert esp.deletes() == [] and cache.ler_forma("k_ok") is not None
    for k_ruim in ("k_tam_v", "k_tam_t", "k_ck", "k_dt", "k_tipo"):
        assert cache.apagar_forma(k_ruim, somente_corrompida=True) is True
        assert cache.apagar_forma(k_ruim, somente_corrompida=True) is False
    assert _sql(pasta, "SELECT chave FROM formas") == [("k_ok",)]
    assert cache.apagar_forma("k_ok") is True and _sql(pasta, "SELECT chave FROM formas") == []


def test_apagar_forma_somente_corrompida_reconfere_dentro_de_begin_immediate(pasta, cache):
    f_valida = _forma_local(3.0)
    cache.gravar_forma("k_race", *f_valida)
    _corromper_checksum(pasta, "k_race")
    assert cache.ler_forma("k_race") is None
    reparou = {"v": False}

    def antes(sql, _params):
        if sql.lstrip().lower().startswith("begin") and not reparou["v"]:
            reparou["v"] = True
            with abrir_cache(pasta) as c2:
                c2.gravar_forma("k_race", *f_valida)

    esp = _espiar(cache, antes=antes)
    assert cache.apagar_forma("k_race", somente_corrompida=True) is False
    assert reparou["v"] and esp.deletes() == []
    sqls_norm = [" ".join(s.lower().split()) for s in esp.sqls]
    idx_begin = next(i for i, s in enumerate(sqls_norm) if s.startswith("begin immediate"))
    assert any(_eh_leitura_forma(s) for s in sqls_norm[idx_begin + 1 :])
    v_db, t_db = cache.ler_forma("k_race")
    assert v_db.tobytes() == f_valida[0].tobytes() and t_db.tobytes() == f_valida[1].tobytes()


def test_toctou_construtor_repara_forma_corrompida_entre_leitura_e_delete(pasta, cache):
    fn, f_ok, f_rep = _malhas_do_cache(), _forma_local(1.0), _forma_local(2.5)
    m_ok, m_bad, m_b = _mat(tx=1.0), _mat(tx=2.0), _mat(tx=9.0)
    cache.gravar_lote({"k_ok": f_ok, "k_bad": f_rep}, [_oc("g_ok", "k_ok", m_ok), _oc("g_bad", "k_bad", m_bad)], documento=DOC_A)
    _corromper_checksum(pasta, "k_bad")
    reparou = {"v": False}

    def reparar():
        if not reparou["v"]:
            reparou["v"] = True
            with abrir_cache(pasta) as c2:
                c2.gravar_lote({"k_bad": f_rep}, [_oc("g_b", "k_bad", m_b)], documento=DOC_B)

    esp = _espiar(cache, apos_cursor=lambda sql, p: reparar if _eh_leitura_forma(sql) and not reparou["v"] and ("k_bad" in p or not p) else None)
    malhas, faltantes = fn(cache, DOC_A, ["g_ok", "g_bad"])
    assert reparou["v"] and list(malhas) == ["g_ok"] and faltantes == ["g_bad"] and esp.deletes() == []
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k_bad",), ("k_ok",)]
    malhas2, faltantes2 = fn(cache, DOC_A, ["g_ok", "g_bad"])
    assert list(malhas2) == ["g_bad", "g_ok"] and faltantes2 == []
    assert np.allclose(malhas2["g_bad"][0], _mundo(f_rep[0], m_bad), rtol=0.0, atol=1e-12)
    assert list(fn(cache, DOC_B, ["g_b"])[0]) == ["g_b"]


def test_toctou_construtor_grava_forma_ausente_entre_leitura_e_pos_leitura(pasta, cache):
    fn, f_nova, m_a, m_b = _malhas_do_cache(), _forma_local(2.0), _mat(tx=7.0), _mat(tx=11.0)
    cache.gravar_lote({}, [_oc("g_aus", "k_nova", m_a)], documento=DOC_A)
    gravou = {"v": False}

    def gravar():
        if not gravou["v"]:
            gravou["v"] = True
            with abrir_cache(pasta) as c2:
                c2.gravar_lote({"k_nova": f_nova}, [_oc("g_b", "k_nova", m_b)], documento=DOC_B)

    esp = _espiar(cache, apos_cursor=lambda sql, p: gravar if _eh_leitura_forma(sql) and not gravou["v"] and ("k_nova" in p or not p) else None)
    malhas, faltantes = fn(cache, DOC_A, ["g_aus"])
    assert gravou["v"] and malhas == {} and faltantes == ["g_aus"] and esp.escritas() == []
    assert _sql(pasta, "SELECT chave FROM formas") == [("k_nova",)]
    malhas2, faltantes2 = fn(cache, DOC_A, ["g_aus"])
    assert list(malhas2) == ["g_aus"] and faltantes2 == []
    assert np.allclose(malhas2["g_aus"][0], _mundo(f_nova[0], m_a), rtol=0.0, atol=1e-12)
    assert list(fn(cache, DOC_B, ["g_b"])[0]) == ["g_b"]


# ---------------------------------------------------------------- (3) OperationalError em apagar_forma
def test_operational_error_em_apagar_forma_lock_real_nao_derruba_malhas_do_cache(pasta, cache):
    fn, f_ok, f_bad, m_ok = _malhas_do_cache(), _forma_local(1.0), _forma_local(2.0), _mat(tx=3.0)
    cache.gravar_lote({"k_ok": f_ok, "k_bad": f_bad}, [_oc("g_ok", "k_ok", m_ok), _oc("g_bad", "k_bad")], documento=DOC_A)
    _corromper_checksum(pasta, "k_bad")
    cache._con.execute("PRAGMA busy_timeout=1")
    con2 = sqlite3.connect(str(_db_path(pasta)), isolation_level=None)
    try:
        con2.execute("BEGIN IMMEDIATE")
        malhas, faltantes = fn(cache, DOC_A, ["g_bad", "g_ok"])
    finally:
        if con2.in_transaction:
            con2.execute("ROLLBACK")
        con2.close()
    assert list(malhas) == ["g_ok"] and faltantes == ["g_bad"] and not cache._con.in_transaction
    assert np.allclose(malhas["g_ok"][0], _mundo(f_ok[0], m_ok), rtol=0.0, atol=1e-12)
    malhas2, faltantes2 = fn(cache, DOC_A, ["g_bad", "g_ok"])
    assert list(malhas2) == ["g_ok"] and faltantes2 == ["g_bad"] and _sql(pasta, "SELECT chave FROM formas") == [("k_ok",)]


def test_operational_error_em_apagar_forma_banco_somente_leitura_nao_derruba(pasta):
    fn, f_ok, f_bad, m_ok = _malhas_do_cache(), _forma_local(1.0), _forma_local(2.0), _mat(tx=6.0)
    with abrir_cache(pasta) as c:
        c.gravar_lote({"k_ok": f_ok, "k_bad": f_bad}, [_oc("g_ok", "k_ok", m_ok), _oc("g_bad", "k_bad")], documento=DOC_A)
    _corromper_checksum(pasta, "k_bad")
    con_ro = sqlite3.connect(f"{_db_path(pasta).resolve().as_uri()}?mode=ro", uri=True, isolation_level=None)
    try:
        malhas, faltantes = fn(CacheGeometria(_db_path(pasta), con_ro), DOC_A, ["g_bad", "g_ok"])
        assert list(malhas) == ["g_ok"] and faltantes == ["g_bad"] and not con_ro.in_transaction
        assert np.allclose(malhas["g_ok"][0], _mundo(f_ok[0], m_ok), rtol=0.0, atol=1e-12)
    finally:
        con_ro.close()


@pytest.mark.parametrize("msg", ["database is locked", "attempt to write a readonly database"])
def test_operational_error_em_apagar_forma_injetado_isolado_por_chave(pasta, cache, monkeypatch, msg):
    fn = _malhas_do_cache()
    cache.gravar_lote(
        {"k_ok": _forma_local(1.0), "k_bad1": _forma_local(2.0), "k_bad2": _forma_local(3.0)},
        [_oc("g_ok", "k_ok"), _oc("g_b1", "k_bad1"), _oc("g_b2", "k_bad2")],
        documento=DOC_A,
    )
    _corromper_checksum(pasta, "k_bad1")
    _corromper_checksum(pasta, "k_bad2")
    real_apagar, chamadas = cache.apagar_forma, []

    def apagar_falhando(chave: str, *args, **kwargs):
        chamadas.append(chave)
        if chave == "k_bad1":
            raise sqlite3.OperationalError(msg)
        return real_apagar(chave, *args, **kwargs)

    monkeypatch.setattr(cache, "apagar_forma", apagar_falhando)
    malhas, faltantes = fn(cache, DOC_A, ["g_b2", "g_ok", "g_b1"])
    assert list(malhas) == ["g_ok"] and faltantes == ["g_b1", "g_b2"]
    assert "k_bad1" in chamadas and "k_bad2" in chamadas
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k_bad1",), ("k_ok",)]
