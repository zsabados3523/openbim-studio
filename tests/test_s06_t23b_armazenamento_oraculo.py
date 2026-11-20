# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T23b: extensão do armazenamento da P1 para o construtor (ADR-010, P2).

Interface exata (cartão T23b): VERSAO_FORMATO == "2"; documento_de(caminho); CacheGeometria.em_memoria;
parâmetro `documento=""` em gravar_ocorrencia/ler_ocorrencia/ocorrencias_do_pavimento/gravar_lote;
formas_presentes(chaves); ocorrencias_por_ids(ids, documento=""); memo_ler(documento, assinatura);
gravar_lote(..., memo=(assinatura, {id_step: chave})). Dados sintéticos; sem IFC.
O implementador NÃO edita este arquivo nem os testes da T21b.
"""
import hashlib
import os
import re
import sqlite3

import numpy as np
import pytest

import obim_geometria.cache_geometria as C
from obim_geometria.cache_geometria import Ocorrencia, abrir_cache, cabecalho_atual


# ---------------------------------------------------------------- auxiliares
def _mat(dx=0.0):
    m = np.eye(4)
    m[0, 3] = dx
    return m


def _oc(gid, chave="k0", dx=0.0, pav="P1", classe="IfcWall"):
    return Ocorrencia(gid, chave, _mat(dx), np.array([[0.0, 0, 0], [1, 1, 1]]), pav, classe)


def _forma(n=1):
    v = np.array([[0, 0, 0], [1, 0, 0], [0, 1, float(n)]], dtype=np.float64)
    return v, np.array([[0, 1, 2]], dtype=np.int32)


def _db(pasta):
    return os.path.join(str(pasta), C.NOME_BANCO)


def _sql(pasta, consulta, args=()):
    con = sqlite3.connect(_db(pasta))
    try:
        r = con.execute(consulta, args).fetchall()
        con.commit()
        return r
    finally:
        con.close()


class _Espiao:
    """Intercala a conexão: registra consultas e pode falhar escritas numa tabela (após o BEGIN)."""

    def __init__(self, real, falhar_tabela=None):
        self.real, self.falhar_tabela, self.chamadas = real, falhar_tabela, []

    def _reg(self, sql, params):
        self.chamadas.append((sql, max(len(params), sql.count("?"))))
        baixo = sql.lower()
        escrita = baixo.lstrip().startswith(("insert", "delete", "update", "replace"))
        if self.falhar_tabela and escrita and self.falhar_tabela in baixo:
            raise sqlite3.OperationalError("falha injetada")

    def execute(self, sql, params=()):
        self._reg(sql, params)
        return self.real.execute(sql, params)

    def executemany(self, sql, seq):
        seq = list(seq)
        self._reg(sql, seq[0] if seq else ())
        return self.real.executemany(sql, seq)

    def __getattr__(self, nome):
        return getattr(self.real, nome)


def _espiar(cache, falhar_tabela=None):
    cache._con = _Espiao(cache._con, falhar_tabela)
    return cache._con


@pytest.fixture
def pasta(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def cache(pasta):
    with abrir_cache(pasta) as c:
        yield c


# ---------------------------------------------------------------- versão e documento_de
def test_versao_formato_e_2_e_vai_no_cabecalho():  # mutante 7
    assert C.VERSAO_FORMATO == "2"
    assert cabecalho_atual()["versao_formato"] == "2"


def test_banco_da_versao_1_e_recriado_vazio(pasta):  # mutante 7
    with abrir_cache(pasta, cabecalho_atual(versao_formato="1")) as c:
        c.gravar_forma("velha", *_forma())
    with abrir_cache(pasta) as c:
        assert c.ler_forma("velha") is None
        assert c.em_memoria is False
        c.gravar_ocorrencia(_oc("a"), documento="d")
        assert c.ler_ocorrencia("a", documento="d") is not None


_ESQUEMA_V1 = (
    "CREATE TABLE meta (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);"
    "CREATE TABLE formas (chave TEXT PRIMARY KEY, dtype_v TEXT NOT NULL, vertices BLOB NOT NULL, "
    "triangulos BLOB NOT NULL, checksum BLOB NOT NULL, gravado_em REAL NOT NULL);"
    "CREATE TABLE ocorrencias (global_id TEXT PRIMARY KEY, chave_forma TEXT NOT NULL, matriz BLOB NOT NULL, "
    "caixa BLOB NOT NULL, pavimento TEXT, classe_ifc TEXT NOT NULL, checksum BLOB NOT NULL);"
)


def test_esquema_antigo_com_cabecalho_atual_tambem_e_recriado(pasta):
    pasta.mkdir()
    con = sqlite3.connect(_db(pasta))
    con.executescript(_ESQUEMA_V1)
    con.execute("INSERT INTO meta VALUES ('cabecalho', ?)", (C._json_canonico(cabecalho_atual()),))
    con.commit()
    con.close()
    with abrir_cache(pasta) as c:
        assert c.em_memoria is False
        c.gravar_ocorrencia(_oc("a"), documento="d")
        assert c.ler_ocorrencia("a", documento="d").global_id == "a"
    assert [r[1] for r in _sql(pasta, "PRAGMA table_info(memo)")] == ["documento", "id_step", "assinatura", "chave"]


def test_integridade_conhece_a_tabela_memo(pasta):
    with abrir_cache(pasta) as c:
        c.gravar_forma("f", *_forma())
    _sql(pasta, "DROP TABLE memo")
    with abrir_cache(pasta) as c:  # sem memo = banco inválido, refeito
        assert c.ler_forma("f") is None
        assert c.memo_ler("d", "s") == {}
    assert _sql(pasta, "SELECT name FROM sqlite_master WHERE name='memo'") == [("memo",)]


def test_esquema_novo_chaves_e_indice(pasta, cache):
    cols = {r[1]: r for r in _sql(pasta, "PRAGMA table_info(ocorrencias)")}
    assert cols["documento"][3] == 1 and cols["documento"][4] == "''"
    assert cols["documento"][5] > 0 and cols["global_id"][5] > 0
    assert {c for c, r in cols.items() if r[5] > 0} == {"documento", "global_id"}
    memo = {r[1]: r for r in _sql(pasta, "PRAGMA table_info(memo)")}
    assert list(memo) == ["documento", "id_step", "assinatura", "chave"]
    assert {c for c, r in memo.items() if r[5] > 0} == {"documento", "id_step"}
    indices = [[i[2] for i in _sql(pasta, f"PRAGMA index_info('{n[1]}')")] for n in _sql(pasta, "PRAGMA index_list(ocorrencias)")]
    assert ["documento", "pavimento", "global_id"] in indices


def test_ocorrencia_nao_mudou():
    assert [f for f in Ocorrencia.__dataclass_fields__] == [
        "global_id", "chave_forma", "matriz", "caixa", "pavimento", "classe_ifc"]


def test_documento_de(tmp_path, monkeypatch):
    p = tmp_path / "sub" / "Casa.ifc"
    esperado = hashlib.sha256(os.path.normcase(str(p.resolve())).encode("utf-8")).hexdigest()
    assert C.documento_de(p) == C.documento_de(str(p)) == esperado
    assert re.fullmatch(r"[0-9a-f]{64}", esperado)
    monkeypatch.chdir(tmp_path)
    assert C.documento_de("sub/../sub/Casa.ifc") == esperado  # relativo e normalizado
    assert C.documento_de(tmp_path / "sub" / "Outra.ifc") != esperado


# ---------------------------------------------------------------- em_memoria
def test_em_memoria_falso_no_disco_e_verdadeiro_na_queda(tmp_path):  # mutante 2
    with abrir_cache(tmp_path / "ok") as c:
        assert c.em_memoria is False
    (tmp_path / "arq").write_text("x")  # a "pasta" é um arquivo: mkdir falha
    with abrir_cache(tmp_path / "arq") as c:
        assert c.em_memoria is True
        c.gravar_ocorrencia(_oc("a"))  # a queda continua utilizável
        assert c.ler_ocorrencia("a") is not None
    (tmp_path / "dir" / C.NOME_BANCO).mkdir(parents=True)  # o banco é um diretório: não dá para apagar nem criar
    with abrir_cache(tmp_path / "dir") as c:
        assert c.em_memoria is True


# ---------------------------------------------------------------- documento nas ocorrências
def test_mesmo_global_id_em_dois_documentos_nao_se_mistura(cache):  # mutante 1
    cache.gravar_ocorrencia(_oc("g", dx=1.0), documento="A")
    cache.gravar_ocorrencia(_oc("g", dx=2.0), documento="B")
    assert cache.ler_ocorrencia("g", documento="A").matriz[0, 3] == 1.0
    assert cache.ler_ocorrencia("g", documento="B").matriz[0, 3] == 2.0
    assert cache.ler_ocorrencia("g") is None and cache.ler_ocorrencia("g", documento="C") is None
    for d, dx in (("A", 1.0), ("B", 2.0)):
        [o] = cache.ocorrencias_do_pavimento("P1", documento=d)
        assert o.matriz[0, 3] == dx
        assert cache.ocorrencias_por_ids(["g"], documento=d)["g"].matriz[0, 3] == dx
    assert cache.ocorrencias_do_pavimento("P1") == []


def test_padrao_sem_documento_continua_valendo(cache):
    cache.gravar_ocorrencia(_oc("g", dx=3.0))
    cache.gravar_lote({}, [_oc("h", dx=4.0)])
    assert cache.ler_ocorrencia("g", documento="").matriz[0, 3] == 3.0
    assert [o.global_id for o in cache.ocorrencias_do_pavimento("P1")] == ["g", "h"]


def test_gravar_lote_com_documento(cache):
    cache.gravar_lote({"k0": _forma()}, [_oc("g", dx=1.0), _oc("h")], documento="A")
    cache.gravar_lote({}, [_oc("g", dx=9.0)], documento="B")
    assert [o.global_id for o in cache.ocorrencias_do_pavimento("P1", documento="A")] == ["g", "h"]
    assert cache.ler_ocorrencia("g", documento="A").matriz[0, 3] == 1.0
    assert [o.global_id for o in cache.ocorrencias_do_pavimento("P1", documento="B")] == ["g"]
    assert cache.ler_ocorrencia("h") is None


def test_documento_entra_no_checksum(pasta, cache):  # mutante extra
    cache.gravar_ocorrencia(_oc("g"), documento="A")
    cache.gravar_ocorrencia(_oc("h"), documento="A")
    cache.gravar_ocorrencia(_oc("h"), documento="B")
    _sql(pasta, "UPDATE ocorrencias SET documento='X' WHERE global_id='g'")  # troca só o documento, checksum fica
    assert cache.ler_ocorrencia("g", documento="X") is None
    assert cache.ocorrencias_por_ids(["g"], documento="X") == {}
    assert [o.global_id for o in cache.ocorrencias_do_pavimento("P1", documento="X")] == []
    assert cache.ler_ocorrencia("g", documento="A") is None
    assert cache.ler_ocorrencia("h", documento="A") is not None  # as outras seguem lidas


# ---------------------------------------------------------------- formas_presentes
def test_formas_presentes_so_as_existentes(cache):  # mutante 3
    for k in ("a", "b", "c"):
        cache.gravar_forma(k, *_forma())
    assert cache.formas_presentes(["a", "c", "x", "y"]) == {"a", "c"}
    assert cache.formas_presentes(["x"]) == set() and cache.formas_presentes([]) == set()
    assert cache.formas_presentes(iter(["b", "b"])) == {"b"}
    assert isinstance(cache.formas_presentes(["a"]), set)


def test_formas_presentes_nao_le_blob_e_usa_blocos_de_500(cache):  # mutantes 3 e 4
    cache.gravar_lote({f"k{i}": _forma() for i in range(0, 1200, 3)}, [])
    espiao = _espiar(cache)
    pedidas = [f"k{i}" for i in range(1200)]
    achadas = cache.formas_presentes(pedidas)
    assert achadas == {f"k{i}" for i in range(0, 1200, 3)}
    consultas = [(s, n) for s, n in espiao.chamadas if "select" in s.lower()]
    assert len(consultas) >= 3
    assert max(n for _, n in consultas) <= 500
    for s, _ in consultas:
        baixo = s.lower()
        assert "vertices" not in baixo and "triangulos" not in baixo


# ---------------------------------------------------------------- ocorrencias_por_ids
def test_ocorrencias_por_ids_5000_em_blocos_de_500(cache):  # mutante 4
    ocs = [_oc(f"g{i:05d}", dx=float(i)) for i in range(5000)]
    cache.gravar_lote({}, ocs, documento="A")
    espiao = _espiar(cache)
    pedidos = [o.global_id for o in ocs] + ["inexistente"]
    achadas = cache.ocorrencias_por_ids(pedidos, documento="A")
    assert len(achadas) == 5000 and "inexistente" not in achadas
    assert achadas["g04999"].matriz[0, 3] == 4999.0 and achadas["g00000"].global_id == "g00000"
    selects = [n for s, n in espiao.chamadas if "select" in s.lower()]
    assert len(selects) >= 10 and max(selects) <= 501  # 500 ids + o parametro `documento`
    assert cache.ocorrencias_por_ids(pedidos, documento="outro") == {}
    assert cache.ocorrencias_por_ids([]) == {}


def test_ocorrencias_por_ids_devolve_dict_de_ocorrencia(cache):
    cache.gravar_ocorrencia(_oc("a", dx=1.0, pav=None, classe="IfcDoor"), documento="A")
    r = cache.ocorrencias_por_ids(["a", "a"], documento="A")
    assert list(r) == ["a"] and isinstance(r["a"], Ocorrencia)
    assert r["a"].pavimento is None and r["a"].classe_ifc == "IfcDoor" and r["a"].matriz.dtype == np.float64


def test_ocorrencias_por_ids_linha_corrompida_fica_fora(pasta, cache):  # mutante 5
    cache.gravar_lote({}, [_oc("a", dx=1.0), _oc("b", dx=2.0), _oc("c", dx=3.0)], documento="A")
    [(blob,)] = _sql(pasta, "SELECT matriz FROM ocorrencias WHERE global_id='b'")
    ruim = bytearray(blob)
    ruim[10] ^= 0xFF  # mesmo tamanho, checksum não bate
    _sql(pasta, "UPDATE ocorrencias SET matriz=? WHERE global_id='b'", (bytes(ruim),))
    assert cache.ler_ocorrencia("b", documento="A") is None
    assert set(cache.ocorrencias_por_ids(["a", "b", "c"], documento="A")) == {"a", "c"}


# ---------------------------------------------------------------- memo
def test_memo_ida_e_volta_por_documento_e_assinatura(cache):  # mutante 6
    cache.gravar_lote({}, [_oc("a")], documento="A", memo=("s1", {10: "ca", 11: "cb"}))
    cache.gravar_lote({}, [_oc("b")], documento="B", memo=("s1", {10: "outro"}))
    assert cache.memo_ler("A", "s1") == {10: "ca", 11: "cb"}
    assert cache.memo_ler("B", "s1") == {10: "outro"}
    assert cache.memo_ler("A", "s2") == {}
    assert cache.memo_ler("C", "s1") == {}
    assert all(isinstance(k, int) for k in cache.memo_ler("A", "s1"))


def test_memo_mesma_assinatura_acumula_e_atualiza(cache):
    cache.gravar_lote({}, [], documento="A", memo=("s1", {1: "x", 2: "y"}))
    cache.gravar_lote({}, [], documento="A", memo=("s1", {2: "y2", 3: "z"}))
    assert cache.memo_ler("A", "s1") == {1: "x", 2: "y2", 3: "z"}


def test_memo_de_assinatura_velha_e_apagado_so_do_documento(pasta, cache):  # mutante 6
    cache.gravar_lote({}, [], documento="A", memo=("velha", {1: "x", 2: "y"}))
    cache.gravar_lote({}, [], documento="B", memo=("velha", {1: "b"}))
    cache.gravar_lote({}, [], documento="A", memo=("nova", {3: "z"}))
    assert cache.memo_ler("A", "nova") == {3: "z"}
    assert cache.memo_ler("A", "velha") == {}
    assert _sql(pasta, "SELECT id_step FROM memo WHERE documento='A'") == [(3,)]  # apagado de fato
    assert cache.memo_ler("B", "velha") == {1: "b"}


def test_gravar_lote_sem_memo_nao_mexe_no_memo(cache):
    cache.gravar_lote({}, [], documento="A", memo=("s", {1: "x"}))
    cache.gravar_lote({"k": _forma()}, [_oc("a")], documento="A")
    assert cache.memo_ler("A", "s") == {1: "x"}


def test_lote_so_com_memo_e_valido(cache):
    cache.gravar_lote({}, [], memo=("s", {}))  # memo vazio não quebra
    cache.gravar_lote({}, [], documento="A", memo=("s", {5: "k"}))
    assert cache.memo_ler("A", "s") == {5: "k"}


def _contagens(pasta):
    return [_sql(pasta, f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("formas", "ocorrencias", "memo")]


@pytest.mark.parametrize("tabela", ["ocorrencias", "formas", "memo"])
def test_memo_na_mesma_transacao_do_lote(pasta, cache, tabela):  # mutante 6
    cache.gravar_lote({}, [], documento="A", memo=("velha", {1: "x"}))
    antes = _contagens(pasta)
    espiao = _espiar(cache, falhar_tabela=tabela)
    with pytest.raises(sqlite3.OperationalError):
        cache.gravar_lote({"k": _forma()}, [_oc("a")], documento="A", memo=("nova", {2: "y"}))
    assert _contagens(pasta) == antes  # nada do lote, memo velho intacto (o DELETE também voltou)
    espiao.falhar_tabela = None
    assert cache.memo_ler("A", "velha") == {1: "x"} and cache.memo_ler("A", "nova") == {}
    cache.gravar_lote({"k": _forma()}, [_oc("a")], documento="A", memo=("nova", {2: "y"}))  # cache segue usável
    assert cache.memo_ler("A", "nova") == {2: "y"}


def test_lote_invalido_nao_grava_memo(pasta, cache):
    ruim = Ocorrencia("", "k", _mat(), np.zeros((2, 3)), "P1", "IfcWall")
    with pytest.raises(ValueError):
        cache.gravar_lote({}, [_oc("a"), ruim], documento="A", memo=("s", {1: "x"}))
    assert _contagens(pasta) == [0, 0, 0]


# Mutantes cobertos:
#  1. ocorrência sem documento na chave (mesmo GlobalId em 2 documentos se mistura): test_mesmo_global_id_*,
#     test_gravar_lote_com_documento, test_padrao_sem_documento_*, test_esquema_novo_chaves_e_indice.
#  2. em_memoria sempre falso (ou sempre verdadeiro): test_em_memoria_falso_no_disco_e_verdadeiro_na_queda.
#  3. formas_presentes devolve todas as pedidas ou lê blob (espião no SELECT): test_formas_presentes_*.
#  4. IN único com mais de 500 parâmetros (5.000 ids, 1.200 chaves): test_ocorrencias_por_ids_5000_*,
#     test_formas_presentes_nao_le_blob_e_usa_blocos_de_500.
#  5. linha corrompida devolvida em ocorrencias_por_ids: test_ocorrencias_por_ids_linha_corrompida_fica_fora.
#  6. memo de outra assinatura devolvido; memo velho não apagado; memo fora da transação do lote:
#     test_memo_ida_e_volta_*, test_memo_de_assinatura_velha_*, test_memo_na_mesma_transacao_do_lote,
#     test_lote_invalido_nao_grava_memo.
#  7. VERSAO_FORMATO inalterado / banco v1 lido como válido: test_versao_formato_*, test_banco_da_versao_1_*,
#     test_esquema_antigo_*, test_integridade_conhece_a_tabela_memo.
#  Extra: documento fora do checksum: test_documento_entra_no_checksum.
