# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do F0-S06-T07c (corte vertical em SVG bruto; ADR-004 regra 9; `cards/F0-S06/F0-S06-T07-divisao.md` e `T07e-especificacao.md`). Não editar este arquivo nem `s06_t07c_aux.py` na implementação.
CONTRATO `app/openbim_app/desenho/corte.py` (sem Qt, sem rede; nenhum `ifcopenshell.geom` em `app/`; `selecao.py` e `auxiliar.py` já existem):
1. `gerar_corte(ifc, gid_vista, *, categorias_ocultas=(), threads=None, limite_triangulos=None, limite_s=auxiliar.LIMITE_PADRAO_S, cancelar=None, executor=None) -> Corte`, espelho de `gerar_planta`.
   `Corte` = dataclass congelada: `svg` (str, SVG BRUTO do motor, XML válido de raiz `svg`; no corte o motor já escreve `viewBox="0 0 largura altura"` do `IfcBlock`, em metros), `n_paths` (= `<path` no texto), `selecao` (a `Selecao` da T07a), `tempos` (`geo_s`, `write_s`,
   `finalize_s` >= 0), `unidade_escala` (1.0 em metro, 0.001 em milímetro), `caixas` (tupla; vazia em modelo pequeno). Vista que não é CORTE, CORTE sem `IfcBlock` ou sem posicionamento, categoria
   inexistente -> `selecao.SelecaoInvalida`; vista inexistente -> `vistas_ifc.VistaInexistente`; tudo isso ANTES de qualquer chamada ao executor. A seleção é `selecao.selecionar(...)` (T07a).
2. [P] Pedido ao auxiliar: depois do `caixas` da seleção, UMA chamada `op == "desenho"` com `elementos` = `[[id, GlobalId], ...]` de `selecao.ids`, `vista` = `{"tipo": "CORTE", "guid": gid_vista,
   "escala": unidade_escala}`, `threads`/`limite_triangulos` repassados como em `gerar_planta`. Seleção vazia -> `Corte` vazio (`n_paths` 0, `svg` válido) SEM chamada `desenho` (fusão num filho só: otimização futura).
3. CONTRATO DO MOTOR (ifcopenshell 0.9.0, medido em 5/11, `settings`: `elevation-ref-guid` = GlobalId da vista, `svg-without-storeys`, `svg-project`, `svg-write-poly`, `svg-xmlns`, `svg-poly`):
   a. A vista é o plano: origem = posicionamento da `IfcAnnotation`, direção de visão = -Z local, X local = `RefDirection`, Y local = Z x X. O motor só desenha o que a lista do iterator contém, e o iterator TEM de
      conter a própria anotação (sem ela o SVG sai sem seção: 0 paths).
   b. Desenhado: o que cruza o plano, dentro de X local em [Position.x, +largura] e Y local em [Position.y, +altura] do `IfcBlock`, vira um `<g class=IfcXxx ifc:guid=...>` com o contorno do CORTE (polilinha fechada;
      parede furada pela porta = 1 polígono com o recorte; janela no meio = contorno externo + furo); o que está ALÉM do plano, dentro da profundidade (Position.z + Z local em [-profundidade, 0], ou seja o
      volume tem de ficar do lado da visão), aparece só em `<g class="projection">` (caminhos sem guid, linhas escondidas removidas); atrás da câmera, fora da profundidade ou fora do retângulo: nada.
   c. Unidade/quadro: o motor multiplica por 1000 x escala da vista (`EPset_Drawing.Scale`/`HumanScale`; 1:100 dá 10 por metro). O SVG tem de sair em METROS: a cópia descartável do filho troca as duas
      propriedades para 1/1000 e 1:1000 (a vista do usuário não muda). Quadro cru: x_svg = X local + largura/2; y_svg = altura/2 - Y local (y cresce para baixo; o teto tem y MENOR que o piso); a
      largura e a altura são as do `IfcBlock`, e o `Position` do bloco NÃO entra nesse deslocamento (só no recorte).
   d. Georreferenciado: com a vista longe da origem (324550 / 7405473, ou cota alta) o motor perde as seções (só `projection`, nenhum grupo com guid). Correção medida: `model-offset` = -(origem da vista no
      mundo, em metros, multiplicada pela unidade do arquivo). A cota do modelo (-1,5 / 12,5 / 100 / 1450 m) e a unidade (mm) não mudam o SVG.
   e. Abertura (`IfcOpeningElement`) não vai ao iterator (o vão continua furado, a abertura não é desenhada), como na planta; a porta/janela que a preenche é cortada e tem grupo próprio.
