# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo mínimo da ORDEM DE PROFUNDIDADE da viewport (S04-T10b). Roda em subprocesso sob `xvfb-run` (nunca na tela real), como `test_s04_selecao.py`.
FALHA ESPERADA HOJE: com xvfb/GL por software o teste de profundidade não funciona; o cubo grande de trás sai por cima do pequeno da frente
(achado do implementador da T10: cubos parecem semitransparentes; `Cena.selecionar` devolve o certo, o DESENHO é que erra).
Regra: um cubo opaco PERTO da câmera, alinhado com um cubo maior ATRÁS, tem de dar a cor do perto no pixel central, em qualquer ordem de inserção.
OBIM_S04_T10B_OBRIGATORIO=1 transforma pulo em falha."""
import importlib.util, os, shutil, sys  # noqa: E401
from pathlib import Path

import pytest

from test_s04_cena import com_guids
from test_s04_viewport import CORES, RAIZ, captura, esperar, lote, novo, rodar
from test_s04_viewport import caso as _caso

ESTE = Path(__file__).resolve()
caso = lambda nome, *a, **k: _caso(nome, *a, alvo=ESTE, **k)  # noqa: E731
OBRIG = os.environ.get("OBIM_S04_T10B_OBRIGATORIO") == "1"
pular = pytest.fail if OBRIG else pytest.skip
CAM = dict(alvo=(0.0, 0.0, 0.0), distancia=20.0, azimute=-90.0, elevacao=0.0)  # olha ao longo de +y; x para a direita, z para cima
# (nome, centro, raio, cor): todos alinhados em x=z=0; a câmera fica em y < 0, então menor y = mais perto
PERTO, MEIO, LONGE = ("perto", (0, -4, 0), 1.0, CORES[0]), ("meio", (0, 0, 0), 2.0, CORES[1]), ("longe", (0, 5, 0), 4.0, CORES[2])

@pytest.fixture(scope="module")
def tela():
    if importlib.util.find_spec("obimcore") is None:
        pular("\n!!! aguarda S04-T07/T08: módulo obimcore ausente (oráculo de profundidade NÃO FOI EXECUTADO) !!!\n")
    import ifcopenshell, obimcore  # noqa: E401,F401
    if not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1") if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("\n!!! sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1): nunca na tela real !!!\n")

def c_ordem(res, ordem):  # `ordem`: nomes separados por vírgula, na ordem de inserção (um lote por cubo)
    por_nome = {x[0]: x[1:] for x in (PERTO, MEIO, LONGE)}
    c, w, _ = novo(0, CAM)
    for i, nome in enumerate(ordem.split(",")):
        c.adicionar_lote(com_guids(lote(cubos=[por_nome[nome]]), f"{i:022d}"))
        yield from esperar(lambda: c.estatisticas()["triangulos_na_placa"] == 12 * (i + 1))
    yield 700
    a = captura(c)
    h, l, _ = a.shape[0], a.shape[1], 0
    res["centro"] = [int(v) for v in a[h // 2, l // 2]]
    res["vizinhos"] = [[int(v) for v in a[h // 2 + dy, l // 2 + dx]] for dy, dx in ((-3, 0), (3, 0), (0, -3), (0, 3))]
    c.parar()

def perto_e_a_cor_do_centro(r, cor):
    return all(abs(a - b) <= 40 for a, b in zip(r["centro"][:3], cor[:3]))

@pytest.mark.parametrize("ordem", ["perto,longe", "longe,perto"])
def test_cubo_perto_tapa_o_cubo_maior_atras_nas_duas_ordens_de_insercao(tela, ordem):
    r = caso("ordem", ordem)
    assert perto_e_a_cor_do_centro(r, PERTO[3]), f"ordem {ordem}: o pixel central deveria ser vermelho (o cubo da frente), saiu {r['centro']} (vizinhos {r['vizinhos']})"

@pytest.mark.parametrize("ordem", ["perto,meio,longe", "longe,meio,perto", "meio,perto,longe", "meio,longe,perto", "perto,longe,meio", "longe,perto,meio"])
def test_tres_cubos_alinhados_em_ordens_permutadas_mostram_sempre_o_mais_perto(tela, ordem):
    r = caso("ordem", ordem)
    assert perto_e_a_cor_do_centro(r, PERTO[3]), f"ordem {ordem}: o pixel central deveria ser vermelho (o mais perto), saiu {r['centro']} (vizinhos {r['vizinhos']})"

if __name__ == "__main__":
    sys.path.insert(0, str(RAIZ / "prototypes"))
    nome, *resto = sys.argv[1:]
    __import__("ifcopenshell"), __import__("obimcore")
    rodar(lambda r: globals()["c_" + nome](r, *resto))
