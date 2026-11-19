# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T21b (ADR-010, fatia P1): armazenamento do cache de geometria por peça.

Módulo a criar: `geometria/obim_geometria/cache_geometria.py` (o implementador NÃO edita este arquivo).

API pública mínima (contrato):
- constantes `NOME_BANCO` (nome do arquivo sqlite dentro da pasta), `VERSAO_FORMATO`, `VERSAO_MOTOR`,
  `VERSAO_IFCOPENSHELL` (lidas em tempo de chamada, não copiadas em outro lugar).
- `cabecalho_atual(**mudancas) -> dict` com exatamente as chaves versao_formato, versao_motor, versao_ifcopenshell,
  tesselacao (dict), plataforma; `mudancas` troca valores.
- `abrir_cache(pasta, cabecalho=None, relogio=time.time) -> CacheGeometria` (cria a pasta e o banco se faltar; cabeçalho
  diferente do gravado, arquivo corrompido ou truncado = banco refeito vazio; nunca levanta exceção por causa do arquivo).
  `CacheGeometria` serve como gerenciador de contexto e tem `fechar()`.
- `CacheGeometria.gravar_forma(chave, vertices, triangulos)`: vertices float32 ou float64 (n,3), triangulos int32 (m,3);
  outro dtype ou formato = ValueError. `ler_forma(chave) -> (vertices, triangulos) | None`, idêntico bit a bit
  (dtype e bytes), sem pickle (`allow_pickle=False`), nunca levanta exceção na leitura: falha = None.
- `Ocorrencia(global_id, chave_forma, matriz (4,4) float64, caixa (2,3) float64 [min, max no mundo], pavimento, classe_ifc)`
  (dataclass). `gravar_ocorrencia(oc)`, `ler_ocorrencia(global_id) -> Ocorrencia | None`,
  `ocorrencias_do_pavimento(pavimento) -> list[Ocorrencia]` (ordenadas por global_id).
- `gravar_lote(formas: dict[chave, (vertices, triangulos)], ocorrencias: list[Ocorrencia])`: tudo numa transação; um item
  inválido = ValueError e NADA do lote fica gravado.
- `tamanho_bytes() -> int`: soma dos bytes dos blobs de formas (não o tamanho do arquivo).
- `limpar(idade_max_s=None, teto_bytes=None)`: remove formas gravadas há mais de `idade_max_s` (pelo `relogio`) e, depois,
  as mais antigas até `tamanho_bytes() <= teto_bytes`; devolve quantas formas saíram.
- `chave_da_forma(elemento, tesselacao=None) -> str` (sha256 hex de 64 caracteres): hash do conteúdo, por valor, sem ids
  STEP nem GlobalId nem posição: representação do corpo (MappedItem resolvido por conteúdo), unidade do projeto,
  aberturas (HasOpenings, com representação e posição relativa à peça), versão do motor, do ifcopenshell e `tesselacao`.