4. Resultado determinístico (duas chamadas = SVG igual), `threads` só muda o paralelismo, o arquivo de entrada NÃO muda (`to_string` igual; escala da vista intacta). Nomes gravados em inglês: o corte NÃO usa
   `OBIM_View.CutHeight` (altura de corte é da planta; valor inválido nele não levanta erro) e nunca grava `OBIM_Vista`/`AlturaCorte`.
GUARDA: sem ifcopenshell, pula (falha com OBIM_S05_OBRIGATORIO=1)."""
import dataclasses
import inspect
import re
import subprocess
import sys

import pytest
import s06_t07_aux as X
import s06_t07b_aux as B
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)

MOD = pytest.mark.parametrize("esq,off,base,k", C.MODELOS)
JANELA = ("jan", "IfcWindow", 3.0, 0.9, 1.0, 1.0)  # 0,9 a 1,9 m: no meio da parede
TOL = 0.005
PAREDE_COM_PORTA = {(1.0, 0.0), (1.0, 2.0), (2.0, 2.0), (2.0, 0.0), (5.0, 0.0), (5.0, 3.0), (0.0, 3.0), (0.0, 0.0)}


def K():
    exigir()
    import openbim_app.desenho.corte as K_
    return K_


def executor_local():
    import obim_geometria.local as L
    return L.executar


def pts(svg, f_g, nome, olhar="+Y"):
    """Polilinhas do grupo do elemento, em metros relativos à origem do modelo (x, z)."""
    return [[C.local(p, olhar) for p in sp] for sp in B.subcaminhos(B.grupo(svg, f_g[nome]))]


def perto(a, b):
    return all(abs(x - y) <= TOL for x, y in zip(a, b)) and len(a) == len(b)


def conjunto_perto(a, b):
    return len(a) == len(b) and all(any(perto(p, q) for q in b) for p in a)


def bbox(sub):
    return B.caixa_de(sub)


def contador(chamadas):
    L = executor_local()

    def exe(ped):
        chamadas.append(ped)
        return L(ped)
    return exe


def proibido(ped):
    raise AssertionError(f"executor chamado: {ped.get('op')}")


@MOD
def test_parede_porta_laje_e_movel_por_modelo(esq, off, base, k):
    K_ = K()
    f, g = C.modelo(esq, off, base, k, vaos=(C.PORTA,))
    c = K_.gerar_corte(f, C.corte(f, off, base, k), executor=executor_local())
    assert isinstance(c, K_.Corte) and dataclasses.is_dataclass(c) and c.unidade_escala == pytest.approx(1.0 / k) and c.caixas == ()
    assert c.n_paths > 0 and c.n_paths == len(re.findall(r"<path\b", c.svg)) and B.svg_valido(c.svg)
    assert [float(v) for v in re.search(r'<svg [^>]*viewBox="([^"]+)"', c.svg).group(1).split()] == pytest.approx([0.0, 0.0, C.DX, C.DY], abs=TOL)
    assert c.tempos.keys() >= {"geo_s", "write_s", "finalize_s"} and all(isinstance(v, float) and v >= 0 for v in c.tempos.values())
    par = pts(c.svg, g, "P")  # parede cortada + vão da porta: 1 polígono fechado com o recorte (área 15 - 2)
    assert len(par) == 1 and par[0][0] == par[0][-1] and conjunto_perto(set(par[0][:-1]), PAREDE_COM_PORTA)
    assert C.area(B.subcaminhos(B.grupo(c.svg, g["P"]))[0]) == pytest.approx(13.0, abs=0.01)
    porta = pts(c.svg, g, "porta")  # a porta preenche o vão: retângulo 1 x 2
    assert len(porta) == 1 and bbox(porta[0]) == pytest.approx((1.0, 0.0, 2.0, 2.0), abs=TOL)
    laje = pts(c.svg, g, "L")  # laje 0,2 m abaixo da cota da parede: retângulo 5 x 0,2, y_svg MAIOR que o da parede (piso embaixo)
    assert len(laje) == 1 and bbox(laje[0]) == pytest.approx((0.0, -0.2, 5.0, 0.0), abs=TOL)
    assert min(p[1] for p in B.subcaminhos(B.grupo(c.svg, g["L"]))[0]) >= max(p[1] for p in B.subcaminhos(B.grupo(c.svg, g["P"]))[0]) - TOL
    assert B.grupo(c.svg, g["M"]) is None  # móvel ALÉM do plano: sem grupo próprio, só linhas de vista na projeção
    proj = {C.local(p) for sp in B.subcaminhos(C.projecao(c.svg)) for p in sp}
    assert {(5.1, 0.0), (5.4, 0.0), (5.1, 1.5), (5.4, 1.5)} <= {(round(x, 1), round(z, 1)) for x, z in proj}
    assert not any(g[n] in c.svg for n in ("Fundo", "Atras", "Longe"))  # além da profundidade, atrás da câmera, a 150 m
    assert {f.by_id(i).Name for i in c.selecao.ids} == {"P", "L", "M", "Oporta", "porta"} and c.selecao.tipo == "CORTE"


def test_parede_inteira_e_janela_no_meio():
    K_ = K()
    f, g = C.modelo("IFC4", extras=False)
    par = pts(K_.gerar_corte(f, C.corte(f), executor=executor_local()).svg, g, "P")
    assert len(par) == 1 and len(par[0]) == 5 and bbox(par[0]) == pytest.approx((0.0, 0.0, 5.0, 3.0), abs=TOL)
    f, g = C.modelo("IFC4", vaos=(JANELA,), extras=False)
    c = K_.gerar_corte(f, C.corte(f), executor=executor_local())
    subs = sorted(B.subcaminhos(B.grupo(c.svg, g["P"])), key=C.area, reverse=True)  # contorno externo + furo da janela
    assert len(subs) == 2 and C.area(subs[0]) == pytest.approx(15.0, abs=0.01) and C.area(subs[1]) == pytest.approx(1.0, abs=0.01)
    assert B.grupo(c.svg, g["jan"]) is not None


def test_olhando_para_menos_y_espelha_o_x():
    K_ = K()
    brutos = {}
    for olhar in ("+Y", "-Y"):
        f, g = C.modelo("IFC4", vaos=(C.PORTA,), extras=False)
        c = K_.gerar_corte(f, C.corte(f, olhar=olhar), executor=executor_local())
        assert conjunto_perto(set(pts(c.svg, g, "P", olhar)[0][:-1]), PAREDE_COM_PORTA)  # o mundo é o mesmo nas duas vistas
        brutos[olhar] = (bbox(B.subcaminhos(B.grupo(c.svg, g["P"]))[0]), bbox(B.subcaminhos(B.grupo(c.svg, g["porta"]))[0]))
    # +Y: x_svg = x + 4; -Y: x_svg = 10 - x (porta 1..2 m: 5..6 e 8..9)
    assert brutos["+Y"][0][0] == pytest.approx(4.0, abs=TOL) and brutos["+Y"][1][0] == pytest.approx(5.0, abs=TOL)
    assert brutos["-Y"][0][0] == pytest.approx(5.0, abs=TOL) and brutos["-Y"][1][0] == pytest.approx(8.0, abs=TOL)


def test_vista_sem_nada_dentro_do_volume_e_vazia_sem_chamar_desenho():
    K_ = K()
    f, g = C.modelo("IFC4", vaos=(C.PORTA,))
    chamadas = []
    c = K_.gerar_corte(f, C.corte(f, origem=(1000.0, 0.0, 0.0)), executor=contador(chamadas))  # volume a 1 km do modelo
    assert c.selecao.ids == () and c.n_paths == 0 and B.svg_valido(c.svg) and not [p for p in chamadas if p["op"] == "desenho"]
    assert c.caixas == ()


def test_pedido_ao_auxiliar_e_chamada_unica_de_desenho():
    K_ = K()
    f, g = C.modelo("IFC4", vaos=(C.PORTA,))
    gv, chamadas = C.corte(f), []
    c = K_.gerar_corte(f, gv, threads=3, limite_triangulos=12345, executor=contador(chamadas))
    d = [p for p in chamadas if p["op"] == "desenho"]
    assert len(d) == 1 and d[0]["vista"] == {"tipo": "CORTE", "guid": gv, "escala": 1.0} and d[0]["threads"] == 3 and d[0]["limite_triangulos"] == 12345
    assert d[0]["elementos"] == [[i, f.by_id(i).GlobalId] for i in c.selecao.ids]
    ps = inspect.signature(K_.gerar_corte).parameters
    novos = {"categorias_ocultas": (), "threads": None, "limite_triangulos": None, "limite_s": K_.auxiliar.LIMITE_PADRAO_S, "cancelar": None, "executor": None}
    assert list(ps)[:2] == ["ifc", "gid_vista"] and {n: ps[n].default for n in novos} == novos and all(ps[n].kind is inspect.Parameter.KEYWORD_ONLY for n in novos)


def test_vistas_invalidas_sao_recusadas_antes_do_executor():
    K_, V = K(), __import__("openbim_app.vistas_ifc", fromlist=["x"])
    from openbim_app.desenho.selecao import SelecaoInvalida
    f, g = C.modelo("IFC4")
    sem_bloco, sem_origem, planta = C.corte(f, nome="B"), C.corte(f, nome="O"), X.vista(f, "PLANTA", nome="Pl")
    f.by_guid(sem_bloco).Representation = None
    f.by_guid(sem_origem).ObjectPlacement = None
    for gid in (planta, sem_bloco, sem_origem):
        with pytest.raises(SelecaoInvalida):
            K_.gerar_corte(f, gid, executor=proibido)
    with pytest.raises(SelecaoInvalida):
        K_.gerar_corte(f, C.corte(f), categorias_ocultas=("IfcNaoExiste",), executor=proibido)
    with pytest.raises(V.VistaInexistente):
        K_.gerar_corte(f, "0000000000000000000000", executor=proibido)


def test_escala_da_vista_nao_muda_o_svg_nem_o_arquivo():
    K_ = K()
    svgs = {}
    for esc in ("1:100", "1:50", "1:500"):
        f, g = C.modelo("IFC4", vaos=(C.PORTA,))
        gv = C.corte(f, escala=esc)
        antes = f.to_string()
        svgs[esc] = K_.gerar_corte(f, gv, executor=executor_local()).svg
        assert f.to_string() == antes and f"Scale" in antes and esc in antes  # a vista do usuário segue na escala dela
        assert re.sub(r'ifc:guid="[^"]+"|id="[^"]+"', "", svgs[esc]) == re.sub(r'ifc:guid="[^"]+"|id="[^"]+"', "", svgs.get("1:100", svgs[esc]))
    assert svgs["1:50"].count("<path") == svgs["1:100"].count("<path") == svgs["1:500"].count("<path")


def test_oculto_some_deterministico_e_entrada_intacta():
    K_ = K()
    for esq in X.ESQUEMAS:
        f, g = C.modelo(esq, C.GEO, 100.0, 1.0, vaos=(C.PORTA,))
        gv = C.corte(f, C.GEO, 100.0, 1.0)
        antes, n_ann = f.to_string(), len(f.by_type("IfcAnnotation"))
        ligado, de_novo = K_.gerar_corte(f, gv, executor=executor_local()), K_.gerar_corte(f, gv, executor=executor_local())
        assert f.to_string() == antes and len(f.by_type("IfcAnnotation")) == n_ann and ligado.svg == de_novo.svg and ligado.selecao == de_novo.selecao
        assert "OBIM_Vista" not in antes and "AlturaCorte" not in antes
        um, tres = K_.gerar_corte(f, gv, threads=1, executor=executor_local()), K_.gerar_corte(f, gv, threads=3, executor=executor_local())
        assert um.n_paths == tres.n_paths == ligado.n_paths
        assert set(re.findall(r'ifc:guid="([^"]+)"', um.svg)) == set(re.findall(r'ifc:guid="([^"]+)"', tres.svg)) == set(re.findall(r'ifc:guid="([^"]+)"', ligado.svg))
        oculto = K_.gerar_corte(f, gv, categorias_ocultas=("IfcFurnishingElement",), executor=executor_local())
        assert oculto.selecao.ocultos_por_classe == {X.MOVEL[esq]: 1} and "M" not in {f.by_id(i).Name for i in oculto.selecao.ids}
        assert oculto.n_paths == ligado.n_paths - 4 and B.grupo(oculto.svg, g["P"]) is not None  # o móvel eram 4 linhas de vista
        assert f.to_string() == antes


def test_corte_ignora_cut_height_da_planta():
    K_ = K()
    f, g = C.modelo("IFC4", vaos=(C.PORTA,))
    gv = C.corte(f)
    base = K_.gerar_corte(f, gv, executor=executor_local()).svg
    ps = C.A.api("pset.add_pset", f, product=f.by_guid(gv), name="OBIM_View")
    C.A.api("pset.edit_pset", f, pset=ps, properties={"CutHeight": -3.0})  # inválida para a planta, sem sentido no corte
    assert K_.gerar_corte(f, gv, executor=executor_local()).svg == base and "OBIM_Vista" not in f.to_string()


@pytest.mark.parametrize("m", [C.MODELOS[1], C.MODELOS[3]])
def test_filho_real_igual_ao_executor_local(m):
    import multiprocessing
    K_ = K()
    esq, off, base, k = m
    f, g = C.modelo(esq, off, base, k, vaos=(C.PORTA,))
    gv = C.corte(f, off, base, k)
    loc, real = K_.gerar_corte(f, gv, executor=executor_local()), K_.gerar_corte(f, gv)
    assert real.svg == loc.svg and real.n_paths == loc.n_paths == 20 and real.selecao == loc.selecao and real.caixas == loc.caixas
    assert not multiprocessing.active_children()


CORTE_PY = __import__("pathlib").Path(__file__).resolve().parent.parent / "app" / "openbim_app" / "desenho" / "corte.py"


@pytest.mark.parametrize("proibido_", ["ifcopenshell.ifcopenshell_wrapper", ".iterator(", "ifcopenshell.geom", "serializers", "ifcopenshell.draw", "OBIM_Vista", "AlturaCorte", "OBIM_Projeto"])
def test_corte_py_sem_motor_nem_nomes_em_portugues(proibido_):
    assert CORTE_PY.exists(), "falta app/openbim_app/desenho/corte.py"
    assert proibido_ not in CORTE_PY.read_text(encoding="utf-8")  # texto cru, comentário incluído (mesmo critério da planta)


def test_importar_corte_nao_carrega_geometria():
    codigo = ("import sys, json\nimport openbim_app.desenho.corte\n"
              "print(json.dumps(sorted(m for m in sys.modules if m.startswith(('ifcopenshell.geom', 'ifcopenshell.draw', 'obim_geometria.desenho', 'obim_geometria.caixas', 'obim_geometria.local')))))\n")
    import json
    import os
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=120, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path), "LC_ALL": "C"})
    assert r.returncode == 0, r.stderr[-1500:]
    assert json.loads(r.stdout.strip().splitlines()[-1]) == []
