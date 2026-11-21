# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T24a (ADR-010, P3): leitura de malhas do cache no mundo.

Modulos alvo (o implementador NAO edita este arquivo):
- `geometria/obim_geometria/cache_geometria.py`: novo metodo `CacheGeometria.apagar_forma(chave: str) -> bool`.
- `geometria/obim_geometria/cache_leitura.py` (novo): `malhas_do_cache(cache, documento, global_ids)`.

Interface exata:
1. `CacheGeometria.apagar_forma(chave: str) -> bool`:
   - Remove a linha `chave` da tabela `formas` em transacao (`with self._tx()`).
   - Devolve `True` se existia e foi apagada; `False` se `chave` nao existia.
   - Funciona mesmo com blobs/checksum corrompidos; nao toca em outras formas, `ocorrencias` nem `memo`.
2. `malhas_do_cache(cache: CacheGeometria, documento: str, global_ids) -> tuple[dict[str, tuple[np.ndarray, np.ndarray]], list[str]]`:
   - `global_ids`: iteravel de `str` (pode ser vazio, gerador ou ter duplicados).
   - Le ocorrencias por `documento` e `global_ids` deduplicados (via `ocorrencias_por_ids`, NUNCA pela
     coluna `pavimento` nem por `ocorrencias_do_pavimento`).
   - Aplica a matriz 4x4 da ocorrencia em float64:
     `verts_mundo = verts_local.astype(np.float64) @ matriz[:3, :3].T + matriz[:3, 3]`.
   - `malhas_mundo`: `dict[str, tuple[np.ndarray, np.ndarray]]` ordenado por GlobalId ascendente;
     cada valor e `(verts_mundo, tris)` C-contiguos (`float64` `(N, 3)`, `int32` `(M, 3)`).
   - `faltantes`: `list[str]` ordenada por GlobalId ascendente, sem duplicados (ocorrencia ausente,
     corrompida ou de outro documento; ou forma ausente ou corrompida).
   - Forma corrompida (existe em `formas`, mas `ler_forma` devolve `None`): GlobalId(s) vao para
     `faltantes` E `cache.apagar_forma(chave)` apaga a linha para o construtor (P2) refazer.
   - Retorno independente do banco e entre ocorrencias: arrays sao copias independentes (ou somente
     leitura), e `dict`/`list` sao novos a cada chamada.
   - Nao abre transacao de escrita (`BEGIN`/`INSERT`/`UPDATE`/`DELETE`/`REPLACE`) em nenhum caso,
     exceto `apagar_forma` quando uma forma existente esta corrompida.

