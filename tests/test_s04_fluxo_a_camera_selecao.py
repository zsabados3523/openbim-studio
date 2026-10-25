# SPDX-License-Identifier: AGPL-3.0-or-later
"""Teste do fluxo A: no fluxo A, `selecionar` logo depois de um comando de câmera vê a câmera NOVA (a mesma regra do fluxo B).
O núcleo só ENFILEIRA `enquadrar`, `orbitar`, `mover` e `aproximar` (e `definir_camera` só muda a câmera de trabalho); a thread de desenho aplica no início do quadro
seguinte, e `Cena.selecionar` usa a câmera do ÚLTIMO QUADRO APRESENTADO. Regra: depois de qualquer comando de câmera (enquadrar, orbitar, camera_mover, aproximar, camera),
o `selecionar` espera 2 quadros apresentados com tempo >= o instante em que o comando voltou (o 1o ainda pode ter aplicado a câmera antiga; o 2o já tem a nova) e falha
(exceção) se não vierem em 10 s. Fora: animar_orbita/parar_animacao (lote 33 O5).
Como se confere (determinístico): um vigia no lugar de `f.cena` anota o instante em que cada método de câmera do núcleo VOLTOU e, na entrada de cada `selecionar`, conta os
quadros de `relogio()` com tempo >= esse instante; tem de haver 2. Sem a espera a conta é 0 (o `selecionar` chega microssegundos depois); não passa por sorte.
Mais o comportamento, com controle: a seleção do centro logo depois do comando é igual à seleção depois de a cena assentar, e o cenário muda a seleção (senão não prova nada).
GUARDA: igual a test_s04_fluxo_a.py (OBIM_S04_T11*_OBRIGATORIO: pulo vira falha); roda em SUBPROCESSO sob `xvfb-run` (nunca na tela real)."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path

import pytest

ESTE = Path(__file__).resolve()
OBRIGATORIO = "1" in (os.environ.get("OBIM_S04_T11_OBRIGATORIO"), os.environ.get("OBIM_S04_T11B_OBRIGATORIO"), os.environ.get("OBIM_S04_T11C_OBRIGATORIO"))
RODADAS = 5
LONGE = {"cmd": "camera", "alvo": [7.0, 0.075, 500.0], "distancia": 5.0, "azimute": -90.0, "elevacao": -20.0}  # alvo 500 m acima das paredes: o centro não acerta nada
FRENTE = {"cmd": "camera", "alvo": [7.0, 0.075, 1.4], "distancia": 30.0, "azimute": -90.0, "elevacao": 20.0}  # o centro da parede do meio (x de 5 a 9)
CENARIOS = {  # comando: (preparo, comando de câmera, confere o comportamento?)  orbitar/aproximar giram em torno do alvo: o centro não muda (só a regra dos 2 quadros)
    "enquadrar": (LONGE, {"cmd": "enquadrar"}, True),  # = passos 3b e 3c do roteiro R
    "camera": (FRENTE, LONGE, True),
    "camera_mover": (FRENTE, {"cmd": "camera_mover", "dx": 400.0, "dy": 0.0}, True),
    "orbitar": (FRENTE, {"cmd": "orbitar", "dx": 200.0, "dy": 0.0}, False),
    "aproximar": (FRENTE, {"cmd": "aproximar", "fator": 0.5}, False),
}
NUCLEO = ("enquadrar", "orbitar", "mover", "aproximar", "definir_camera")  # métodos de câmera da Cena


def pular(msg):
    (pytest.fail if OBRIGATORIO else pytest.skip)(f"\n!!! S04-T14d: {msg} (teste da câmera antes da seleção no fluxo A NÃO FOI EXECUTADO) !!!\n")


# ---------- subprocesso (python este_arquivo.py corrida) ----------
class Vigia:  # fica no lugar de `f.cena`
    def __init__(s, real, agora):
        s.real, s.agora, s.t_cam, s.quadros, s.esconder = real, agora, None, [], False

    def __getattr__(s, nome):
        a = getattr(s.real, nome)
        if nome in NUCLEO:
            def cam(*args, **kw):
                r = a(*args, **kw)
                s.t_cam = s.agora()  # depois de o comando voltar (como o B)
                return r
            return cam
        if nome == "relogio":  # `esconder`: o desenho "parou" para o fluxo (só quadros anteriores ao último comando de câmera)
            return lambda: [x for x in a() if x[0] < s.t_cam] if s.esconder else a()
        if nome == "selecionar":
            def sel(x, y):
                s.quadros.append(None if s.t_cam is None else sum(1 for t, _ in s.real.relogio() if t >= s.t_cam))
                return a(x, y)
            return sel
        return a


def c_corrida(res):
    import fluxo_a
    import obimcore
    from s04_fluxo_aux import PAREDE, TIPO, assentar
    f = fluxo_a.FluxoA(None, janela=True, saida=Path(tempfile.mkdtemp()))
    f.executar(TIPO)
    gs = [f.executar(PAREDE)[0] for _ in range(3)]  # x de 0 a 4, 5 a 9, 10 a 14 (y de 0 a 0,15; z de 0 a 2,8)
    v = f.cena = Vigia(f.cena, obimcore.agora)
    centro = lambda: (f.executar({"cmd": "selecionar", "x": "centro", "y": "centro"}) or [None])[0]  # noqa: E731
    res.update(gs=gs, janela=bool(f.janela_principal.isVisible()), cenarios={})
    for nome, (prep, cmd, _) in CENARIOS.items():
        rs = res["cenarios"][nome] = []
        for _ in range(RODADAS):
            f.executar(prep)
            assentar(f)
            antes = centro()
            f.executar(dict(cmd))
            imediato, q = centro(), v.quadros[-1]  # nada entre o comando e o selecionar (como os passos 3b e 3c)
            assentar(f)
            rs.append({"antes": antes, "imediato": imediato, "quadros": q, "depois": centro()})
    f.executar(FRENTE)
    assentar(f)
    v.esconder = True  # o próximo comando de câmera nunca chega a um quadro: o selecionar tem de desistir com erro em 10 s, não ficar preso nem responder com a câmera velha
    f.executar({"cmd": "enquadrar"})
    t0 = time.perf_counter()
    try:
        r = centro()
        res["sem_quadro"] = {"erro": None, "devolveu": r, "ms": (time.perf_counter() - t0) * 1000}
    except Exception as e:
        res["sem_quadro"] = {"erro": f"{type(e).__name__}: {e}", "ms": (time.perf_counter() - t0) * 1000}
    v.esconder = False
    f.fechar()
    return res


# ---------- casos ----------
@pytest.fixture(scope="module")
def corrida():
    import s04_fluxo_aux as aux
    if not (aux.PASTA / "fluxo_a.py").is_file():
        pular("tools/s04/fluxo_a/fluxo_a.py ausente")
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real")
    from test_s04_viewport import caso
    r = caso("corrida", alvo=ESTE, limite=600)
    assert r["janela"], r
    return r


@pytest.mark.parametrize("nome", list(CENARIOS))
def test_selecionar_depois_do_comando_de_camera_espera_2_quadros_apresentados(corrida, nome):
    q = [x["quadros"] for x in corrida["cenarios"][nome]]
    assert len(q) == RODADAS and all(n is not None and n >= 2 for n in q), (
        f"{nome}: o selecionar chegou ao núcleo com {q} quadros apresentados depois do comando de câmera (exige 2 em cada uma das {RODADAS} rodadas)")


@pytest.mark.parametrize("nome", [n for n, c in CENARIOS.items() if c[2]])
def test_selecionar_logo_depois_do_comando_de_camera_ve_a_camera_nova(corrida, nome):
    rs, g1 = corrida["cenarios"][nome], corrida["gs"][1]
    for x in rs:  # controle: o cenário muda a seleção do centro (senão o caso não prova nada) e a câmera assentada acerta o esperado
        assert x["antes"] != x["depois"] and g1 in (x["antes"], x["depois"]), f"{nome}: cenário sem efeito (antes {x['antes']}, assentado {x['depois']}; parede do meio {g1})"
    assert [x["imediato"] for x in rs] == [x["depois"] for x in rs], f"{nome}: seleção logo depois do comando {[x['imediato'] for x in rs]} != com a cena assentada {[x['depois'] for x in rs]}"


def test_sem_quadro_novo_o_selecionar_falha_em_10_s(corrida):
    s = corrida["sem_quadro"]
    assert s["erro"] is not None, f"sem quadro com a câmera nova, o selecionar respondeu {s.get('devolveu')!r} em {s['ms']:.0f} ms (com a câmera velha) em vez de falhar"
    assert 9500 <= s["ms"] <= 15000, f"o selecionar desistiu em {s['ms']:.0f} ms (exige cerca de 10 s): {s['erro']}"


if __name__ == "__main__":
    import faulthandler
    faulthandler.dump_traceback_later(int(os.environ.get("OBIM_LIMITE", 600)) - 20, exit=True)
    sys.path.insert(0, str(ESTE.parent))
    import s04_fluxo_aux  # noqa: F401  (põe tools/s04/fluxo_a, app/ e tests/ no caminho)
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    nome = sys.argv[1]
    try:
        saida = globals()["c_" + nome]({})
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False), flush=True)
    os._exit(0)
