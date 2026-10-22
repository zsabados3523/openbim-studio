# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S04-V1c (cartão `docs/state/cards/F0-S04/F0-S04-V1c.md`, critério 1; ADR-004 §5.1 item 8): `spatial.assign_container` em sub-lotes.
Quem implementa não edita este arquivo; quem tira os `@AINDA_NAO` (xfail estrito) é o autor do oráculo, em commit próprio, depois da implementação
(só as linhas `AINDA_NAO = ...` e `@AINDA_NAO`). Contrato (o implementador lê só isto e o cartão):
1. `fluxo_a.SUBLOTE_CONTAINER = 100` no nível do módulo; `_paredes` lê o valor do módulo NA HORA da chamada (o oráculo o troca com monkeypatch) e chama
   `api("spatial.assign_container", ...)` (o `api` do módulo, lido na hora: é o ponto de cessão de `lote._Fatiador`) uma vez por sub-lote de no máximo
   SUBLOTE_CONTAINER peças, na ordem de criação, todas com o mesmo `relating_structure`; tudo dentro da MESMA transação (um desfazer só).
2. "Mesmo IFC da chamada única" = mesmo conteúdo canônico: contagem por classe, conjunto de GlobalId, cada IfcRelContainedInSpatialStructure (GlobalId,
   pavimento, CONJUNTO de peças; uma só por pavimento), matriz de posição de cada parede nova e a lista de GlobalId devolvida (em ordem).
   A ORDEM interna de `RelatedElements` e os números STEP NÃO entram: o próprio `assign_container` monta a lista com `set` (medido em 2026-10-22:
   duas chamadas ÚNICAS iguais, com GlobalId fixos, já saem com ~2.000 linhas STEP diferentes). A ordem que o oráculo fixa é a das peças entregues à API.
VALOR MEDIDO (Linux local, 2026-10-22, xvfb-run, ambiente openbim; base sintética do `gerar_modelo_grande` com 36.000 paredes e 6.000 por andar = 31 MB;
1.000 paredes num pavimento que já tem 6.000; tempo de CADA chamada de assign_container, 2 rodadas):
  100 peças: 84-85 ms (mediana), maior 116-149 ms · 250 peças: mediana 176-195, maior 284-285 ms · 1.000 peças: 639-668 ms.
  (base 300 do lote.py, 0,2 MB: 100 -> 66 ms, 250 -> 159-163 ms, 1.000 -> 627-640 ms; custo linear, ~0,65 ms por peça.)
  Regra: o maior valor cuja chamada mais longa fique <= 250 ms -> 100 (250 passa de 250 ms). O casa25 real foi ~1,6x mais lento que a base sintética
  na chamada única (~1.000 ms contra ~640 ms), por isso 100 e não um valor mais justo. Custo: a soma das chamadas sobe de ~640 para 920-1.070 ms.