Geometria sintetica via API real de `cache_geometria`; sem IFC real e sem dados externos.
"""
from __future__ import annotations

import importlib
import os
import sqlite3

import numpy as np
import pytest

import obim_geometria.cache_geometria as C
from obim_geometria.cache_geometria import Ocorrencia, abrir_cache, documento_de

DOC_A = documento_de("modelo_a.ifc")
DOC_B = documento_de("modelo_b.ifc")
_ESCRITA_SQL = ("begin", "commit", "rollback", "insert", "update", "delete", "replace")


def _malhas_do_cache():
    return importlib.import_module("obim_geometria.cache_leitura").malhas_do_cache


def _forma_local(escala=1.0, dtype=np.float64):
    """Tetraedro assimetrico local (detecta matriz ausente e transposta R errada)."""
    v = np.array([[0.0, 0.0, 0.0], [2.0, 0.5, 0.0], [0.25, 3.0, 0.0], [0.5, 0.75, 4.0]], dtype=dtype) * escala
    t = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int32)
    return np.ascontiguousarray(v, dtype=dtype), t


def _mat(tx=0.0, ty=0.0, tz=0.0, rot_z_90=False, esc=(1.0, 1.0, 1.0)):
    m = np.eye(4, dtype=np.float64)
    if rot_z_90:
        m[:3, :3] = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    m[:3, :3] = m[:3, :3] @ np.diag(np.asarray(esc, dtype=np.float64))
    m[:3, 3] = [tx, ty, tz]
    return m


def _mundo(v, m):
    return np.asarray(v, dtype=np.float64) @ m[:3, :3].T + m[:3, 3]


def _oc(gid, chave="k1", mat=None, pav="P1", classe="IfcWall", v_ref=None):
    m = _mat() if mat is None else np.asarray(mat, dtype=np.float64)
    if v_ref is None:
        caixa = np.array([[m[0, 3], m[1, 3], m[2, 3]], [m[0, 3] + 1.0, m[1, 3] + 1.0, m[2, 3] + 1.0]])
    else:
        w = _mundo(v_ref, m)
        caixa = np.vstack((w.min(axis=0), w.max(axis=0)))
    return Ocorrencia(gid, chave, m, caixa, pav, classe)


def _sql(pasta, consulta, args=()):
    con = sqlite3.connect(os.path.join(str(pasta), C.NOME_BANCO))
    try:
        r = con.execute(consulta, args).fetchall()
        con.commit()
        return r
    finally:
        con.close()


class _Espiao:
    def __init__(self, real):
        self.real, self.sqls = real, []

    def execute(self, sql, params=()):
        self.sqls.append(sql)
        return self.real.execute(sql, params)

    def executemany(self, sql, seq):
        self.sqls.append(sql)
        return self.real.executemany(sql, seq)

    def escritas(self) -> list[str]:
        return [s for s in self.sqls if s.lstrip().lower().startswith(_ESCRITA_SQL)]

    def __getattr__(self, nome):
        return getattr(self.real, nome)


def _espiar(cache):
    esp = _Espiao(cache._con)
    cache._con = esp
    return esp


@pytest.fixture
def pasta(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def cache(pasta):
    with abrir_cache(pasta) as c:
        yield c


# ---------------------------------------------------------------- apagar_forma
def test_apagar_forma_remove_so_a_chave_e_preserva_o_resto(pasta, cache):
    f1, f2 = _forma_local(1.0), _forma_local(2.0)
    cache.gravar_lote({"k1": f1, "k2": f2}, [_oc("g1", "k1"), _oc("g2", "k2")], documento=DOC_A, memo=("s1", {1: "k1"}))
    assert cache.apagar_forma("k1") is True
    assert cache.apagar_forma("k1") is False
    assert cache.apagar_forma("inexistente") is False
    assert cache.ler_forma("k1") is None
    assert cache.formas_presentes(["k1", "k2"]) == {"k2"}
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k2",)]
    assert cache.ler_ocorrencia("g1", documento=DOC_A) is not None
    assert cache.memo_ler(DOC_A, "s1") == {1: "k1"}


def test_apagar_forma_remove_linha_corrompida_e_permite_regravar(pasta, cache):
    f1 = _forma_local(1.0)
    cache.gravar_forma("k_bad", *f1)
    [(blob,)] = _sql(pasta, "SELECT vertices FROM formas WHERE chave='k_bad'")
    ruim = bytearray(blob)
    ruim[0] ^= 0xFF
    _sql(pasta, "UPDATE formas SET vertices=? WHERE chave='k_bad'", (bytes(ruim),))
    assert "k_bad" in cache.formas_presentes(["k_bad"]) and cache.ler_forma("k_bad") is None
    assert cache.apagar_forma("k_bad") is True
    assert "k_bad" not in cache.formas_presentes(["k_bad"])
    assert _sql(pasta, "SELECT COUNT(*) FROM formas WHERE chave='k_bad'") == [(0,)]
    cache.gravar_forma("k_bad", *f1)
    v_novo, t_novo = cache.ler_forma("k_bad")
    assert np.array_equal(v_novo, f1[0]) and np.array_equal(t_novo, f1[1])


# ---------------------------------------------------------------- matriz e precisao
def test_aplica_matriz_rotacao_translacao_e_escala(cache):
    fn = _malhas_do_cache()
    v_loc, t_loc = _forma_local(1.0, dtype=np.float64)
    m1 = _mat(tx=10.0, ty=-5.0, tz=2.5, rot_z_90=True)
    m2 = _mat(tx=1_000_000.25, ty=2_000_000.75, tz=12.5, rot_z_90=True, esc=(2.0, 0.5, 3.0))
    cache.gravar_lote({"k1": (v_loc, t_loc)}, [_oc("g1", "k1", m1, v_ref=v_loc), _oc("g2", "k1", m2, v_ref=v_loc)], documento=DOC_A)
    malhas, faltantes = fn(cache, DOC_A, ["g2", "g1"])
    assert faltantes == [] and list(malhas) == ["g1", "g2"]
    for gid, m in (("g1", m1), ("g2", m2)):
        vw, tw = malhas[gid]
        assert vw.dtype == np.float64 and vw.shape == v_loc.shape and vw.flags["C_CONTIGUOUS"]
        assert tw.dtype == np.int32 and tw.shape == t_loc.shape and tw.flags["C_CONTIGUOUS"]
        assert np.allclose(vw, _mundo(v_loc, m), rtol=0.0, atol=1e-12) and np.array_equal(tw, t_loc)
        assert not np.allclose(vw, v_loc)
        assert not np.allclose(vw, v_loc @ m[:3, :3] + m[:3, 3], rtol=0.0, atol=1e-6)  # detecta falta de .T


def test_forma_float32_promovida_para_float64_no_mundo(cache):
    fn = _malhas_do_cache()
    v32, t32 = _forma_local(1.0, dtype=np.float32)
    m = _mat(tx=1_000_000.125, ty=2_000_000.375, tz=0.5, rot_z_90=True)
    cache.gravar_lote({"k32": (v32, t32)}, [_oc("g1", "k32", m, v_ref=v32)], documento=DOC_A)
    malhas, faltantes = fn(cache, DOC_A, ["g1"])
    assert faltantes == []
    vw, tw = malhas["g1"]
    assert vw.dtype == np.float64 and tw.dtype == np.int32
    assert np.allclose(vw, _mundo(v32, m), rtol=0.0, atol=1e-12)


# ---------------------------------------------------------------- selecao por GlobalId (nunca pavimento)
def test_le_pela_lista_de_global_ids_nunca_pela_coluna_pavimento(cache, monkeypatch):
    fn = _malhas_do_cache()
    cache.gravar_lote(
        {"k1": _forma_local(1.0)},
        [
            _oc("g_p1_in", "k1", _mat(tx=1.0), pav="P1"),
            _oc("g_p1_out", "k1", _mat(tx=2.0), pav="P1"),
            _oc("g_p2", "k1", _mat(tx=3.0), pav="P2"),
            _oc("g_sem_pav", "k1", _mat(tx=4.0), pav=None),
        ],
        documento=DOC_A,
    )
    monkeypatch.setattr(cache, "ocorrencias_do_pavimento", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("nao usar pavimento")))
    esp = _espiar(cache)
    malhas, faltantes = fn(cache, DOC_A, ["g_sem_pav", "g_p2", "g_p1_in"])
    assert faltantes == [] and list(malhas) == ["g_p1_in", "g_p2", "g_sem_pav"] and "g_p1_out" not in malhas
    for sql in esp.sqls:
        if "where" in sql.lower():
            assert "pavimento" not in sql.lower().split("where", 1)[1]


# ---------------------------------------------------------------- faltantes, documentos, ordem, bordas
def test_forma_ausente_vai_para_faltantes_sem_apagar_nem_escrever(cache, monkeypatch):
    fn = _malhas_do_cache()
    cache.gravar_lote({"k_ok": _forma_local(1.0)}, [_oc("g1", "k_ok"), _oc("g2", "k_falta")], documento=DOC_A)
    apagadas = []
    real_apagar = cache.apagar_forma
    monkeypatch.setattr(cache, "apagar_forma", lambda chave: (apagadas.append(chave), real_apagar(chave))[1])
    esp = _espiar(cache)
    malhas, faltantes = fn(cache, DOC_A, ["g2", "g1"])
    assert list(malhas) == ["g1"] and faltantes == ["g2"] and apagadas == [] and esp.escritas() == []


def test_global_id_desconhecido_e_ocorrencia_corrompida_viram_faltantes(pasta, cache):
    fn = _malhas_do_cache()
    cache.gravar_lote({"k1": _forma_local(1.0)}, [_oc("g_ok", "k1"), _oc("g_oc_ruim", "k1")], documento=DOC_A)
    [(blob,)] = _sql(pasta, "SELECT matriz FROM ocorrencias WHERE global_id='g_oc_ruim'")
    ruim = bytearray(blob)
    ruim[8] ^= 0xFF
    _sql(pasta, "UPDATE ocorrencias SET matriz=? WHERE global_id='g_oc_ruim'", (bytes(ruim),))
    esp = _espiar(cache)
    malhas, faltantes = fn(cache, DOC_A, ["g_desc_2", "g_ok", "g_oc_ruim", "g_desc_1"])
    assert list(malhas) == ["g_ok"] and faltantes == ["g_desc_1", "g_desc_2", "g_oc_ruim"] and esp.escritas() == []


def test_ocorrencia_de_outro_documento_nao_vaza_e_vira_faltante(cache):
    fn = _malhas_do_cache()
    f1, f2 = _forma_local(1.0), _forma_local(3.0)
    cache.gravar_lote({"k1": f1, "k2": f2}, [_oc("g_comum", "k1", _mat(tx=10.0))], documento=DOC_A)
    cache.gravar_lote({}, [_oc("g_comum", "k2", _mat(tx=99.0)), _oc("g_so_b", "k2", _mat(tx=5.0))], documento=DOC_B)
    cache.gravar_lote({}, [_oc("g_padrao", "k1", _mat(tx=7.0))], documento="")
    malhas, faltantes = fn(cache, DOC_A, ["g_so_b", "g_comum", "g_padrao"])
    assert list(malhas) == ["g_comum"] and faltantes == ["g_padrao", "g_so_b"]
    assert np.allclose(malhas["g_comum"][0], _mundo(f1[0], _mat(tx=10.0)), rtol=0.0, atol=1e-12)
    m_pad, f_pad = fn(cache, "", ["g_padrao", "g_comum"])
    assert list(m_pad) == ["g_padrao"] and f_pad == ["g_comum"]


def test_ordem_deterministica_por_global_id(cache):
    fn = _malhas_do_cache()
    ids = ["g_z", "g_a", "g_m", "g_0", "g_b"]
    cache.gravar_lote({"k1": _forma_local(1.0)}, [_oc(g, "k1", _mat(tx=float(i))) for i, g in enumerate(ids)], documento=DOC_A)
    entradas = [
        ["g_z", "f_b", "g_a", "f_a", "g_m", "g_0", "g_b"],
        ["g_b", "g_0", "g_m", "f_a", "g_a", "f_b", "g_z"],
        (x for x in ["g_m", "g_z", "f_b", "g_b", "g_0", "g_a", "f_a"]),
    ]
    esperado_ok, ref = sorted(ids), None
    for ent in entradas:
        malhas, faltantes = fn(cache, DOC_A, ent)
        assert list(malhas) == esperado_ok and faltantes == ["f_a", "f_b"]
        if ref is None:
            ref = malhas
        else:
            for g in esperado_ok:
                assert malhas[g][0].tobytes() == ref[g][0].tobytes() and malhas[g][1].tobytes() == ref[g][1].tobytes()


def test_lista_vazia_e_duplicados(cache):
    fn = _malhas_do_cache()
    cache.gravar_lote({"k1": _forma_local(1.0)}, [_oc("g1", "k1"), _oc("g2", "k1")], documento=DOC_A)
    esp = _espiar(cache)
    assert fn(cache, DOC_A, []) == ({}, [])
    assert fn(cache, DOC_A, (x for x in ())) == ({}, [])
    malhas, faltantes = fn(cache, DOC_A, ["g2", "g_x", "g1", "g2", "g_x", "g1"])
    assert list(malhas) == ["g1", "g2"] and faltantes == ["g_x"]
    m_gen, f_gen = fn(cache, DOC_A, (x for x in ["g2", "g2", "g_x", "g_x"]))
    assert list(m_gen) == ["g2"] and f_gen == ["g_x"] and esp.escritas() == []


def test_mais_de_500_global_ids_em_blocos(cache):
    fn = _malhas_do_cache()
    ocs = [_oc(f"g{i:04d}", "k1", _mat(tx=float(i))) for i in range(620)]
    cache.gravar_lote({"k1": _forma_local(1.0)}, ocs, documento=DOC_A)
    desconhecidos = [f"x{i:03d}" for i in range(40)]
    esp = _espiar(cache)
    malhas, faltantes = fn(cache, DOC_A, list(reversed([o.global_id for o in ocs] + desconhecidos)))
    assert list(malhas) == [f"g{i:04d}" for i in range(620)] and faltantes == desconhecidos and esp.escritas() == []


# ---------------------------------------------------------------- forma corrompida + apagar_forma
@pytest.mark.parametrize("modo", ["checksum", "dtype_invalido", "blob_truncado"])
def test_forma_corrompida_vira_faltante_e_linha_e_apagada(pasta, cache, monkeypatch, modo):
    fn = _malhas_do_cache()
    f_ok, f_bad = _forma_local(1.0), _forma_local(2.0)
    cache.gravar_lote(
        {"k_ok": f_ok, "k_bad": f_bad},
        [_oc("g_ok", "k_ok", _mat(tx=1.0)), _oc("g_b2", "k_bad", _mat(tx=2.0)), _oc("g_b1", "k_bad", _mat(tx=3.0))],
        documento=DOC_A,
    )
    if modo == "checksum":
        [(blob,)] = _sql(pasta, "SELECT vertices FROM formas WHERE chave='k_bad'")
        b = bytearray(blob)
        b[3] ^= 0xFF
        _sql(pasta, "UPDATE formas SET vertices=? WHERE chave='k_bad'", (bytes(b),))
    elif modo == "dtype_invalido":
        _sql(pasta, "UPDATE formas SET dtype_v='int8' WHERE chave='k_bad'")
    else:
        _sql(pasta, "UPDATE formas SET triangulos=? WHERE chave='k_bad'", (b"\x01\x02\x03",))

    assert "k_bad" in cache.formas_presentes(["k_bad"])
    apagadas = []
    real_apagar = cache.apagar_forma
    monkeypatch.setattr(cache, "apagar_forma", lambda chave: (apagadas.append(chave), real_apagar(chave))[1])
    malhas, faltantes = fn(cache, DOC_A, ["g_b2", "g_ok", "g_b1"])
    assert list(malhas) == ["g_ok"] and faltantes == ["g_b1", "g_b2"]
    assert "k_bad" in apagadas and "k_ok" not in apagadas and "k_bad" not in cache.formas_presentes(["k_bad"])
    assert _sql(pasta, "SELECT chave FROM formas ORDER BY chave") == [("k_ok",)]
    assert set(cache.ocorrencias_por_ids(["g_ok", "g_b1", "g_b2"], documento=DOC_A)) == {"g_ok", "g_b1", "g_b2"}
    cache.gravar_forma("k_bad", *f_bad)  # construtor P2 refaz a forma ausente
    malhas2, faltantes2 = fn(cache, DOC_A, ["g_b2", "g_ok", "g_b1"])
    assert list(malhas2) == ["g_b1", "g_b2", "g_ok"] and faltantes2 == []


def test_forma_corrompida_so_escreve_delete_da_forma_ruim(pasta, cache):
    fn = _malhas_do_cache()
    cache.gravar_lote(
        {"k_ok": _forma_local(1.0), "k_bad": _forma_local(2.0)},
        [_oc("g_ok", "k_ok"), _oc("g_bad", "k_bad"), _oc("g_aus", "k_aus")],
        documento=DOC_A,
    )
    _sql(pasta, "UPDATE formas SET dtype_v='ruim' WHERE chave='k_bad'")
    esp = _espiar(cache)
    malhas, faltantes = fn(cache, DOC_A, ["g_ok", "g_bad", "g_aus"])
    assert list(malhas) == ["g_ok"] and faltantes == ["g_aus", "g_bad"]
    dml = [s.lstrip().lower() for s in esp.escritas() if not s.lstrip().lower().startswith(("begin", "commit", "rollback"))]
    assert len(dml) == 1 and dml[0].startswith("delete from formas")
    assert all("ocorrencias" not in s and "memo" not in s for s in dml)


# ---------------------------------------------------------------- copia/imutabilidade e sem transacao de escrita
def test_retorno_independente_do_banco_e_entre_ocorrencias(cache):
    fn = _malhas_do_cache()
    v_loc, t_loc = _forma_local(1.0)
    m1, m2 = _mat(tx=1.0), _mat(tx=5.0)
    cache.gravar_lote({"k_comp": (v_loc, t_loc)}, [_oc("g1", "k_comp", m1), _oc("g2", "k_comp", m2)], documento=DOC_A)
    esp1, esp2 = _mundo(v_loc, m1), _mundo(v_loc, m2)
    malhas, faltantes = fn(cache, DOC_A, ["g1", "g2", "g_falta"])
    v1, t1 = malhas["g1"]
    v2, t2 = malhas["g2"]
    for arr in (v1, t1):
        if arr.flags.writeable:
            arr[...] = 0
        else:
            with pytest.raises(ValueError):
                arr[0, 0] = 0
    malhas.clear()
    faltantes.append("intruso")
    assert np.allclose(v2, esp2, rtol=0.0, atol=1e-12) and np.array_equal(t2, t_loc)
    malhas_nova, faltantes_nova = fn(cache, DOC_A, ["g1", "g2", "g_falta"])
    assert np.allclose(malhas_nova["g1"][0], esp1, rtol=0.0, atol=1e-12)
    assert np.array_equal(malhas_nova["g1"][1], t_loc) and faltantes_nova == ["g_falta"]
    v_db, t_db = cache.ler_forma("k_comp")
    assert np.array_equal(v_db, v_loc) and np.array_equal(t_db, t_loc)


def test_leitura_normal_nunca_abre_transacao_de_escrita(cache):
    fn = _malhas_do_cache()
    cache.gravar_lote(
        {"k1": _forma_local(1.0)},
        [_oc("g1", "k1", _mat(tx=1.0)), _oc("g_sem_forma", "k_nao_existe")],
        documento=DOC_A,
    )
    esp = _espiar(cache)
    for doc, ids in ((DOC_A, ["g1"]), (DOC_A, []), (DOC_A, ["desc"]), (DOC_B, ["g1"]), (DOC_A, ["g1", "g_sem_forma", "desc"])):
        fn(cache, doc, ids)
        assert not cache._con.in_transaction
    assert esp.escritas() == []


# Mutantes cobertos:
#  1. Le por `pavimento` em vez de GlobalId: test_le_pela_lista_de_global_ids_nunca_pela_coluna_pavimento.
#  2. Ignora forma ausente: test_forma_ausente_vai_para_faltantes_sem_apagar_nem_escrever.
#  3. Forma corrompida nao vira faltante ou nao e apagada: test_forma_corrompida_vira_faltante_e_linha_e_apagada,
#     test_apagar_forma_remove_linha_corrompida_e_permite_regravar, test_apagar_forma_remove_so_a_chave_e_preserva_o_resto.
#  4. Matriz nao aplicada / sem R.T / perda float32: test_aplica_matriz_rotacao_translacao_e_escala,
#     test_forma_float32_promovida_para_float64_no_mundo.
#  5. Ordem nao deterministica: test_ordem_deterministica_por_global_id, test_mais_de_500_global_ids_em_blocos.
#  6. Ocorrencia de outro documento vaza: test_ocorrencia_de_outro_documento_nao_vaza_e_vira_faltante.
#  7. GlobalId desconhecido ou ocorrencia corrompida: test_global_id_desconhecido_e_ocorrencia_corrompida_viram_faltantes.
#  8. Lista vazia / duplicados: test_lista_vazia_e_duplicados.
#  9. Retorno compartilha buffer mutavel: test_retorno_independente_do_banco_e_entre_ocorrencias.
# 10. Transacao de escrita fora de apagar_forma: test_leitura_normal_nunca_abre_transacao_de_escrita,
#     test_forma_ausente_vai_para_faltantes_sem_apagar_nem_escrever, test_forma_corrompida_so_escreve_delete_da_forma_ruim.
