# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S06-T25: chave incremental do cache de desenho, cancelável e gentil com o GIL.
Contrato: `cache.CacheCancelado(Exception)`, `CacheDesenho.chave(ifc, pedido, cancelar=None) -> str`
(hash sha256 incremental: um `json.dumps` por elemento e por contexto; checa `cancelar` a cada elemento e
a cada ~1000 nós em `_serializar`; determinística em 3 processos; sensível a elemento/estilo/relação/contexto;
ordem de `pedido["elementos"]` significativa fixada; 4 threads não travam pulso 10 ms > 100 ms); chamadores
`planta`/`corte`/`refino` repassam `cancelar`, convertem `CacheCancelado` em `DesenhoCancelado` e não gravam.
"""
from __future__ import annotations

import inspect, json, os, subprocess, sys, threading, time
from pathlib import Path

import pytest
import s06_t07_aux as X
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from s06_t15i_aux import ExecutorEspiao, auxiliar, corte, planta

from openbim_app.desenho import cache as M, refino

CASA_SIMPLES = Path(__file__).resolve().parent / "amostras" / "casa-simples.ifc"
RAIZ_APP = Path(__file__).resolve().parent.parent / "app"


def _ifc_api():
    exigir()
    import ifcopenshell, ifcopenshell.api
    return ifcopenshell, ifcopenshell.api


def _exigir_cache_cancelado():
    exc_cls = getattr(M, "CacheCancelado", None)
    assert exc_cls is not None, "cache.CacheCancelado ainda não existe"
    assert issubclass(exc_cls, Exception), "CacheCancelado deve herdar de Exception"
    return exc_cls


def _criar_ifc_sintetico(caminho: Path, n_paredes: int = 6, props: int = 2, *, estilo: bool = False, vista: bool = False):
    """Cria IFC4 sintético via ifcopenshell.api e salva em `caminho`."""
    _ifc, api = _ifc_api()
    f = api.run("project.create_file", version="IFC4")
    proj = api.run("root.create_entity", f, ifc_class="IfcProject", name="Projeto_T25")
    api.run("unit.assign_unit", f)
    ctx = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno_T25")
    bld = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Predio_T25")
    pav = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pavimento_T25")
    pav.Elevation = 0.0
    for pai, filho in ((proj, site), (site, bld), (bld, pav)):
        api.run("aggregate.assign_object", f, relating_object=pai, products=[filho])
    paredes, surf = [], None
    for i in range(n_paredes):
        w = api.run("root.create_entity", f, ifc_class="IfcWall", name=f"PAREDE_T25_{i:04d}")
        api.run("spatial.assign_container", f, relating_structure=pav, products=[w])
        rep = api.run("geometry.add_wall_representation", f, context=body, length=2.0 + i * 0.1, height=3.0, thickness=0.2)
        api.run("geometry.assign_representation", f, product=w, representation=rep)
        if props > 0:
            ps = api.run("pset.add_pset", f, product=w, name="Pset_WallCommon")
            api.run("pset.edit_pset", f, pset=ps, properties={f"Prop_{j}": f"Val_{i}_{j}" for j in range(props)})
        if estilo and i == 0:
            est = api.run("style.add_style", f, name="Estilo_T25")
            surf = api.run(
                "style.add_surface_style", f, style=est, ifc_class="IfcSurfaceStyleShading",
                attributes={"SurfaceColour": {"Name": None, "Red": 0.2, "Green": 0.3, "Blue": 0.4}},
            )
            api.run("style.assign_representation_styles", f, shape_representation=rep, styles=[est])
        paredes.append(w)
    vdict = {"tipo": "PLANTA", "altura_corte_m": 1.2, "pavimento": pav.GlobalId, "escala": 1.0}
    anot = api.run("root.create_entity", f, ifc_class="IfcAnnotation", name="VISTA_CTX_T25") if vista else None
    if anot is not None:
        vdict["guid"] = anot.GlobalId
    f.write(str(caminho))
    ped = {"protocolo": 1, "op": "desenho", "elementos": [[w.id(), w.GlobalId] for w in paredes], "vista": vdict, "moveis_como_caixa": False}
    return f, ped, {"projeto": proj, "pavimento": pav, "paredes": paredes, "anotacao": anot, "surf": surf}


def _pedido_casa_simples():
    ifc, _api = _ifc_api()
    f = ifc.open(str(CASA_SIMPLES))
    pav = f.by_type("IfcBuildingStorey")[0]
    elems = list(f.by_type("IfcWall")) + list(f.by_type("IfcSlab"))
    ped = {
        "protocolo": 1, "op": "desenho", "elementos": [[e.id(), e.GlobalId] for e in elems],
        "vista": {"tipo": "PLANTA", "altura_corte_m": 1.2, "pavimento": pav.GlobalId, "escala": 0.001},
        "moveis_como_caixa": False,
    }
    return f, ped, elems


@pytest.fixture(scope="module")
def ifc_grande(tmp_path_factory):
    """IFC sintético grande (500 paredes x 20 props) gerado 1x por módulo em tmp_path."""
    arq = tmp_path_factory.mktemp("t25_grande") / "grande.ifc"
    f, ped, _meta = _criar_ifc_sintetico(arq, n_paredes=500, props=20, vista=True)
    return arq, f, ped


class _EventContador(threading.Event):
    def __init__(self, disparar_em: int | None = None):
        super().__init__()
        self.chamadas, self._disparar_em = 0, disparar_em

    def is_set(self) -> bool:
        self.chamadas += 1
        if self._disparar_em is not None and self.chamadas >= self._disparar_em:
            self.set()
        return super().is_set()


class _CacheEspiaoCancel(M.CacheDesenho):
    def __init__(self, pasta, *, disparar_no_chave: bool = False):
        super().__init__(pasta)
        self.disparar_no_chave, self.cancelar_recebidos, self.guardou = disparar_no_chave, [], 0

    def chave(self, ifc, pedido: dict, cancelar: threading.Event | None = None) -> str:
        self.cancelar_recebidos.append(cancelar)
        if self.disparar_no_chave and cancelar is not None:
            cancelar.set()
        return super().chave(ifc, pedido, cancelar=cancelar)

    def guardar(self, chave: str, dados: dict) -> bool:
        self.guardou += 1
        return super().guardar(chave, dados)


def _eh_sha256_hex(v: str) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(ch in "0123456789abcdef" for ch in v)


def test_contrato_assinatura_e_excecao(tmp_path):
    """CacheCancelado existe e chave() aceita cancelar opcional (padrão None)."""
    _exigir_cache_cancelado()
    sig = inspect.signature(M.CacheDesenho.chave)
    assert "cancelar" in sig.parameters and sig.parameters["cancelar"].default is None
    f, ped, _ = _pedido_casa_simples()
    c = M.CacheDesenho(tmp_path / "cache")
    k1 = c.chave(f, ped)
    assert _eh_sha256_hex(k1) and k1 == c.chave(f, ped, cancelar=None) == c.chave(f, ped, cancelar=threading.Event())


def test_mutante1_cancelar_antes_levanta_rapido(ifc_grande, tmp_path):
    """Mutante 1: cancelar setado antes levanta CacheCancelado em < 0,2 s."""
    CacheCancelado = _exigir_cache_cancelado()
    _arq, f, ped = ifc_grande
    ev = threading.Event()
    ev.set()
    t0 = time.monotonic()
    with pytest.raises(CacheCancelado):
        M.CacheDesenho(tmp_path / "cache").chave(f, ped, cancelar=ev)
    assert time.monotonic() - t0 < 0.2


def test_mutante1_cancelar_no_meio_elementos_levanta_rapido(ifc_grande, tmp_path, monkeypatch):
    """Mutante 1: cancelar no meio levanta CacheCancelado em < 0,2 s sem percorrer todos os elementos."""
    CacheCancelado = _exigir_cache_cancelado()
    _arq, f, ped = ifc_grande
    ev, dumps_real, chamadas = threading.Event(), json.dumps, 0

    def espiao(obj, *args, **kwargs):
        nonlocal chamadas
        chamadas += 1
        return dumps_real(obj, *args, **kwargs)

    monkeypatch.setattr(json, "dumps", espiao)
    monkeypatch.setattr(M.json, "dumps", espiao)
    timer = threading.Timer(0.015, ev.set)
    t0 = time.monotonic()
    timer.start()
    try:
        with pytest.raises(CacheCancelado):
            M.CacheDesenho(tmp_path / "cache").chave(f, ped, cancelar=ev)
    finally:
        timer.cancel()
    assert time.monotonic() - t0 < 0.2 and chamadas < len(ped["elementos"])


def test_mutante1_cancelar_em_serializar_a_cada_1000_nos(tmp_path):
    """Mutante 1: `_serializar` checa `cancelar` a cada ~1000 nós num único elemento grande."""
    CacheCancelado = _exigir_cache_cancelado()
    f, ped_base, meta = _criar_ifc_sintetico(tmp_path / "um_grande.ifc", n_paredes=2, props=1)
    _ifc, api = _ifc_api()
    w_peq, w_grd = meta["paredes"]
    ps = api.run("pset.add_pset", f, product=w_grd, name="Pset_Gigante")
    api.run("pset.edit_pset", f, pset=ps, properties={f"G_{j:04d}": j for j in range(4500)})
    c = M.CacheDesenho(tmp_path / "cache")
    ped_peq = {**ped_base, "elementos": [[w_peq.id(), w_peq.GlobalId]]}
    ped_grd = {**ped_base, "elementos": [[w_grd.id(), w_grd.GlobalId]]}
    ev_peq, ev_grd = _EventContador(), _EventContador()
    c.chave(f, ped_peq, cancelar=ev_peq)
    c.chave(f, ped_grd, cancelar=ev_grd)
    assert ev_grd.chamadas - ev_peq.chamadas >= 4
    ev_meio = _EventContador(disparar_em=ev_peq.chamadas + 2)
    with pytest.raises(CacheCancelado):
        c.chave(f, ped_grd, cancelar=ev_meio)
    assert ev_meio.chamadas < ev_grd.chamadas


def test_mutante2_json_dumps_incremental_sem_conjunto(tmp_path, monkeypatch):
    """Mutante 2: nenhuma chamada `json.dumps` serializa mais de 1 elemento; contexto separado."""
    f_sin, ped_sin, meta = _criar_ifc_sintetico(tmp_path / "inc.ifc", n_paredes=6, props=2, vista=True)
    f_casa, ped_casa, elems_casa = _pedido_casa_simples()
    c, dumps_real = M.CacheDesenho(tmp_path / "cache"), json.dumps
    for rotulo, f, ped, nomes, ctx_nome in (
        ("sintetico", f_sin, ped_sin, [w.Name for w in meta["paredes"]], "VISTA_CTX_T25"),
        ("casa-simples", f_casa, ped_casa, [e.Name for e in elems_casa], None),
    ):
        payloads: list[str] = []

        def espiao(obj, *args, **kwargs):
            s = dumps_real(obj, *args, **kwargs)
            payloads.append(s)
            return s

        monkeypatch.setattr(json, "dumps", espiao)
        monkeypatch.setattr(M.json, "dumps", espiao)
        assert _eh_sha256_hex(c.chave(f, ped))
        assert len(payloads) >= len(nomes) + 1, f"{rotulo}: poucas chamadas json.dumps ({len(payloads)})"
        vistos: set[str] = set()
        for p in payloads:
            presentes = [m for m in nomes if m in p]
            assert len(presentes) <= 1, f"{rotulo}: json.dumps agregou elementos: {presentes}"
            vistos.update(presentes)
        assert vistos == set(nomes), f"{rotulo}: faltaram elementos: {set(nomes) - vistos}"
        if ctx_nome is not None:
            ctx_calls = [p for p in payloads if ctx_nome in p]
            assert ctx_calls and all(sum(1 for m in nomes if m in p) == 0 for p in ctx_calls)


def test_mutante3_sensivel_a_elemento_estilo_relacao_e_contexto(tmp_path, monkeypatch):
    """Mutante 3: mudanças em elemento, estilo, relação, contexto ou versão mudam a chave; `threads` não."""
    f, ped, meta = _criar_ifc_sintetico(tmp_path / "sensivel.ifc", n_paredes=4, props=2, estilo=True, vista=True)
    ifc, api = _ifc_api()
    c = M.CacheDesenho(tmp_path / "cache")
    k0 = c.chave(f, ped)
    assert c.chave(f, {**ped, "threads": 1}) == k0 == c.chave(f, {**ped, "threads": 8})
    assert c.chave(f, {**ped, "elementos": ped["elementos"][:-1]}) != k0
    w0 = meta["paredes"][0]
    w0.Name = "PAREDE_ALTERADA"
    assert c.chave(f, ped) != k0
    w0.Name = "PAREDE_T25_0000"
    assert c.chave(f, ped) == k0
    meta["surf"].SurfaceColour.Red = 0.95
    assert c.chave(f, ped) != k0
    meta["surf"].SurfaceColour.Red = 0.2
    assert c.chave(f, ped) == k0
    ps = api.run("pset.add_pset", f, product=w0, name="Pset_Extra")
    api.run("pset.edit_pset", f, pset=ps, properties={"Carga": "Alta"})
    k_pset = c.chave(f, ped)
    assert k_pset != k0
    mat = api.run("material.add_material", f, name="Concreto_T25")
    api.run("material.assign_material", f, products=[w0], material=mat)
    k_mat = c.chave(f, ped)
    assert k_mat != k_pset
    vao = api.run("root.create_entity", f, ifc_class="IfcOpeningElement", name="Vao_T25")
    f.create_entity("IfcRelVoidsElement", GlobalId=ifc.guid.new(), RelatingBuildingElement=w0, RelatedOpeningElement=vao)
    k_vao = c.chave(f, ped)
    assert k_vao != k_mat
    meta["anotacao"].Name = "VISTA_CTX_ALTERADA"
    k_anot = c.chave(f, ped)
    assert k_anot != k_vao
    meta["pavimento"].Elevation = 3.0
    k_pav = c.chave(f, ped)
    assert k_pav != k_anot
    ulen = next(u for u in meta["projeto"].UnitsInContext.Units if u.UnitType == "LENGTHUNIT")
    ulen.Prefix = None if ulen.Prefix == "MILLI" else "MILLI"
    k_uni = c.chave(f, ped)
    assert k_uni != k_pav and c.chave(f, {**ped, "moveis_como_caixa": True}) != k_uni
    monkeypatch.setattr(M, "VERSAO_MODULO", "t25-outra-versao")
    assert c.chave(f, ped) != k_uni


def test_mutante4_determinismo_entre_3_processos(tmp_path):
    """Mutante 4: 3 processos com PYTHONHASHSEED e ordens de dict distintos geram a mesma chave."""
    arq_sin = tmp_path / "det.ifc"
    f_sin, ped_sin, _ = _criar_ifc_sintetico(arq_sin, n_paredes=5, props=3, estilo=True, vista=True)
    f_casa, ped_casa, _ = _pedido_casa_simples()
    c = M.CacheDesenho(tmp_path / "cache")
    script = (
        "import json, sys, ifcopenshell; from openbim_app.desenho.cache import CacheDesenho; "
        "print(CacheDesenho('/nao/usado').chave(ifcopenshell.open(sys.argv[1]), json.loads(sys.argv[2])))"
    )
    for caminho, f_local, ped in ((CASA_SIMPLES, f_casa, ped_casa), (arq_sin, f_sin, ped_sin)):
        esperada, chaves = c.chave(f_local, ped), []
        for idx, seed in enumerate(("1", "42", "99999")):
            ks, vks = list(ped.keys()), list(ped["vista"].keys())
            if idx == 1:
                ks.reverse(), vks.reverse()
            elif idx == 2:
                ks, vks = ks[1:] + ks[:1], vks[1:] + vks[:1]
            ped_rot = {k: ({vk: ped["vista"][vk] for vk in vks} if k == "vista" else ped[k]) for k in ks}
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(RAIZ_APP)}
            proc = subprocess.run([sys.executable, "-c", script, str(caminho), json.dumps(ped_rot)], capture_output=True, text=True, check=True, env=env, timeout=30)
            chaves.append(proc.stdout.strip())
        assert len(set(chaves)) == 1 and chaves[0] == esperada, f"divergência ({caminho.name}): {chaves}"


def test_mutante5_ordem_dos_elementos_muda_a_chave(tmp_path):
    """Mutante 5: comportamento atual fixado — ordem de `pedido['elementos']` muda a chave."""
    f_sin, ped_sin, _ = _criar_ifc_sintetico(tmp_path / "ordem.ifc", n_paredes=4, props=1)
    f_casa, ped_casa, _ = _pedido_casa_simples()
    c = M.CacheDesenho(tmp_path / "cache")
    for f, ped in ((f_casa, ped_casa), (f_sin, ped_sin)):
        el, k0 = ped["elementos"], c.chave(f, ped)
        assert c.chave(f, {**ped, "elementos": [list(e) for e in el]}) == k0
        k_inv = c.chave(f, {**ped, "elementos": list(reversed(el))})
        k_swp = c.chave(f, {**ped, "elementos": [el[1], el[0], *el[2:]]})
        assert k_inv != k0 and k_swp != k0 and k_swp != k_inv


def test_tempo_mutante6_gil_4_threads_pulso_10ms(ifc_grande, tmp_path):
    """[TESTE DE TEMPO] Mutante 6: 4 threads em `chave` não travam pulso de 10 ms por > 100 ms (folga 5x)."""
    _arq, f, ped = ifc_grande
    c, parar, gaps, erros, chaves = M.CacheDesenho(tmp_path / "cache"), threading.Event(), [], [], []

    def pulso():
        ant = time.perf_counter()
        while not parar.is_set():
            time.sleep(0.010)
            agora = time.perf_counter()
            gaps.append(agora - ant)
            ant = agora

    def trab():
        try:
            chaves.append(c.chave(f, ped))
        except BaseException as exc:  # pragma: no cover
            erros.append(exc)

    tp = threading.Thread(target=pulso)
    tp.start()
    ts = [threading.Thread(target=trab) for _ in range(4)]
    for t in ts: t.start()
    for t in ts: t.join(timeout=30)
    parar.set()
    tp.join(timeout=5)
    assert not erros and len(chaves) == 4 and len(set(chaves)) == 1 and len(gaps) >= 5
    maior_ms = max(gaps) * 1000.0
    assert maior_ms <= 100.0, f"GIL travou pulso de 10 ms por {maior_ms:.1f} ms (limite 100 ms)"


def _checar_chamador_cancelado(pasta: Path, esp_c: _CacheEspiaoCancel, ev: threading.Event, fn, sem_exec):
    CacheCancelado = _exigir_cache_cancelado()
    with pytest.raises(auxiliar.DesenhoCancelado) as info:
        fn()
    assert not isinstance(info.value, CacheCancelado)
    assert esp_c.cancelar_recebidos == [ev] and sem_exec()
    assert esp_c.guardou == 0 and not list(pasta.rglob("*"))


def test_mutante7_planta_engole_cache_cancelado_e_nao_grava(tmp_path):
    """Mutante 7: `planta.gerar_planta` repassa `cancelar`, trata `CacheCancelado` e não grava."""
    _exigir_cache_cancelado()
    exigir()
    f, pavs = X.estrutura("IFC4")
    X.conter(f, pavs[0], X.caixa(f, "IfcWall", "p1", 0.0, 0.0, 0.0, 2.0, 0.2, 2.0))
    gid = X.vista(f, "PLANTA", pavs[0], nome="VP")
    for no_chave in (False, True):
        pasta = tmp_path / f"cp_{int(no_chave)}"
        esp_c, esp_e, ev = _CacheEspiaoCancel(pasta, disparar_no_chave=no_chave), ExecutorEspiao(), threading.Event()
        if not no_chave:
            ev.set()
        _checar_chamador_cancelado(pasta, esp_c, ev, lambda: planta.gerar_planta(f, gid, cache=esp_c, cancelar=ev, executor=esp_e), lambda: esp_e.pedidos_desenho == [])


def test_mutante7_corte_engole_cache_cancelado_e_nao_grava(tmp_path):
    """Mutante 7: `corte.gerar_corte` repassa `cancelar`, trata `CacheCancelado` e não grava."""
    _exigir_cache_cancelado()
    exigir()
    f, _g = C.modelo("IFC4")
    gid, pasta = C.corte(f), tmp_path / "cc"
    esp_c, esp_e, ev = _CacheEspiaoCancel(pasta, disparar_no_chave=True), ExecutorEspiao(), threading.Event()
    _checar_chamador_cancelado(pasta, esp_c, ev, lambda: corte.gerar_corte(f, gid, cache=esp_c, cancelar=ev, executor=esp_e), lambda: esp_e.pedidos_desenho == [])


def test_mutante7_refino_engole_cache_cancelado_e_nao_grava(tmp_path):
    """Mutante 7: `refino.refinar_pesados` repassa `cancelar`, trata `CacheCancelado` e não grava."""
    _exigir_cache_cancelado()
    f, ped, elems = _pedido_casa_simples()
    w = elems[0]
    res = {"svg": f'<svg xmlns:ifc="x"><g ifc:guid="{w.GlobalId}" data-silhueta="1"><path d="M 0,0 L 1,0 Z"/></g></svg>', "pesados": [{"id": w.id(), "guid": w.GlobalId, "faces": 120}]}
    pasta, chamadas = tmp_path / "cr", []
    esp_c, ev = _CacheEspiaoCancel(pasta, disparar_no_chave=True), threading.Event()
    _checar_chamador_cancelado(pasta, esp_c, ev, lambda: refino.refinar_pesados(f, ped, res, cache=esp_c, cancelar=ev, executor=chamadas.append), lambda: chamadas == [])


# Mutantes derrubados:
# 1. `cancelar` ignorado (antes, meio < 0,2 s, e ~1000 nós em `_serializar`): test_mutante1_*
# 2. Um `json.dumps` do conjunto (<= 1 elemento por payload; contexto separado): test_mutante2_json_dumps_incremental_sem_conjunto
# 3. Chave igual p/ pedidos diferentes (elemento, estilo, pset/material/abertura, contexto, versão): test_mutante3_sensivel_*
# 4. Chave não determinística entre 3 processos (PYTHONHASHSEED/ordem de dicts): test_mutante4_determinismo_entre_3_processos
# 5. Ordem de `pedido["elementos"]` ignorada (comportamento atual fixado: muda chave): test_mutante5_ordem_dos_elementos_muda_a_chave
# 6. GIL travado > 100 ms com 4 threads e pulso de 10 ms (teste de tempo): test_tempo_mutante6_gil_4_threads_pulso_10ms
# 7. `CacheCancelado` escapando ou `cancelar` omitido em planta/corte/refino (ou gravando): test_mutante7_*
