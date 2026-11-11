# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T18c-1 (T2): opções `pesados` e `limiar_pesado` de `planta.gerar_planta`. Não editar na implementação.
CONTRATO (`app/openbim_app/desenho/planta.py`; só por nome, depois de `faixas`):
1. Sem `pesados` (None): o pedido ao auxiliar e a chave de cache são IDÊNTICOS aos de hoje (sem as chaves `pesados` e `limiar_pesado`).
2. `pesados="silhueta"`: `pedido["pesados"] == "silhueta"`; com `limiar_pesado` (int) o pedido leva `limiar_pesado`; sem ele, a chave não vai.
3. `pesados` fora de (None, "silhueta"); `limiar_pesado` não int, bool ou < 1 -> ValueError antes de qualquer trabalho (executor não é chamado).
4. `Planta.pesados` = tuple de dicts copiados de `r["pesados"]` da resposta (() se ausente); `Planta.pedido` = o dict enviado (igual ao usado na chave de cache; comparado sem `arquivo`/`threads`, que o auxiliar acrescenta ao enviar).
   Planta vazia (sem elementos): `pesados == ()` e `pedido` None ou {}.
5. Cache: pedidos com e sem `pesados` têm chaves diferentes; acerto de cache devolve os `pesados` da resposta guardada.
6. Com `faixas` junto de `pesados`: os dois vão no pedido.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
from __future__ import annotations

import copy
import inspect

import pytest
import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (autouse)
from s06_t15i_aux import ExecutorEspiao, local, planta

PESADOS = [{"guid": "G1", "id": 11, "faces": 5000}, {"guid": "G2", "id": 12, "faces": 9000}]


class Exec(ExecutorEspiao):
    """Grava o pedido de `desenho`; devolve a resposta real do motor mais `pesados` (a menos que `pesados=None`)."""

    def __init__(self, pesados=PESADOS):
        super().__init__(local.executar)
        self.pesados = pesados
        self.respostas: list[dict] = []

    def __call__(self, pedido):
        r = super().__call__(pedido)
        if pedido.get("op") == "desenho":
            r = dict(r)
            if self.pesados is not None:
                r["pesados"] = copy.deepcopy(self.pesados)
            self.respostas.append(r)
        return r


def nu(ped):
    """O pedido sem o que `auxiliar.preparar` acrescenta ao enviar (caminho do arquivo e threads)."""
    return {k: v for k, v in ped.items() if k not in ("arquivo", "threads")}


def M():
    exigir()
    from openbim_app.desenho import cache
    return cache


def modelo():
    exigir()
    f, pavs = X.estrutura("IFC4")
    p1 = X.caixa(f, "IfcWall", "p1", 0.0, 0.0, 0.0, 2.0, 0.2, 2.0)
    p2 = X.caixa(f, "IfcWall", "p2", 4.0, 0.0, 0.0, 2.0, 0.2, 2.0)
    X.conter(f, pavs[0], p1, p2)
    return f, X.vista(f, "PLANTA", pavs[0], nome="VA")


def gerar(f, gid, ex, **kw):
    return planta.gerar_planta(f, gid, executor=ex, **kw)


def test_assinatura_so_por_nome_padrao_none():
    ps = inspect.signature(planta.gerar_planta).parameters
    for nome in ("pesados", "limiar_pesado"):
        assert nome in ps and ps[nome].kind is inspect.Parameter.KEYWORD_ONLY and ps[nome].default is None


def test_planta_ganha_campos_pesados_e_pedido():
    exigir()
    assert {"pesados", "pedido"} <= {c for c in inspect.signature(planta.Planta).parameters}


@pytest.mark.parametrize("kw", [{}, {"pesados": None}])
def test_sem_pesados_pedido_identico_ao_de_hoje(kw):
    f, gid = modelo()
    ex0, ex = Exec(), Exec()
    gerar(f, gid, ex0)
    p = gerar(f, gid, ex, **kw)
    ped = ex.pedidos_desenho[0]
    assert "pesados" not in ped and "limiar_pesado" not in ped and "pesados" not in p.pedido
    assert nu(ped) == nu(ex0.pedidos_desenho[0])
    assert nu(p.pedido) == nu(ped)


def test_sem_pesados_chave_de_cache_identica(tmp_path):
    c, ex = M().CacheDesenho(tmp_path / "c"), Exec()
    f, gid = modelo()
    gerar(f, gid, ex, cache=c)
    gerar(f, gid, ex, cache=c, pesados=None)
    gerar(f, gid, ex, cache=c, pesados=None, limiar_pesado=None)
    assert len(ex.pedidos_desenho) == 1, "pesados=None tem de cair na mesma chave"


def test_silhueta_vai_ao_pedido_sem_limiar():
    f, gid = modelo()
    ex = Exec()
    p = gerar(f, gid, ex, pesados="silhueta")
    ped = ex.pedidos_desenho[0]
    assert ped["pesados"] == "silhueta" and "limiar_pesado" not in ped
    assert nu(p.pedido) == nu(ped)