"""
import dataclasses
import inspect

import ifcopenshell
import ifcopenshell.api
import numpy as np
import pytest

import obim_geometria.cache_geometria as C

_DIA = 86400.0


# ---------------------------------------------------------------- modelos IFC em memória
def _mat(dx=0.0, dy=0.0, dz=0.0):
    m = np.eye(4)
    m[:3, 3] = (dx, dy, dz)
    return m


def _run(f, uso, **kw):
    return ifcopenshell.api.run(uso, f, **kw)


def _novo(lixo=0):
    """IFC4 mínimo. `lixo` cria entidades sem relação antes de tudo, só para deslocar os ids STEP."""
    f = ifcopenshell.file(schema="IFC4")
    for i in range(lixo):
        f.createIfcCartesianPoint((float(i), 0.0, 0.0))
    _run(f, "root.create_entity", ifc_class="IfcProject", name="P")
    _run(f, "unit.assign_unit", length={"is_metric": True, "raw": "METERS"})
    ctx = _run(f, "context.add_context", context_type="Model")
    corpo = _run(f, "context.add_context", context_type="Model", context_identifier="Body",
                 target_view="MODEL_VIEW", parent=ctx)
    return f, corpo


def _parede(f, corpo, comp=4.0, alt=3.0, esp=0.2, mat=None, nome="W"):
    w = _run(f, "root.create_entity", ifc_class="IfcWall", name=nome)
    r = _run(f, "geometry.add_wall_representation", context=corpo, length=comp, height=alt, thickness=esp)
    _run(f, "geometry.assign_representation", product=w, representation=r)
    _run(f, "geometry.edit_object_placement", product=w, matrix=_mat() if mat is None else mat)
    return w


def _abertura(f, corpo, parede, mat, larg=1.0, alt=2.0):
    o = _run(f, "root.create_entity", ifc_class="IfcOpeningElement", name="O")
    r = _run(f, "geometry.add_wall_representation", context=corpo, length=larg, height=alt, thickness=0.4)
    _run(f, "geometry.assign_representation", product=o, representation=r)
    _run(f, "geometry.edit_object_placement", product=o, matrix=mat)
    _run(f, "feature.add_feature", feature=o, element=parede)
    return o


def _tipo_com_instancias(n=2):
    f, corpo = _novo()
    t = _run(f, "root.create_entity", ifc_class="IfcWallType", name="T")
    r = _run(f, "geometry.add_wall_representation", context=corpo, length=4.0, height=3.0, thickness=0.2)
    _run(f, "geometry.assign_representation", product=t, representation=r)
    inst = []
    for i in range(n):
        w = _run(f, "root.create_entity", ifc_class="IfcWall", name=f"W{i}")
        _run(f, "type.assign_type", related_objects=[w], relating_type=t)
        _run(f, "geometry.edit_object_placement", product=w, matrix=_mat(dx=10.0 * i))
        inst.append(w)
    return f, t, inst


def _forma(n=4, dtype=np.float64, semente=0):
    rng = np.random.default_rng(semente)
    v = rng.random((n, 3)).astype(dtype)
    t = (np.arange(n * 3) % n).reshape(-1, 3).astype(np.int32)
    return v, t


def _oc(gid="2abc", chave="k1", pav="P1", classe="IfcWall"):
    return C.Ocorrencia(gid, chave, _mat(1e6, 2e6, 3.0), np.array([[1e6, 2e6, 3.0], [1e6 + 1, 2e6 + 1, 6.0]]),
                        pav, classe)


@pytest.fixture
def pasta(tmp_path):
    return tmp_path / "geometria"


# ---------------------------------------------------------------- forma: round trip
@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_forma_round_trip_bit_a_bit(pasta, dtype):
    v, t = _forma(50, dtype)
    with C.abrir_cache(pasta) as c:
        c.gravar_forma("k", v, t)
    with C.abrir_cache(pasta) as c:  # reabre: veio do disco
        v2, t2 = c.ler_forma("k")
    assert v2.dtype == v.dtype and t2.dtype == np.int32
    assert v2.tobytes() == v.tobytes() and t2.tobytes() == t.tobytes()


def test_forma_ausente_e_dtype_invalido(pasta):
    v, t = _forma()
    with C.abrir_cache(pasta) as c:
        assert c.ler_forma("nao-existe") is None
        with pytest.raises(ValueError):
            c.gravar_forma("k", v, t.astype(np.int64))
        with pytest.raises(ValueError):
            c.gravar_forma("k", v.astype(np.float16), t)
        with pytest.raises(ValueError):
            c.gravar_forma("k", v[:, :2], t)
        assert c.ler_forma("k") is None


def test_sem_pickle_no_codigo():
    src = inspect.getsource(C)
    assert "pickle" not in src.lower().replace("allow_pickle=false", "")
    if "np.load" in src or "numpy.load" in src:
        assert "allow_pickle=False" in src


# ---------------------------------------------------------------- ocorrência
def test_ocorrencia_round_trip(pasta):
    a, b = _oc("g2", "k1", "P1", "IfcSlab"), _oc("g1", "k2", "P1", "IfcWall")
    with C.abrir_cache(pasta) as c:
        c.gravar_ocorrencia(a)
        c.gravar_ocorrencia(b)
        c.gravar_ocorrencia(_oc("g3", "k1", "P2"))
    with C.abrir_cache(pasta) as c:
        r = c.ler_ocorrencia("g2")
        assert c.ler_ocorrencia("nada") is None
        lista = c.ocorrencias_do_pavimento("P1")
    assert dataclasses.asdict(r).keys() == dataclasses.asdict(a).keys()
    assert (r.global_id, r.chave_forma, r.pavimento, r.classe_ifc) == ("g2", "k1", "P1", "IfcSlab")
    assert r.matriz.dtype == np.float64 and r.matriz.tobytes() == a.matriz.tobytes()  # georreferenciado: sem perda
    assert r.caixa.tobytes() == a.caixa.tobytes()
    assert [o.global_id for o in lista] == ["g1", "g2"]


def test_copias_dividem_a_forma(pasta):
    v, t = _forma()
    with C.abrir_cache(pasta) as c:
        c.gravar_forma("k", v, t)
        antes = c.tamanho_bytes()
        for i in range(5):
            c.gravar_ocorrencia(_oc(f"g{i}", "k"))
        assert c.tamanho_bytes() == antes
        assert len(c.ocorrencias_do_pavimento("P1")) == 5


# ---------------------------------------------------------------- cabeçalho
def test_cabecalho_tem_os_campos():
    h = C.cabecalho_atual()
    assert set(h) == {"versao_formato", "versao_motor", "versao_ifcopenshell", "tesselacao", "plataforma"}
    assert h["versao_ifcopenshell"] == C.VERSAO_IFCOPENSHELL and h["versao_motor"] == C.VERSAO_MOTOR
    assert h["plataforma"] == C.cabecalho_atual()["plataforma"]


@pytest.mark.parametrize("campo,valor", [("versao_formato", "outra"), ("versao_motor", "outra"),
                                         ("versao_ifcopenshell", "0.0.1"), ("tesselacao", {"deflexao": 0.5}),
                                         ("plataforma", "outro-so")])
def test_cabecalho_diferente_invalida_tudo(pasta, campo, valor):
    v, t = _forma()
    with C.abrir_cache(pasta) as c:
        c.gravar_forma("k", v, t)
        c.gravar_ocorrencia(_oc())
    with C.abrir_cache(pasta, C.cabecalho_atual()) as c:  # mesmo cabeçalho: continua
        assert c.ler_forma("k") is not None
    with C.abrir_cache(pasta, C.cabecalho_atual(**{campo: valor})) as c:
        assert c.ler_forma("k") is None and c.ler_ocorrencia("2abc") is None
        assert c.tamanho_bytes() == 0 and c.ocorrencias_do_pavimento("P1") == []
        c.gravar_forma("k2", v, t)  # banco novo é gravável
    with C.abrir_cache(pasta, C.cabecalho_atual(**{campo: valor})) as c:
        assert c.ler_forma("k2") is not None


def test_versao_do_motor_do_modulo_invalida(pasta, monkeypatch):
    v, t = _forma()
    with C.abrir_cache(pasta) as c:
        c.gravar_forma("k", v, t)
    monkeypatch.setattr(C, "VERSAO_MOTOR", "motor-novo")
    with C.abrir_cache(pasta) as c:
        assert c.ler_forma("k") is None


# ---------------------------------------------------------------- corrompido, truncado
def _caminho(pasta):
    return pasta / C.NOME_BANCO


def _refaz_e_funciona(pasta, chave_morta):
    with C.abrir_cache(pasta) as c:  # não levanta
        assert c.ler_forma(chave_morta) is None and c.ler_ocorrencia("2abc") is None
        assert c.ocorrencias_do_pavimento("P1") == []
        v, t = _forma(semente=7)
        c.gravar_forma("novo", v, t)
        assert c.ler_forma("novo")[0].tobytes() == v.tobytes()


def test_lixo_no_lugar_do_banco(pasta):
    pasta.mkdir()
    _caminho(pasta).write_bytes(b"isto nao e sqlite " * 500)
    _refaz_e_funciona(pasta, "k")


def test_arquivo_vazio(pasta):
    pasta.mkdir()
    _caminho(pasta).write_bytes(b"")
    _refaz_e_funciona(pasta, "k")


@pytest.mark.parametrize("fracao", [0.0, 0.01, 0.5])
def test_banco_truncado(pasta, fracao):
    v, t = _forma(20000)  # centenas de KB: vários blocos do sqlite
    with C.abrir_cache(pasta) as c:
        c.gravar_forma("k", v, t)
        c.gravar_ocorrencia(_oc())
    p = _caminho(pasta)
    dados = p.read_bytes()
    p.write_bytes(dados[:int(len(dados) * fracao)])
    _refaz_e_funciona(pasta, "k")


def test_bytes_alterados_no_meio_nunca_levantam(pasta):
    v, t = _forma(20000)
    with C.abrir_cache(pasta) as c:
        c.gravar_forma("k", v, t)
    p = _caminho(pasta)
    dados = bytearray(p.read_bytes())
    meio = len(dados) // 2
    dados[meio:meio + 4096] = b"\xff" * 4096
    p.write_bytes(bytes(dados))
    with C.abrir_cache(pasta) as c:
        r = c.ler_forma("k")  # ou None, ou o dado íntegro; nunca exceção nem dado trocado
        assert r is None or (r[0].tobytes() == v.tobytes() and r[1].tobytes() == t.tobytes())


# ---------------------------------------------------------------- transação
def test_lote_invalido_nao_deixa_forma_pela_metade(pasta):
    v, t = _forma()
    ruim = (v, t.astype(np.int64))
    with C.abrir_cache(pasta) as c:
        with pytest.raises(ValueError):
            c.gravar_lote({"a": (v, t), "b": ruim}, [_oc("g1", "a")])
        assert c.ler_forma("a") is None and c.ler_ocorrencia("g1") is None and c.tamanho_bytes() == 0
        c.gravar_lote({"a": (v, t), "b": (v, t)}, [_oc("g1", "a"), _oc("g2", "b")])
        assert c.ler_forma("b") is not None and c.ler_ocorrencia("g2") is not None


def test_lote_gravado_sobrevive_a_queda_sem_fechar(pasta):
    """Processo morto depois do lote (sem fechar): o lote já está no disco; nada pela metade."""
    v, t = _forma()
    c = C.abrir_cache(pasta)
    c.gravar_lote({"a": (v, t)}, [_oc("g1", "a")])
    with C.abrir_cache(pasta) as c2:  # segundo leitor, sem fechar o primeiro
        r = c2.ler_forma("a")
        assert r is not None and r[0].tobytes() == v.tobytes()
        assert c2.ler_ocorrencia("g1") is not None
    c.fechar()


# ---------------------------------------------------------------- limpeza
def test_limpeza_por_idade(pasta):
    t_ = [0.0]
    v, t = _forma()
    with C.abrir_cache(pasta, relogio=lambda: t_[0]) as c:
        c.gravar_forma("velha", v, t)
        t_[0] = 29 * _DIA
        c.gravar_forma("meia", v, t)
        t_[0] = 31 * _DIA
        c.gravar_forma("nova", v, t)
        assert c.limpar(idade_max_s=30 * _DIA) == 1  # só a de 31 dias
        assert c.ler_forma("velha") is None
        assert c.ler_forma("meia") is not None and c.ler_forma("nova") is not None
        assert c.limpar(idade_max_s=30 * _DIA) == 0


def test_limpeza_por_teto_tira_o_mais_antigo_primeiro(pasta):
    t_ = [0.0]
    with C.abrir_cache(pasta, relogio=lambda: t_[0]) as c:
        for i, k in enumerate(["a", "b", "c"]):
            t_[0] = float(i)
            c.gravar_forma(k, *_forma(100, semente=i))
        um = c.tamanho_bytes() // 3
        assert c.limpar(teto_bytes=int(2.5 * um)) == 1
        assert c.ler_forma("a") is None and c.ler_forma("b") is not None and c.ler_forma("c") is not None
        assert c.tamanho_bytes() <= 2.5 * um
        assert c.limpar(teto_bytes=0) == 2 and c.tamanho_bytes() == 0
        assert c.limpar() == 0


def test_limpeza_sem_criterio_nao_apaga(pasta):
    with C.abrir_cache(pasta) as c:
        c.gravar_forma("a", *_forma())
        assert c.limpar() == 0 and c.ler_forma("a") is not None


# ---------------------------------------------------------------- chave da forma
def _k(e, **kw):
    return C.chave_da_forma(e, **kw)


def test_chave_formato_e_determinismo():
    f, corpo = _novo()
    w = _parede(f, corpo)
    ks = {_k(w) for _ in range(3)}
    assert len(ks) == 1
    k = ks.pop()
    assert isinstance(k, str) and len(k) == 64 and int(k, 16) >= 0
    f2, corpo2 = _novo()
    assert _k(_parede(f2, corpo2)) == k  # outro arquivo, mesmo conteúdo, outros GlobalIds


def test_chave_muda_com_a_geometria():
    f, corpo = _novo()
    base = _k(_parede(f, corpo))
    assert _k(_parede(f, corpo, comp=4.5)) != base
    assert _k(_parede(f, corpo, esp=0.25)) != base


def test_chave_ignora_posicao_e_nome():
    f, corpo = _novo()
    w = _parede(f, corpo)
    base = _k(w)
    _run(f, "geometry.edit_object_placement", product=w, matrix=_mat(1e6, 2e6, 3.0))
    assert _k(w) == base  # só a posição mudou
    w.Name = "outro nome"
    assert _k(w) == base


def test_chave_ignora_renumeracao_step():
    f, corpo = _novo()
    w = _parede(f, corpo)
    _abertura(f, corpo, w, _mat(1.0, 0.0, 0.0))
    base = _k(w)
    g, corpo_g = _novo(lixo=37)  # mesmo conteúdo, ids STEP deslocados
    wg = _parede(g, corpo_g)
    _abertura(g, corpo_g, wg, _mat(1.0, 0.0, 0.0))
    assert wg.id() != w.id() and _k(wg) == base


def test_chave_sobrevive_a_gravar_e_reabrir(tmp_path):
    f, corpo = _novo(lixo=5)
    w = _parede(f, corpo)
    _abertura(f, corpo, w, _mat(1.0, 0.0, 0.0))
    base, gid = _k(w), w.GlobalId
    f.write(str(tmp_path / "a.ifc"))
    g = ifcopenshell.open(str(tmp_path / "a.ifc"))
    assert _k(g.by_guid(gid)) == base


def test_abertura_movida_muda_a_chave():
    f, corpo = _novo()
    w = _parede(f, corpo)
    o = _abertura(f, corpo, w, _mat(1.0, 0.0, 0.0))
    base = _k(w)
    _run(f, "geometry.edit_object_placement", product=o, matrix=_mat(2.0, 0.0, 0.0))
    assert _k(w) != base


def test_abertura_trocada_de_tamanho_muda_a_chave():
    f, corpo = _novo()
    w = _parede(f, corpo)
    _abertura(f, corpo, w, _mat(1.0, 0.0, 0.0), larg=1.0)
    f2, corpo2 = _novo()
    w2 = _parede(f2, corpo2)
    _abertura(f2, corpo2, w2, _mat(1.0, 0.0, 0.0), larg=1.2)
    assert _k(w) != _k(w2)


def test_abertura_adicionada_muda_a_chave():
    f, corpo = _novo()
    w = _parede(f, corpo)
    sem = _k(w)
    _abertura(f, corpo, w, _mat(1.0, 0.0, 0.0))
    com = _k(w)
    assert com != sem
    _abertura(f, corpo, w, _mat(2.5, 0.0, 0.0))
    assert _k(w) not in (sem, com)


def test_parede_e_abertura_movidas_juntas_mantem_a_chave():
    f, corpo = _novo()
    w = _parede(f, corpo)
    o = _abertura(f, corpo, w, _mat(1.0, 0.0, 0.0))
    base = _k(w)
    _run(f, "geometry.edit_object_placement", product=w, matrix=_mat(10.0, 20.0, 0.0))
    _run(f, "geometry.edit_object_placement", product=o, matrix=_mat(11.0, 20.0, 0.0))
    assert _k(w) == base  # posição relativa igual


def test_item_mapeado_por_conteudo():
    f, t, (a, b) = _tipo_com_instancias(2)
    assert a.Representation.Representations[0].Items[0].is_a("IfcMappedItem")
    base = _k(a)
    assert _k(b) == base  # duas instâncias do mesmo tipo, posições diferentes
    solido = next(e for e in f.traverse(t) if e.is_a("IfcExtrudedAreaSolid"))
    solido.Depth = solido.Depth + 1.0  # edita o tipo
    assert _k(a) != base and _k(a) == _k(b)


def test_item_mapeado_igual_a_copia_em_outro_arquivo():
    f, t, (a, _) = _tipo_com_instancias(2)
    g, _t, (c, _) = _tipo_com_instancias(2)
    assert _k(a) == _k(c)


def test_unidade_muda_a_chave():
    f, corpo = _novo()
    w = _parede(f, corpo)
    base = _k(w)
    # troca só o prefixo da unidade (m -> mm): os números da peça ficam iguais, o tamanho real muda
    next(u for u in f.by_type("IfcSIUnit") if u.UnitType == "LENGTHUNIT").Prefix = "MILLI"
    assert _k(w) != base


def test_tesselacao_e_versoes_entram_na_chave(monkeypatch):
    f, corpo = _novo()
    w = _parede(f, corpo)
    base = _k(w)
    assert _k(w, tesselacao={"deflexao": 0.5}) != base
    assert _k(w, tesselacao={"deflexao": 0.5}) == _k(w, tesselacao={"deflexao": 0.5})
    monkeypatch.setattr(C, "VERSAO_MOTOR", "motor-novo")
    assert _k(w) != base
    monkeypatch.undo()
    assert _k(w) == base
    monkeypatch.setattr(C, "VERSAO_IFCOPENSHELL", "0.0.1")
    assert _k(w) != base


def test_plataforma_e_texto():
    assert isinstance(C.cabecalho_atual()["plataforma"], str) and C.cabecalho_atual()["plataforma"]
