# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T07e3: `planta.py` vira CLIENTE do processo auxiliar; o motor (anotação temporária, ajustes, serializador, laço do iterator) mora em `geometria/obim_geometria/desenho.py`.
Especificação: `cards/F0-S06/F0-S06-T07e-especificacao.md` (§2, §4, §5 casos 1, 7, 9, 10). Completa `test_s06_t07e_desenho_oraculo.py` (casos 1, 2, 7 e 9 da planta) e não repete o que ele cobre.
Não editar este arquivo nem `s06_t07e_aux.py` na implementação; quem tira os `@AINDA_NAO_E3B` (xfail estrito, com o `raises` do motivo real de hoje) é o autor do oráculo, em commit próprio, depois da e3.
CONTRATO [P] = escolha do oráculo que a especificação não fixa (provisória até o Opus confirmar):
- `obim_geometria.desenho.processar(pedido: dict) -> dict` (mesmo desenho de `caixas.processar`): abre `pedido["arquivo"]`, confere cada `[id, GlobalId]` (senão `{"ok": false, "erro": {"tipo": "ArquivoDivergente", ...}}`),
  trabalha NESSE arquivo sem limpar nem copiar, devolve a resposta crua da especificação §2; `enviados` = ids que foram ao serializador, `caixas` = ids desenhados como caixa (modelo pequeno: lista vazia).
  `processo.entrada` e `local.executar` despacham `op == "desenho"` para ele (import preguiçoso dentro da função) e mandam as fases `aberto`, `geometria`, `motor`, nessa ordem.
- `gerar_planta(ifc, gid, *, categorias_ocultas=(), threads=None, limite_triangulos=None, limite_s=auxiliar.LIMITE_PADRAO_S, cancelar=None, executor=None) -> Planta`: tudo depois de `gid` só por nome. `Planta` ganha
  o campo `caixas` (resposta `caixas`); `tempos` ganha `abrir_s`, `copia_s`, `auxiliar_s`. Pedido `desenho`: `elementos` = `[[id, GlobalId], ...]` da seleção, `threads` repassado (None = padrão do `auxiliar`),
  `limite_triangulos` repassado, `vista` = `{"tipo": "PLANTA", "altura_corte_m": Planta.altura_corte, "origem_pav": [x, y, z] do posicionamento do pavimento NA UNIDADE DO ARQUIVO, "escala": Planta.unidade_escala}`.
