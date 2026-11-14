# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T19b, parte 3 (robustez de `linhas_visiveis`): memória e tempo com teto (grade adaptativa, triângulos grandes), validação de
entrada, triângulos duplicados e sondas analíticas que matam mutantes (triângulos pequenos, mapa de profundidade, orientação, aresta com 3 faces,
diagonal coplanar, sinal de tol_z). Memória/tempo rodam em subprocesso com malhas sintéticas de numpy. Régua e helpers vêm da parte 1."""
from __future__ import annotations

import json
import math
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pytest
from test_s06_t19b1_visibilidade_oraculo import _caixa, _cobertura, _junta, _lv, _segs

_T12 = _caixa(0, 0, 0, 1, 1, 1)[1].tolist()
_PRE = f"""import json,time,tracemalloc,numpy as np
from obim_geometria.visibilidade import linhas_visiveis as lv
U=np.array([(x,y,z) for z in (0,1) for x,y in ((0,0),(1,0),(1,1),(0,1))],float);T=np.array({_T12})
def boxes(ox,oy,s,h):
    v=(U[None]*np.array([s,s,h])+np.stack([ox,oy,0*ox],1)[:,None]).reshape(-1,3)
    return v,(T[None]+8*np.arange(len(ox))[:,None,None]).reshape(-1,3)