GUARDA (pula, nunca afrouxa): sem ifcopenshell ou sem o fluxo A, pula; com OBIM_S04_V1C_OBRIGATORIO=1 todo pulo vira falha. Sem janela (janela=False).
CORREÇÃO (2026-10-22, CI do PR 261): o ifcopenshell guarda o histórico de desfazer de cada arquivo num dicionário da CLASSE (`ifcopenshell.file.registry`),
que nunca solta: os ~10 modelos deste arquivo (~75 mil objetos cada) ficavam vivos e cada varredura do coletor do Python ficava mais longa, até uma pausa
única de ~250-500 ms no teste seguinte (test_viewport_responsivo). Agora cada caso tira do registro os arquivos que ele mesmo criou e coleta o lixo ao
terminar (`_limpa`, autouse); nenhum número nem caso mudou."""
import gc
import itertools
import math
import os
import tempfile
from collections import Counter
from pathlib import Path

import pytest

OBRIGATORIO = os.environ.get("OBIM_S04_V1C_OBRIGATORIO") == "1"
AINDA_NAO = pytest.mark.xfail(strict=True, reason="V1c: _paredes ainda faz uma chamada única de spatial.assign_container")
SUBLOTE = 100  # o valor fixado acima (medido)
N = 1000
AC = "spatial.assign_container"


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! S04-V1c: {msg} (oráculo dos sub-lotes NÃO FOI EXECUTADO) !!!\n")


@pytest.fixture(autouse=True)
def _limpa():  # solta o histórico dos modelos DESTE caso (registro da classe) e coleta aqui, não no teste seguinte de outro arquivo
    try:
        import ifcopenshell
        reg = getattr(ifcopenshell.file, "registry", {})  # `ifcopenshell.file` é a CLASSE (o pacote reexporta), não o submódulo
    except ImportError:  # sem ifcopenshell: o caso pula sozinho
        reg = {}
    antes = set(reg)
    yield
    for k in set(reg) - antes:
        reg.pop(k, None)
    gc.collect()


@pytest.fixture(scope="module")
def mods():
    try:
        import s04_fluxo_aux  # noqa: F401  (põe a pasta do fluxo A, app, prototypes e scripts no caminho)
        import fluxo_a
        import gerar_modelo_grande
        import ifcopenshell.guid
        import ifcopenshell.util.placement
        import lote
    except Exception as e:  # noqa: BLE001
        pular(f"sem o fluxo A ou o ifcopenshell ({e!r})")
    base = Path(tempfile.mkdtemp(prefix="v1c_")) / "base.ifc"
    gerar_modelo_grande.gerar(str(base), paredes=300)  # a base do lote.py (Andar 1 já tem 200 paredes e uma relação de contenção)
    return {"fluxo_a": fluxo_a, "lote": lote, "guid": ifcopenshell.guid, "pl": ifcopenshell.util.placement, "base": str(base)}


def _rodar(m, monkeypatch, base, n=N, sublote=None, espiao=None):  # FluxoA sem janela, GlobalId em sequência fixa; devolve (f, guids do lote, antes)
    fa = m["fluxo_a"]
    cont = itertools.count(1)
    monkeypatch.setattr(m["guid"], "new", lambda: m["guid"].compress("%032x" % next(cont)))
    if sublote is not None:
        monkeypatch.setattr(fa, "SUBLOTE_CONTAINER", sublote, raising=False)
    f = fa.FluxoA(base, janela=False)
    f.executar(m["lote"].TIPO)
    antes = _canon(m, f)
    if espiao is not None:
        monkeypatch.setattr(fa, "api", espiao(fa.api))
    try:
        guids = f.executar(m["lote"].lote_cmd(n))
    finally:
        monkeypatch.undo()  # volta api, guid.new e a constante
    return f, guids, antes


def _canon(m, f, novos=()):
    ifc = f.ifc
    rels = sorted((r.GlobalId, r.RelatingStructure.GlobalId, tuple(sorted(e.GlobalId for e in r.RelatedElements)))
                  for r in ifc.by_type("IfcRelContainedInSpatialStructure"))
    pos = {g: [round(x, 9) for x in m["pl"].get_local_placement(ifc.by_guid(g).ObjectPlacement).ravel().tolist()] for g in novos}
    return {"classes": Counter(e.is_a() for e in ifc), "guids": sorted(e.GlobalId for e in ifc.by_type("IfcRoot")), "rels": rels, "pos": pos}


def _uma_relacao_com_todas(f, guids):
    w = f.ifc.by_guid(guids[0])
    pav = w.ContainedInStructure[0].RelatingStructure
    rels = [r for r in f.ifc.by_type("IfcRelContainedInSpatialStructure") if r.RelatingStructure == pav]
    assert len(rels) == 1, f"{len(rels)} relações de contenção no pavimento (uma por sub-lote?)"
    assert set(guids) <= {e.GlobalId for e in rels[0].RelatedElements}
    assert all(len(f.ifc.by_guid(g).ContainedInStructure) == 1 and f.ifc.by_guid(g).ContainedInStructure[0] == rels[0] for g in guids)


# ---------- (a) o IFC é o da chamada única ----------
@pytest.mark.parametrize("modelo", ["base300", "novo"])  # "novo": pavimento SEM relação de contenção (a armadilha "uma relação por sub-lote")
def test_a_ifc_igual_ao_da_chamada_unica(mods, monkeypatch, modelo):
    base = mods["base"] if modelo == "base300" else None
    f1, g1, _ = _rodar(mods, monkeypatch, base, sublote=10**6)  # referência: um sub-lote só = a chamada única
    f2, g2, _ = _rodar(mods, monkeypatch, base)  # o valor do módulo
    assert len(g1) == N and g2 == g1, "GlobalId devolvidos (em ordem) diferentes"
    c1, c2 = _canon(mods, f1, g1), _canon(mods, f2, g2)
    for k in ("classes", "guids", "rels", "pos"):
        assert c2[k] == c1[k], f"conteúdo do IFC difere da chamada única em {k!r}"
    _uma_relacao_com_todas(f2, g2)


# ---------- (b) cada chamada recebe no máximo SUBLOTE_CONTAINER peças ----------
def _espia_ac(reg):
    def embrulho(api0):
        def api(nome, *a, **k):
            if nome == AC:
                reg.append(([p.GlobalId for p in k["products"]], k["relating_structure"].GlobalId))
            return api0(nome, *a, **k)
        return api
    return embrulho


def test_b_constante_fixada(mods):
    assert getattr(mods["fluxo_a"], "SUBLOTE_CONTAINER", None) == SUBLOTE, "fluxo_a.SUBLOTE_CONTAINER deve ser 100 (valor medido, ver cabeçalho)"


@pytest.mark.parametrize("n", [N, 1001, 250])  # 1001 e 250: o resto do último sub-lote
def test_b_chamadas_em_sublotes(mods, monkeypatch, n):
    reg = []
    f, guids, _ = _rodar(mods, monkeypatch, mods["base"], n=n, espiao=_espia_ac(reg))
    assert len(reg) >= math.ceil(n / SUBLOTE), f"{len(reg)} chamadas de {AC} para {n} peças (mínimo {math.ceil(n / SUBLOTE)})"
    assert all(0 < len(p) <= SUBLOTE for p, _ in reg), [len(p) for p, _ in reg]
    assert len({s for _, s in reg}) == 1, "relating_structure mudou entre sub-lotes"
    juntos = [g for p, _ in reg for g in p]
    assert juntos == guids, "peças fora da ordem de criação, repetidas ou faltando"
    _uma_relacao_com_todas(f, guids)


# ---------- (c) desfazer/refazer do lote é um passo só e inteiro ----------
def test_c_desfazer_refazer_um_passo(mods, monkeypatch):
    reg = []
    f, guids, antes = _rodar(mods, monkeypatch, mods["base"], espiao=_espia_ac(reg))
    assert reg, f"{AC} não passou pelo `api` do módulo"
    depois = _canon(mods, f, guids)
    n_hist = len(f.historico)
    f.executar({"cmd": "desfazer"})
    assert len(f.historico) == n_hist - 1
    assert _canon(mods, f) == antes, "um desfazer não voltou o modelo inteiro ao de antes do lote"
    f.executar({"cmd": "refazer"})
    assert _canon(mods, f, guids) == depois, "um refazer não refez o lote inteiro"
    _uma_relacao_com_todas(f, guids)


# ---------- (d) o ponto de cessão passa entre sub-lotes ----------
def test_d_cessao_entre_sublotes(mods, monkeypatch):
    lote, ev = mods["lote"], []
    fat = lote._Fatiador(lambda: ev.append("cessao"))

    def embrulho(api0):
        def api(nome, *a, **k):
            ev.append(nome)
            return fat.op(nome, api0, nome, *a, **k)
        return api

    def espiao(api0):  # FATIA_MS = 0 (lido em `op`): cede depois de toda operação; só a estrutura conta, nenhum tempo
        monkeypatch.setattr(lote, "FATIA_MS", 0)
        return embrulho(api0)
    _rodar(mods, monkeypatch, mods["base"], espiao=espiao)
    idx = [i for i, e in enumerate(ev) if e == AC]
    assert len(idx) >= math.ceil(N / SUBLOTE), f"{len(idx)} chamadas de {AC}"
    sem = [(a, b) for a, b in zip(idx, idx[1:]) if "cessao" not in ev[a:b]]
    assert not sem, f"{len(sem)} pares de sub-lotes sem cessão entre eles"
    assert ev.count("cessao") >= len(idx) - 1