- Seleção vazia (tudo oculto, pavimento sem peça): `Planta` vazia (`n_paths` 0, `svg` válido) SEM `preparar`, SEM cópia e SEM executor.
Os 3 oráculos T07b (`planta`, `completa`, `entrega`) só trocaram o ALVO: `P()` passa `executor=obim_geometria.local.executar` (via `s06_t07b_aux.com_local`, que só repassa `executor` se `gerar_planta` já o aceitar)."""
import ast
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import s06_t07e_aux as T
from test_s06_t07e_auxiliar_oraculo import _loc, _x, tmp_aux  # noqa: F401  (a fixture `tmp_aux` vem junto)

APP = Path(__file__).resolve().parent.parent / "app"
GEO = Path(__file__).resolve().parent.parent / "geometria" / "obim_geometria"
PLANTA = APP / "openbim_app" / "desenho" / "planta.py"


def _p():
    from openbim_app.desenho import planta
    return planta


def _levanta(cls, fn, *a, **k):  # `pytest.raises` falharia com `Failed`, que o xfail com `raises=AssertionError` não reconhece
    try:
        fn(*a, **k)
    except cls as e:
        return e
    raise AssertionError(f"não levantou {cls.__name__}")


def _vazio(pasta):
    assert not list(pasta.glob("obim-desenho-*")), "pasta temporária ficou"
    import multiprocessing
    assert not multiprocessing.active_children(), "filho vivo"


@pytest.mark.parametrize("proibido", ["ifcopenshell.ifcopenshell_wrapper", ".iterator(", "ifcopenshell.geom", "serializers"])
def test_planta_py_nao_tem_motor(proibido):
    assert proibido not in PLANTA.read_text(encoding="utf-8")  # texto cru, comentário incluído (mesmo critério do caso 10)


def test_planta_py_nao_tem_ifcopenshell_draw():  # guarda de regressão: passa hoje e tem de continuar passando
    assert "ifcopenshell.draw" not in PLANTA.read_text(encoding="utf-8")


def test_importar_planta_nao_carrega_geometria():  # a janela só importa planta; o motor fica para o filho
    codigo = ("import sys, json\nimport openbim_app.desenho.planta\n"
              "print(json.dumps(sorted(m for m in sys.modules if m.startswith(('ifcopenshell.geom', 'ifcopenshell.draw', 'obim_geometria.desenho', 'obim_geometria.caixas', 'obim_geometria.local')))))\n")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=120,
                       env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path), "LC_ALL": "C"})
    assert r.returncode == 0, r.stderr[-1500:]
    assert json.loads(r.stdout.strip().splitlines()[-1]) == []


def test_processo_py_so_importa_biblioteca_padrao_no_topo():  # guarda de regressão: passa hoje e tem de continuar passando
    topo = ast.parse((GEO / "processo.py").read_text(encoding="utf-8")).body
    nomes = {(n.module or "") if isinstance(n, ast.ImportFrom) else a.name for n in topo if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (getattr(n, "names", None) or [None])}
    assert not [n for n in nomes if n.split(".")[0] in ("ifcopenshell", "obim_geometria", "openbim_app", "numpy")], nomes


def test_desenho_processar_igual_ao_local_e_confere_ids(tmp_aux):
    import obim_geometria.desenho as D
    L, X = _loc(), _x()
    f, d = T.modelo()
    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0}
    ped = {"op": "desenho", "elementos": T.elementos(f, "P", "M"), "vista": vista}
    with X.preparar(f, ped) as p:
        a, b = D.processar(dict(p.pedido)), L.executar(dict(p.pedido))
        assert a["ok"] and b["ok"] and a["svg"] == b["svg"] and a["n_paths"] == b["n_paths"] > 0
        assert sorted(a["enviados"]) == sorted(i for i, _ in T.elementos(f, "P", "M")) and a["caixas"] == [] and a["falhas_geometria"] == []
        assert a["tempos"].keys() >= {"abrir_s", "geo_s", "write_s", "finalize_s"} and json.loads(json.dumps(a)) == a
        ruim = dict(p.pedido, elementos=[[T.elementos(f, "P")[0][0], d["M"].GlobalId]])
        r = D.processar(ruim)
        assert r["ok"] is False and r["erro"]["tipo"] == "ArquivoDivergente"


def test_processo_entrada_despacha_desenho_com_as_tres_fases(tmp_aux):
    X = _x()
    import obim_geometria.processo as PR

    class Tx:
        def __init__(self):
            self.msgs = []

        def send_bytes(self, b):
            self.msgs.append(json.loads(b.decode("utf-8")))

        def close(self):
            pass
    f, d = T.modelo()
    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "origem_pav": [0.0, 0.0, 0.0], "escala": 1.0}
    with X.preparar(f, {"op": "desenho", "elementos": T.elementos(f, "P", "M"), "vista": vista}) as p:
        tx = Tx()
        PR.entrada(tx, json.dumps(p.pedido))
    resp = next((m["dados"] for m in tx.msgs if m["tipo"] == "resposta"), None)
    assert resp and resp["ok"] and resp["n_paths"] > 0 and f"ifc:guid=\"{d['P'].GlobalId}\"" in resp["svg"], resp
    fases = [m["fase"] for m in tx.msgs if m["tipo"] == "fase"]
    assert [x for x in fases if x in ("aberto", "geometria", "motor")] == ["aberto", "geometria", "motor"]


def test_executor_local_continua_recusando_operacao_desconhecida():  # guarda de regressão
    r = _loc().executar({"protocolo": 1, "op": "nao-existe"})
    assert r["ok"] is False and r["erro"]["tipo"] == "OperacaoDesconhecida"


def test_assinatura_de_gerar_planta():
    import inspect
    ps = inspect.signature(_p().gerar_planta).parameters
    novos = {"categorias_ocultas": (), "threads": None, "limite_triangulos": None, "limite_s": _x().LIMITE_PADRAO_S, "cancelar": None, "executor": None}
    assert all(n in ps and ps[n].kind is inspect.Parameter.KEYWORD_ONLY and ps[n].default == v for n, v in novos.items()), ps
    assert list(ps)[:2] == ["ifc", "gid_vista"]


def test_filho_real_igual_ao_local_byte_a_byte(tmp_aux):
    P_, L = _p(), _loc()
    f, d = T.modelo()
    antes = f.to_string()
    loc = P_.gerar_planta(f, d["vp"], executor=L.executar)  # o local primeiro: hoje a falta do `executor` aparece de graça
    real = P_.gerar_planta(f, d["vp"])
    assert real.svg == loc.svg and real.n_paths == loc.n_paths > 0 and real.caixas == loc.caixas and real.selecao == loc.selecao
    assert real.altura_corte == loc.altura_corte and real.unidade_escala == loc.unidade_escala
    assert f.to_string() == antes
    assert real.tempos["copia_s"] > 0 and real.tempos["auxiliar_s"] > 0 and real.tempos["abrir_s"] > 0
    _vazio(tmp_aux)


def test_threads_padrao_e_caixas_e_threads_chegam_ao_motor(tmp_aux, monkeypatch):
    import ifcopenshell.geom as G
    P_, L = _p(), _loc()
    f, d = T.modelo()
    peds, nthr, orig = [], [], G.iterator

    def it(st, arq, n, **k):
        nthr.append(n)
        return orig(st, arq, n, **k)
    monkeypatch.setattr(G, "iterator", it)

    def espia(pedido):  # devolve `caixas` inventado para provar que o cliente repassa
        peds.append(pedido)
        return {**L.executar(pedido), "caixas": [7, 9]}
    p = P_.gerar_planta(f, d["vp"], executor=espia)
    assert p.caixas == (7, 9) and isinstance(peds[0]["threads"], int) and peds[0]["threads"] >= 1 and nthr == [peds[0]["threads"]]
    P_.gerar_planta(f, d["vp"], threads=3, executor=espia)
    assert peds[1]["threads"] == 3 and nthr[-1] == 3
    _vazio(tmp_aux)


@pytest.mark.parametrize("esq,off,base,k", T.MODELOS)
def test_pedido_e_json_puro_e_leva_os_numeros_do_pavimento(tmp_aux, esq, off, base, k):
    P_, L = _p(), _loc()
    f, d = T.modelo(esq, off, base, k)
    vistos = []

    def espia(pedido):
        vistos.append((json.loads(json.dumps(pedido)) == pedido, json.loads(json.dumps(pedido)), Path(pedido["arquivo"]).is_file()))
        return L.executar(pedido)
    p = P_.gerar_planta(f, d["vp"], threads=3, limite_triangulos=12345, executor=espia)
    assert len(vistos) == 1 and vistos[0][0] and vistos[0][2]
    ped = vistos[0][1]
    assert ped["op"] == "desenho" and ped["protocolo"] == 1 and ped["threads"] == 3 and ped["limite_triangulos"] == 12345 and Path(ped["arquivo"]).is_absolute()
    assert {tuple(e) for e in ped["elementos"]} == {(i, f.by_id(i).GlobalId) for i in p.selecao.ids} and len(ped["elementos"]) == len(p.selecao.ids) > 0
    v = ped["vista"]
    assert v["tipo"] == "PLANTA" and v["altura_corte_m"] == pytest.approx(base + 1.2, abs=1e-6) and p.altura_corte == v["altura_corte_m"] and v["escala"] == pytest.approx(1.0 / k)
    assert v["origem_pav"] == pytest.approx([off[0] * k, off[1] * k, base * k])  # posicionamento do pavimento na unidade do ARQUIVO (mm no 2X3)
    _vazio(tmp_aux)


@pytest.fixture
def sem_copia(tmp_aux, monkeypatch):
    X = _x()

    def nao(*a, **k):
        raise AssertionError("auxiliar.preparar chamado: planta vazia não faz cópia nem processo")
    monkeypatch.setattr(X, "preparar", nao)
    return tmp_aux


def test_selecao_vazia_nao_chama_executor_nem_faz_copia(sem_copia):
    P_ = _p()
    f, d = T.modelo()
    antes = f.to_string()

    def nao(pedido):
        raise AssertionError("executor chamado para seleção vazia")
    p = P_.gerar_planta(f, d["vp"], categorias_ocultas=("IfcElement",), executor=nao)
    assert p.n_paths == 0 and p.selecao.ids == () and "<path" not in p.svg and ET.fromstring(p.svg).tag.endswith("svg")
    assert p.tempos.keys() >= {"geo_s", "write_s", "finalize_s"} and f.to_string() == antes
    _vazio(sem_copia)


@pytest.mark.parametrize("tipo,classe", [("ArquivoDivergente", "ArquivoDivergente"), ("ProtocoloInvalido", "ProtocoloInvalido"), ("ZeroDivisionError", "FalhaNoAuxiliar")])
def test_erros_tipados_do_auxiliar_sobem_por_gerar_planta(tmp_aux, tipo, classe):
    P_, X = _p(), _x()
    f, d = T.modelo()
    e = _levanta(getattr(X, classe), P_.gerar_planta, f, d["vp"], executor=lambda ped: {"ok": False, "erro": {"tipo": tipo, "mensagem": "xyz", "rastro": "rastro"}})
    assert isinstance(e, X.ErroAuxiliar) and isinstance(e, RuntimeError) and "xyz" in str(e)
    if classe == "FalhaNoAuxiliar":
        assert (e.tipo, e.mensagem, e.rastro) == (tipo, "xyz", "rastro") and str(e) == f"{tipo}: xyz"
    _vazio(tmp_aux)


def test_cancelar_armado_antes_levanta_cancelado_sem_chamar_executor(tmp_aux):
    import threading
    P_, X = _p(), _x()
    f, d = T.modelo()
    ev = threading.Event()
    ev.set()

    def nao(ped):
        raise AssertionError("executor chamado com cancelar armado")
    _levanta(X.DesenhoCancelado, P_.gerar_planta, f, d["vp"], cancelar=ev, executor=nao)
    _vazio(tmp_aux)


def test_filho_real_erro_e_tempo_sobem_por_gerar_planta(tmp_aux, monkeypatch):  # hoje a planta roda no próprio processo: os ganchos do filho não valem
    P_, X = _p(), _x()
    f, d = T.modelo()
    monkeypatch.setenv("OBIM_TESTE_AUX_LEVANTAR", "xyz")
    e = _levanta(X.FalhaNoAuxiliar, P_.gerar_planta, f, d["vp"])
    assert e.tipo == "RuntimeError" and "xyz" in e.mensagem and e.rastro
    monkeypatch.delenv("OBIM_TESTE_AUX_LEVANTAR")
    monkeypatch.setenv("OBIM_TESTE_AUX_DORMIR_S", "60")
    e = _levanta(X.AuxiliarEstourouTempo, P_.gerar_planta, f, d["vp"], limite_s=1)
    assert e.limite_s == 1
    _vazio(tmp_aux)