"""
_FIM = """
tracemalloc.start();t0=time.time();o=lv(v,t);dt=time.time()-t0
print(json.dumps([dt,tracemalloc.get_traced_memory()[1]/1e6,sum(float(np.hypot(*np.diff(p,axis=0).T).sum()) for p in o)]))"""

def _roda(gen):
    """Roda `linhas_visiveis` num subprocesso (teto de 4 GB de endereço) e devolve (segundos, pico em MB, comprimento total)."""
    raiz = str(Path(sys.modules[_lv().__module__].__file__).parent.parent)
    pre = None
    try:
        import resource
        pre = lambda: resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))  # noqa: E731
    except ImportError:
        pass
    r = subprocess.run([sys.executable, "-c", _PRE + gen + _FIM], capture_output=True, text=True, timeout=300,
                       env={"PYTHONPATH": raiz, "PATH": ""}, preexec_fn=pre)
    assert r.returncode == 0, f"processo morreu (memória estourada?): {r.stderr[-300:]}"
    return json.loads(r.stdout.strip().splitlines()[-1])

def test_caixa_enorme_nao_estoura_memoria():
    """Caixa 10x10 m (12 triângulos): a grade cresce (~6 milhões de células no máximo); o desenho é o mesmo (perímetro 40)."""
    dt, mb, comp = _roda("v,t=boxes(np.array([0.]),np.array([0.]),10,1)")
    assert mb < 1000 and dt < 10 and comp == pytest.approx(40.0, rel=0.01)

def test_duzentas_placas_espalhadas_nao_estouram_memoria():
    dt, mb, comp = _roda("ix,iy=np.meshgrid(np.arange(20.),np.arange(10.));v,t=boxes(ix.ravel(),iy.ravel(),0.5,0.1)")
    assert mb < 1000 and dt < 10 and comp == pytest.approx(400.0, rel=0.01)

def test_48_mil_triangulos_grandes_tempo_e_memoria_limitados():
    """4000 placas de 6 cm (48 mil triângulos, cada um com mais de 400 células): sem laço quadratico."""
    dt, mb, comp = _roda("ix,iy=np.meshgrid(np.arange(80.),np.arange(50.));v,t=boxes(ix.ravel()*0.1,iy.ravel()*0.1,0.06,0.01);assert len(t)==48000")
    assert dt < 4 and mb < 700 and comp == pytest.approx(960.0, rel=0.02)

def _base():
    v, t = _caixa(0, 0, 0, 1, 1, 1)
    return v, t

@pytest.mark.parametrize("mod", ["verts_2d", "tris_4col", "indice_negativo", "indice_fora"])
def test_entrada_invalida_levanta_valueerror(mod):
    v, t = _base()
    v, t = {"verts_2d": (v[:, :2], t), "tris_4col": (v, np.hstack([t, t[:, :1]])),
            "indice_negativo": (v, np.vstack([t, [[0, 1, -1]]])), "indice_fora": (v, np.vstack([t, [[0, 1, len(v)]]]))}[mod]
    with pytest.raises(ValueError, match=r"(?i)verts|tris|v[eé]rtice|tri[aâ]ngulo|[ií]ndice"):
        _lv()(v, t)

@pytest.mark.parametrize("ruim", [np.nan, np.inf, -np.inf])
def test_vertice_nao_finito_descarta_o_triangulo_sem_aviso(ruim):
    v, t = _base()
    v2, t2 = np.vstack([v, [[ruim, 0, 0], [3, 3, 1], [4, 3, 1]]]), np.vstack([t, [[8, 9, 10]]])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        got = _segs(_lv()(v2, t2))
    ref = _segs(_lv()(v, t))
    assert np.isfinite(got).all() and _cobertura(got, ref) >= 0.99 and _cobertura(ref, got) >= 0.99

def test_triangulos_duplicados_equivalem_a_malha_sem_duplicata():
    lv = _lv()
    v, t = _base()
    for tt in (np.vstack([t, t[:, [1, 2, 0]]]), np.vstack([t, t[:, ::-1]])):  # caixa toda duplicada: sem diagonal falsa no topo
        got, ref = _segs(lv(v, tt)), _segs(lv(v, t))
        assert _cobertura(got, ref) >= 0.99 and _cobertura(ref, got) >= 0.99
    tri = np.array([[0, 0, 0], [2, 0, 0], [0, 2, 0.0]])
    got = _segs(lv(tri, np.array([[0, 1, 2], [2, 0, 1]])))
    ref = np.array([[(0, 0), (2, 0)], [(2, 0), (0, 2)], [(0, 2), (0, 0)]], float)
    assert len(got) and _cobertura(got, ref) >= 0.99 and _cobertura(ref, got) >= 0.99

def _sub(v, t, k):
    """Subdivide cada triângulo em 4 (pontos médios das arestas), k vezes."""
    for _ in range(k):
        vs, cache, nt = list(v), {}, []
        def mid(i, j):
            c = (min(i, j), max(i, j))
            if c not in cache:
                cache[c] = len(vs)
                vs.append((v[i] + v[j]) / 2)
            return cache[c]
        for a, b, c in t:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nt += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
        v, t = np.array(vs), np.array(nt)
    return v, t

def _rot(v, graus, desloc=(0.0, 0.0)):
    c, s = math.cos(math.radians(graus)), math.sin(math.radians(graus))
    return np.stack([c * v[:, 0] - s * v[:, 1] + desloc[0], s * v[:, 0] + c * v[:, 1] + desloc[1], v[:, 2]], 1)

@pytest.mark.parametrize("graus", [0.0, 17.3])
@pytest.mark.parametrize("invertida", [False, True])
def test_malha_subdividida_igual_a_malha_grossa(graus, invertida):
    """Triângulos pequenos (3 a 6 mm, cabem em menos de 25 células de 2 mm) e o mapa de profundidade: mesmo desenho que a malha grossa (tol. 0,5 mm)."""
    v, t = _junta(_caixa(0, 0, 0, .05, .025, .025), _caixa(.025, .0125, 0, .075, .0375, .05))
    t = t[:, ::-1] if invertida else t
    vf, tf = _sub(v, t, 3)
    a, b = _segs(_lv()(_rot(v, graus), t)), _segs(_lv()(_rot(vf, graus), tf))
    assert len(a) and _cobertura(a, b, 5e-4) >= 0.99 and _cobertura(b, a, 5e-4) >= 0.99

def _trecho(segs, p0, p1):
    """(comprimento visível, parâmetro máximo) dos segmentos que ficam sobre a reta p0->p1 (até 0,1 mm)."""
    p0, d = np.array(p0, float), np.array(p1, float) - np.array(p0, float)
    L = math.hypot(*d)
    u, n = d / L, np.array([-d[1], d[0]]) / L
    rel = segs - p0
    along, perp = rel @ u, rel @ n
    k = (np.abs(perp) < 1e-4).all(1) & (along > -1e-4).all(1) & (along < L + 1e-4).all(1)
    al = along[k]
    return (np.abs(al[:, 1] - al[:, 0]).sum(), al.max()) if len(al) else (0.0, 0.0)

@pytest.mark.parametrize("invertida", [False, True])
def test_oclusao_parcial_girada_fora_da_grade_corta_no_ponto_certo(invertida):
    """A=[0,2]x[0,1]x[0,1], B=[1,3]x[.5,1.5]x[0,2], girado 17,3 graus e deslocado (1,37 mm; 0,71 mm). Visível: aresta y=1 até x=1; aresta x=2 até y=.5."""
    v, t = _junta(_caixa(0, 0, 0, 2, 1, 1), _caixa(1, 0.5, 0, 3, 1.5, 2))
    t = t[:, ::-1] if invertida else t
    segs = _segs(_lv()(_rot(v, 17.3, (0.00137, 0.00071)), t))
    p = lambda x, y: _rot(np.array([[x, y, 0.0]]), 17.3, (0.00137, 0.00071))[0, :2]  # noqa: E731
    c1, m1 = _trecho(segs, p(0, 1), p(2, 1))
    c2, m2 = _trecho(segs, p(2, 0), p(2, 1))
    assert (c1, m1) == (pytest.approx(1.0, abs=3e-3), pytest.approx(1.0, abs=2e-3))
    assert (c2, m2) == (pytest.approx(0.5, abs=3e-3), pytest.approx(0.5, abs=2e-3))

def test_trecho_final_visivel_de_uma_aresta():
    """Caixa [0,4]x[0,1]x[0,.5] sob placa z=1 sobre [-1,3]x[-1,2]: aresta y=1 visível só de x=3 a 4."""
    v, t = _junta(_caixa(0, 0, 0, 4, 1, 0.5), (np.array([[-1, -1, 1], [3, -1, 1], [3, 2, 1], [-1, 2, 1.0]]), np.array([[0, 1, 2], [0, 2, 3]])))
    c, m = _trecho(_segs(_lv()(v, t)), (0, 1), (4, 1))
    assert c == pytest.approx(1.0, abs=2e-3) and m == pytest.approx(4.0, abs=1e-3)
    ini = _segs(_lv()(v, t))
    assert _cobertura((np.array([[1.5, 1.0], [2.5, 1.0]]), np.array([1.0, 1.0])), ini, 1e-3) == 0.0

@pytest.mark.parametrize("dz,visivel", [(0.01, True), (5e-5, True), (-5e-5, True), (-5e-4, False), (-0.01, False)])
def test_tol_z_aresta_acima_ou_abaixo_da_superficie(dz, visivel):
    """Placa z=1 sobre [0,4]^2; triângulo plano em z=1+dz. Com tol_z=1e-4: até 5e-5 abaixo conta visível; 5e-4 abaixo fica escondido."""
    v = np.array([[0, 0, 1], [4, 0, 1], [4, 4, 1], [0, 4, 1], [1, 1, 1 + dz], [3, 1, 1 + dz], [2, 3, 1 + dz]], float)
    got = _segs(_lv()(v, np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]]), tol_z=1e-4))
    ref = np.array([[(1, 1), (3, 1)], [(3, 1), (2, 3)], [(2, 3), (1, 1)]], float)
    cob = _cobertura(ref, got)
    assert cob >= 0.99 if visivel else cob <= 0.01

@pytest.mark.parametrize("dz,visivel", [(0.01, True), (5e-5, True), (-5e-5, True), (-5e-4, False), (-0.01, False)])
def test_tol_z_aresta_paralela_a_rampa(dz, visivel):
    """Rampa z=2y sobre [0,2]^2 (declive 2 em y: a margem do mapa de profundidade pesa); aresta horizontal em y=1 (z=2), dz acima ou abaixo (tol_z=1e-4)."""
    v = np.array([[0, 0, 0], [2, 0, 0], [2, 2, 4], [0, 2, 4], [.5, 1, 2 + dz], [1.5, 1, 2 + dz], [1, 1.5, 10]], float)
    got = _segs(_lv()(v, np.array([[0, 1, 2], [0, 2, 3], [4, 5, 6]]), tol_z=1e-4))
    cob = _cobertura(np.array([[(.6, 1), (1.4, 1)]], float), got)
    assert cob >= 0.99 if visivel else cob <= 0.01

def test_aresta_atravessando_pente_de_faixas_estreitas():
    """Aresta y=0 (z=1, de x=1,9 mm a 1,0019 m, fora da grade) sob triângulos z=2 que em y=0 têm 3,7 mm de largura e passo 6 mm: visível só nos vãos.
    Cada faixa cobre uma célula inteira de 2 mm e corta as vizinhas; pega o mínimo (e não o máximo) dos 4 cantos do mapa."""
    e0, xs = 0.0019, np.arange(0.0005, 1.0, 0.006)
    fv = np.array([p for x in xs for p in ((x - .0018, -.05, 2.0), (x + .0055, -.05, 2.0), (x + .0018, .05, 2.0))])  # largura 3,7 mm em y=0
    ft = np.arange(3 * len(xs)).reshape(-1, 3)
    v, t = _junta((np.array([[e0, 0, 1], [e0 + 1, 0, 1], [0, .3, 1.0]]), np.array([[0, 1, 2]])), (fv, ft))
    c, _ = _trecho(_segs(_lv()(v, t)), (e0, 0), (e0 + 1, 0))
    assert c == pytest.approx(1.0 - sum(max(0.0, min(x + .0037, e0 + 1) - max(x, e0)) for x in xs), abs=0.02)

def test_aresta_com_tres_faces_e_desenhada():
    v = np.array([[0, 0, 0], [1, 0, 0], [0.5, 1, 0], [0.5, 0.6, 0], [0.5, -1, 0]], float)
    got = _segs(_lv()(v, np.array([[0, 1, 2], [0, 1, 3], [1, 0, 4]])))
    assert _cobertura(np.array([[(0, 0), (1, 0)]], float), got) >= 0.99

def test_diagonal_coplanar_nao_e_desenhada():
    v = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0.0]])
    got = _segs(_lv()(v, np.array([[0, 1, 2], [0, 2, 3]])))
    per = np.array([[(0, 0), (1, 0)], [(1, 0), (1, 1)], [(1, 1), (0, 1)], [(0, 1), (0, 0)]], float)
    assert _cobertura(got, per) >= 0.99 and _cobertura(per, got) >= 0.99

_TUBOS = """import math
v,t,n=[],[],0
th=2*math.pi*np.arange(64)/64
for k in range({n}):
    a=np.stack([np.zeros(64),0.15*k+0.025*np.cos(th),1+0.025*np.sin(th)],1)
    v.append(np.vstack([a,a+[20,0,0]]));t.append(np.array([(i,(i+1)%64,64+(i+1)%64) for i in range(64)]+[(i,64+(i+1)%64,64+i) for i in range(64)])+n*128);n+=1