@pytest.mark.parametrize("lim", [1, 4000])
def test_silhueta_com_limiar_vai_ao_pedido(lim):
    f, gid = modelo()
    ex = Exec()
    gerar(f, gid, ex, pesados="silhueta", limiar_pesado=lim)
    ped = ex.pedidos_desenho[0]
    assert ped["pesados"] == "silhueta" and ped["limiar_pesado"] == lim and type(ped["limiar_pesado"]) is int


@pytest.mark.parametrize("kw", [
    {"pesados": "x"}, {"pesados": "Silhueta"}, {"pesados": ""}, {"pesados": True}, {"pesados": 1}, {"pesados": ["silhueta"]},
    {"pesados": "silhueta", "limiar_pesado": 0}, {"pesados": "silhueta", "limiar_pesado": -3}, {"pesados": "silhueta", "limiar_pesado": True},
    {"pesados": "silhueta", "limiar_pesado": False}, {"pesados": "silhueta", "limiar_pesado": 2.5}, {"pesados": "silhueta", "limiar_pesado": "4"},
    {"pesados": None, "limiar_pesado": 0}, {"pesados": None, "limiar_pesado": 1.5},
])
def test_valores_invalidos_levantam_antes_de_qualquer_trabalho(kw):
    f, gid = modelo()
    ex = Exec()
    with pytest.raises(ValueError):
        gerar(f, gid, ex, **kw)
    assert ex.chamadas == []


def test_planta_traz_pesados_copiados_da_resposta():
    f, gid = modelo()
    ex = Exec()
    p = gerar(f, gid, ex, pesados="silhueta")
    r = ex.respostas[0]
    assert isinstance(p.pesados, tuple) and p.pesados == tuple(PESADOS) == tuple(r["pesados"])
    assert all(isinstance(d, dict) and d is not o for d, o in zip(p.pesados, r["pesados"]))
    r["pesados"][0]["faces"] = 1  # mexer na resposta não muda a planta
    assert p.pesados[0]["faces"] == 5000


def test_pesados_ausente_da_resposta_vira_tupla_vazia():
    f, gid = modelo()
    p = gerar(f, gid, Exec(pesados=None), pesados="silhueta")
    assert p.pesados == ()
    assert gerar(f, gid, Exec(pesados=None)).pesados == ()


def test_pedido_da_planta_e_o_enviado():
    f, gid = modelo()
    ex = Exec()
    p = gerar(f, gid, ex, pesados="silhueta", limiar_pesado=7)
    assert isinstance(p.pedido, dict) and nu(p.pedido) == nu(ex.pedidos_desenho[0])


def test_planta_vazia_sem_pesados_e_pedido_nulo():
    exigir()
    f, pavs = X.estrutura("IFC4")
    gid = X.vista(f, "PLANTA", pavs[0], nome="VZ")
    p = gerar(f, gid, Exec(), pesados="silhueta")
    assert p.n_paths == 0 and p.pesados == () and p.pedido in (None, {})


def test_chaves_de_cache_diferem_com_e_sem_pesados(tmp_path):
    cache = M()
    c = cache.CacheDesenho(tmp_path / "c")
    f, gid = modelo()
    a = gerar(f, gid, Exec())
    b = gerar(f, gid, Exec(), pesados="silhueta")
    d = gerar(f, gid, Exec(), pesados="silhueta", limiar_pesado=9)
    ch = [c.chave(f, p.pedido) for p in (a, b, d)]
    assert len(set(ch)) == 3
    # a planta usa a mesma chave que `Planta.pedido` dá
    ex = Exec()
    gerar(f, gid, ex, cache=c, pesados="silhueta")
    assert c.obter(ch[1]) is not None and c.obter(ch[0]) is None
    gerar(f, gid, ex, cache=c)
    assert len(ex.pedidos_desenho) == 2, "sem pesados não pode servir a entrada com pesados"


def test_acerto_de_cache_devolve_pesados_guardados(tmp_path):
    c, ex = M().CacheDesenho(tmp_path / "c"), Exec()
    f, gid = modelo()
    p1 = gerar(f, gid, ex, cache=c, pesados="silhueta")
    p2 = gerar(f, gid, ex, cache=c, pesados="silhueta")
    assert len(ex.pedidos_desenho) == 1, "segundo pedido tinha de ser acerto"
    assert p1.pesados == tuple(PESADOS) and p2.pesados == p1.pesados and isinstance(p2.pesados, tuple)
    assert nu(p2.pedido) == nu(p1.pedido)


def test_faixas_e_pesados_juntos_no_pedido():
    f, gid = modelo()
    ex = Exec()
    gerar(f, gid, ex, pesados="silhueta", limiar_pesado=3, faixas=4)
    ped = ex.pedidos_desenho[0]
    assert ped["faixas"] == 4 and ped["pesados"] == "silhueta" and ped["limiar_pesado"] == 3