v,t=np.vstack(v),np.vstack(t);c,s=math.cos(math.pi/6),math.sin(math.pi/6)
v=np.stack([c*v[:,0]-s*v[:,1],s*v[:,0]+c*v[:,1],v[:,2]],1)"""

def test_tubos_longos_na_diagonal_tempo_limitado_e_quase_linear():
    """Tubos de 20 m girados 30 graus (triângulos longos e finos, caixa 2D enorme): 50 tubos x 64 segmentos em < 5 s; dobrar os triângulos custa < 3,2x."""
    base, dobro, um = _roda(_TUBOS.format(n=25)), _roda(_TUBOS.format(n=50)), _roda(_TUBOS.format(n=1))
    assert dobro[0] < 5 and dobro[0] < 3.2 * max(base[0], 0.3)
    # tubos afastados não se escondem: o desenho de N tubos é N vezes o de um (confere a geometria da margem da faixa orientada)
    assert dobro[2] == pytest.approx(50 * um[2], rel=2e-3) and base[2] == pytest.approx(25 * um[2], rel=2e-3)

@pytest.mark.parametrize("w", [1e-2, 1e-3, 1e-4])
def test_lasca_girada_de_ponta_aguda_nao_esconde_a_aresta_que_sai_pela_ponta(w):
    """Lasca de 20 m (ponta em (0,0,1), base em x=-20, meia largura w: ângulos da ponta 1e-3, 1e-4, 2e-5 rad); aresta y=0 em z=0,9 passa sob ela
    e sai pela ponta: visível de x=0 a 0,08 (tol. 5 mm)."""
    v = np.array([[0, 0, 1.0], [-20, -w, 0], [-20, w, 0], [-.5, 0, .9], [.08, 0, .9], [.04, -.3, .9]])
    c, m = _trecho(_segs(_lv()(_rot(v, 30.0), np.array([[0, 1, 2], [3, 4, 5]]))), _rot(v, 30.0)[3, :2], _rot(v, 30.0)[4, :2])
    assert m == pytest.approx(0.58, abs=5e-3) and c == pytest.approx(0.08, abs=5e-3)

def test_vao_visivel_entre_duas_tampas_com_subtrecho_alinhado_a_grade():
    """Grade de 2 mm alinhada em x=0; aresta de 0 a 0,02 (z=1) sob duas tampas z=2 que deixam o vão x de 0,01415 a 0,01585 (y=0)."""
    t = lambda *p: (np.array(p, float), np.array([[0, 1, 2]]))  # noqa: E731
    v, tr = _junta(t((0, 0, 1), (.02, 0, 1), (.01, .3, 1)), t((.0115, -.05, 2), (.0142, .001, 2), (.0115, .05, 2)), t((.0185, -.05, 2), (.0185, .05, 2), (.0158, .001, 2)))
    assert _cobertura(np.array([[(.0145, 0), (.0155, 0)]], float), _segs(_lv()(v, tr)), 1e-4) >= 0.99

@pytest.mark.parametrize("kw", [{"tol_z": -1e-4}, {"tol_z": float("nan")}, {"min_len": -1.0}, {"min_len": float("nan")}, {"angulo_graus": -1.0}, {"angulo_graus": float("nan")},
                                {"tol_z": math.inf}, {"min_len": math.inf}, {"angulo_graus": math.inf}, {"tol_z": -math.inf}, {"min_len": -math.inf}, {"angulo_graus": -math.inf}])
def test_parametros_negativos_ou_nan_levantam_valueerror(kw):
    with pytest.raises(ValueError):
        _lv()(*_base(), **kw)

def test_verts_vazio_com_tris_e_coordenada_enorme_levantam_valueerror():
    v, t = _base()
    with pytest.raises(ValueError):
        _lv()(np.zeros((0, 3)), t)
    with pytest.raises(ValueError):
        _lv()(v * 2e12, t)

def test_cone_de_512_lados_e_rapido():
    dt, mb, comp = _roda("th=2*math.pi*np.arange(512)/512;v=np.vstack([[0,0,1],np.stack([np.cos(th),np.sin(th),0*th],1)]);t=np.array([(0,1+i,1+(i+1)%512) for i in range(512)])"
                         .replace("th=", "import math;th=", 1))
    assert dt < 1.0

def _leque(dz_ponta):
    """Plano z=1+10x (triângulo A(0,0), B(1,-.5), C(1,.5)); aresta de A até E=(.6,0) com a ponta dz_ponta acima do plano."""
    zf = lambda x, y: 1 + 10 * x  # noqa: E731
    v = np.array([[0, 0, 1], [1, -.5, zf(1, 0)], [1, .5, zf(1, 0)], [.6, 0, zf(.6, 0) + dz_ponta], [.6, .1, zf(.6, .1) - .5]], float)
    return _trecho(_segs(_lv()(v, np.array([[0, 1, 2], [0, 3, 4]]))), (0, 0), (.6, 0))

def test_aresta_que_sai_de_vertice_de_triangulo_inclinado_corta_no_ponto_certo():
    """Ponta 5 mm abaixo do plano (inclinação 10): visível só de 0 a 0,012 (a aresta fica 1e-4 abaixo em x=0,012)."""
    c, m = _leque(-.005)
    assert c == pytest.approx(0.012, abs=4e-3) and m < 0.02

def test_aresta_de_vertice_de_triangulo_inclinado_com_ponta_acima_fica_inteira():
    c, m = _leque(+.005)
    assert c == pytest.approx(0.6, abs=5e-3)

@pytest.mark.parametrize("sinal", ["+x", "-x", "+y", "-y"])
def test_lasca_alinhada_aos_eixos_nao_esconde_a_aresta_que_sai_pela_ponta(sinal):
    """Mesma lasca (ângulo 2e-5 rad) alinhada a cada eixo, sem rotação: pega a retirada de um dos 4 cortes da caixa do triângulo."""
    f = {"+x": lambda p: p, "-x": lambda p: -p, "+y": lambda p: p[:, ::-1], "-y": lambda p: -p[:, ::-1]}[sinal]
    xy = np.array([[0, 0], [-20, -1e-4], [-20, 1e-4], [-.5, 0], [.08, 0], [.04, -.3]], float)
    v = np.column_stack([f(xy), [1, 0, 0, .9, .9, .9]])
    c, m = _trecho(_segs(_lv()(v, np.array([[0, 1, 2], [3, 4, 5]]))), v[3, :2], v[4, :2])
    assert c == pytest.approx(0.08, abs=5e-3) and m == pytest.approx(0.58, abs=5e-3)

@pytest.mark.parametrize("min_len", [1e-6, 0.0])
def test_min_len_abaixo_de_1e_5_levanta_valueerror(min_len):
    with pytest.raises(ValueError):
        _lv()(*_base(), min_len=min_len)

@pytest.mark.parametrize("min_len", [1e-5, 1e-4])
def test_min_len_a_partir_de_1e_5_e_aceito(min_len):
    assert len(_lv()(*_base(), min_len=min_len)) > 0
