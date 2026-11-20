# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T25b: chave rapida do cache pelo arquivo IFC salvo em disco.
Contrato: `CacheDesenho.chave(ifc, pedido, cancelar=None, *, arquivo=None) -> str`.
- Modelo igual ao arquivo salvo (`revisao == revisao_salva`, `caminho_ifc` resolvido;
  mesma regra de `gerente._resolver_ifc_aberto`): sha256 com prefixo de modo ("arquivo")
  sobre versao, tamanho, `st_mtime_ns`, caminho resolvido normalizado e pedido (elementos,
  vista, opcoes, contexto; sem `threads`) SEM tocar no grafo IFC.
- Modelo editado nao salvo (`revisao != revisao_salva`), `revisao_salva` None, sem caminho
  ou arquivo inexistente: cai para o grafo (T25), sem excecao.
- Chamadores `planta.py`, `corte.py`, `refino.py` e `gerente.py` repassam `arquivo` so quando salvo.
"""
from __future__ import annotations

import inspect, json, os, shutil, subprocess, sys, threading, time
from pathlib import Path

import pytest
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from s06_t15i_aux import corte, local

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app import vistas_ifc  # noqa: E402
from openbim_app.desenho import cache as M, gerente as G, refino  # noqa: E402

RAIZ_APP = Path(__file__).resolve().parent.parent / "app"


def _ifc_api():
    exigir()
    import ifcopenshell, ifcopenshell.api
    return ifcopenshell, ifcopenshell.api


def _eh_sha256_hex(v: str) -> bool:
    return isinstance(v, str) and len(v) == 64 and all(ch in "0123456789abcdef" for ch in v)


def _criar_ifc_sintetico(caminho: Path, n_paredes: int = 4, props: int = 2, *, com_vistas: bool = False):
    """Cria IFC4 sintetico via ifcopenshell.api e grava em `caminho`."""
    _ifc, api = _ifc_api()
    f = api.run("project.create_file", version="IFC4")
    proj = api.run("root.create_entity", f, ifc_class="IfcProject", name="Projeto_T25b")
    api.run("unit.assign_unit", f)
    ctx = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno_T25b")
    bld = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Predio_T25b")
    pav = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pav_T25b")
    pav.Elevation = 0.0
    for pai, filho in ((proj, site), (site, bld), (bld, pav)):
        api.run("aggregate.assign_object", f, relating_object=pai, products=[filho])
    paredes = []
    for i in range(n_paredes):
        w = api.run("root.create_entity", f, ifc_class="IfcWall", name=f"PAREDE_T25B_{i:04d}")
        api.run("spatial.assign_container", f, relating_structure=pav, products=[w])
        rep = api.run("geometry.add_wall_representation", f, context=body, length=2.0 + i * 0.1, height=3.0, thickness=0.2)
        api.run("geometry.assign_representation", f, product=w, representation=rep)
        if props > 0:
            ps = api.run("pset.add_pset", f, product=w, name="Pset_WallCommon")
            api.run("pset.edit_pset", f, pset=ps, properties={f"P_{j}": f"V_{i}_{j}" for j in range(props)})
        paredes.append(w)
    gid_planta = gid_corte = None
    if com_vistas:
        gid_planta = vistas_ifc.criar_vista(f, "Planta_T25b", "PLANTA", escala="1:100", origem=(0.0, 0.0, 0.0), tamanho=(10.0, 10.0, 3.0))
        api.run("spatial.assign_container", f, relating_structure=pav, products=[f.by_guid(gid_planta)])
        gid_corte = vistas_ifc.criar_vista(f, "Corte_T25b", "CORTE", escala="1:100", origem=(-1.0, -1.0, -0.5), tamanho=(10.0, 6.0, 6.0))
        eixo = f.by_guid(gid_corte).ObjectPlacement.RelativePlacement
        eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
        eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        f.by_guid(gid_corte).Representation.Representations[0].Items[0].TreeRootExpression.Position.Location.Coordinates = (0.0, 0.0, -6.0)
    f.write(str(caminho))
    vista = {"tipo": "PLANTA", "altura_corte_m": 1.2, "pavimento": pav.GlobalId, "escala": 1.0}
    if gid_planta is not None:
        vista["guid"] = gid_planta
    ped = {
        "protocolo": 1, "op": "desenho", "elementos": [[w.id(), w.GlobalId] for w in paredes], "vista": vista,
        "moveis_como_caixa": False, "caixas_coords": {paredes[0].id(): [0.0, 0.0, 0.0, 2.0, 0.2, 3.0]}, "contexto": {"unidades": "METRE"},
    }
    return f, ped, {"pavimento": pav, "paredes": paredes, "gid_planta": gid_planta, "gid_corte": gid_corte}


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


@pytest.fixture(scope="module")
def ifc_grande(tmp_path_factory):
    """IFC sintetico grande (500 paredes x 20 props) gerado 1x por modulo em tmp_path."""
    arq = tmp_path_factory.mktemp("t25b_grande") / "grande.ifc"
    f, ped, _meta = _criar_ifc_sintetico(arq, n_paredes=500, props=20)
    return arq, f, ped


class _IfcEspiao:
    def __init__(self, ifc): self._ifc, self.chamadas = ifc, 0
    def by_guid(self, g: str): self.chamadas += 1; return self._ifc.by_guid(g)
    def by_id(self, i: int): self.chamadas += 1; return self._ifc.by_id(i)
    def by_type(self, t: str): self.chamadas += 1; return self._ifc.by_type(t)


class _CacheEspiao(M.CacheDesenho):
    def __init__(self, pasta: Path):
        super().__init__(pasta)
        self.arquivos, self.chaves, self.pedidos = [], [], []

    def chave(self, ifc, pedido: dict, cancelar: threading.Event | None = None, *, arquivo=None) -> str:
        self.arquivos.append(arquivo)
        self.pedidos.append(dict(pedido))
        ch = super().chave(ifc, pedido, cancelar=cancelar, arquivo=arquivo)
        self.chaves.append(ch)
        return ch


def _espiar_grafo(monkeypatch) -> dict[str, int]:
    cont, ser_real, elem_real = {"ser": 0, "elem": 0}, M._serializar, M._assinatura_elemento
    monkeypatch.setattr(M, "_serializar", lambda *a, **kw: (cont.__setitem__("ser", cont["ser"] + 1), ser_real(*a, **kw))[1])
    monkeypatch.setattr(M, "_assinatura_elemento", lambda *a, **kw: (cont.__setitem__("elem", cont["elem"] + 1), elem_real(*a, **kw))[1])
    return cont


def _pedir_gerente(app, g: G.GerenteDesenho, tipo: str, ifc, gid: str, **kw):
    fim, loop = [], QEventLoop()
    _ok = lambda ch, dados: (fim.append(("pronto", dados)), loop.quit())
    _err = lambda ch, msg: (fim.append(("falhou", msg)), loop.quit())
    g.pronto.connect(_ok)
    g.falhou.connect(_err)
    QTimer.singleShot(10_000, loop.quit)
    try:
        g.pedir(tipo, ifc, gid, **kw)
        loop.exec()
    finally:
        g.pronto.disconnect(_ok)
        g.falhou.disconnect(_err)
    assert fim and fim[0][0] == "pronto", f"gerente nao concluiu com pronto: {fim!r}"
    return fim[0][1]


def test_contrato_assinatura_arquivo_e_cancelar(tmp_path):
    """Assinatura `chave(ifc, pedido, cancelar=None, *, arquivo=None)` e cancelamento ativo."""
    sig = inspect.signature(M.CacheDesenho.chave)
    assert "arquivo" in sig.parameters
    param = sig.parameters["arquivo"]
    assert param.kind == inspect.Parameter.KEYWORD_ONLY and param.default is None
    arq = tmp_path / "contrato.ifc"
    f, ped, _ = _criar_ifc_sintetico(arq, n_paredes=2, props=1)
    ev = threading.Event()
    ev.set()
    with pytest.raises(M.CacheCancelado):
        M.CacheDesenho(tmp_path / "cache").chave(f, ped, cancelar=ev, arquivo=arq.resolve())


def test_mutante1_salvo_mesma_chave_3_chamadas_2_processos_sem_grafo(tmp_path, monkeypatch):
    """Mutante 1: arquivo igual = mesma chave em 3 chamadas e 2 processos, zero serializacao do grafo."""
    arq = tmp_path / "salvo.ifc"
    f, ped, _ = _criar_ifc_sintetico(arq, n_paredes=4, props=2, com_vistas=True)
    cont, ifc_esp, c = _espiar_grafo(monkeypatch), _IfcEspiao(f), M.CacheDesenho(tmp_path / "cache")
    chaves = [c.chave(ifc_esp, ped, arquivo=arq.resolve()) for _ in range(3)]
    assert all(_eh_sha256_hex(k) for k in chaves) and len(set(chaves)) == 1
    assert cont["ser"] == 0 and cont["elem"] == 0 and ifc_esp.chamadas == 0

    script = (
        "import json, sys; from pathlib import Path; import ifcopenshell; "
        "from openbim_app.desenho.cache import CacheDesenho; p = Path(sys.argv[1]).resolve(); "
        "print(CacheDesenho('/nao/usado').chave(ifcopenshell.open(str(p)), json.loads(sys.argv[2]), arquivo=p))"
    )
    ch_proc = []
    for idx, seed in enumerate(("1", "99999")):
        ks, vks = list(ped.keys()), list(ped["vista"].keys())
        if idx == 1:
            ks.reverse(), vks.reverse()
        ped_rot = {k: ({vk: ped["vista"][vk] for vk in vks} if k == "vista" else ped[k]) for k in ks}
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(RAIZ_APP)}
        proc = subprocess.run([sys.executable, "-c", script, str(arq), json.dumps(ped_rot)], capture_output=True, text=True, check=True, env=env, timeout=30)
        ch_proc.append(proc.stdout.strip())
    assert ch_proc == [chaves[0], chaves[0]]


def test_mutante1_chamadores_repassam_arquivo_quando_salvo(app, tmp_path, monkeypatch):
    """Mutante 1 (chamadores): gerente, planta, corte e refino usam modo arquivo quando salvo."""
    arq = tmp_path / "chamadores.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    w0, cont = meta["paredes"][0], _espiar_grafo(monkeypatch)

    esp_p, chamadas = _CacheEspiao(tmp_path / "cp"), []
    exec_p = lambda q: (chamadas.append(q), {"ok": True, "svg": "<svg><path d='M0 0L1 0'/></svg>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []})[1]
    g = G.GerenteDesenho(cache=esp_p, filho_persistente=False)
    try:
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=2, revisao_salva=2, executor=exec_p)
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=2, revisao_salva=2, executor=exec_p)
    finally:
        g.fechar()
    assert len(chamadas) == 1 and len(esp_p.arquivos) == 2
    assert all(a is not None and Path(a).resolve() == arq.resolve() for a in esp_p.arquivos) and cont["ser"] == 0 and cont["elem"] == 0

    esp_c = _CacheEspiao(tmp_path / "cc")
    exec_c = lambda q: local.executar(q) if q.get("op") != "desenho" else {"ok": True, "svg": "<svg/>", "n_paths": 1, "tempos": {}, "caixas": []}
    corte.gerar_corte(f, meta["gid_corte"], caminho_ifc=arq, cache=esp_c, executor=exec_c)
    assert len(esp_c.arquivos) == 1 and esp_c.arquivos[0] is not None and Path(esp_c.arquivos[0]).resolve() == arq.resolve()
    assert cont["ser"] == 0 and cont["elem"] == 0

    esp_r = _CacheEspiao(tmp_path / "cr")
    svg_sil = f'<svg xmlns:ifc="x"><g ifc:guid="{w0.GlobalId}" data-silhueta="1"><path d="M 0,0 L 1,0 Z"/></g></svg>'
    exec_pes = lambda _q: {"ok": True, "svg": svg_sil, "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": [{"id": w0.id(), "guid": w0.GlobalId, "faces": 120}]}
    monkeypatch.setattr(refino, "_refinar_uma", lambda *a, **kw: {"ok": True, "grupo": f'<g ifc:guid="{w0.GlobalId}"><path d="M 0,0 L 2,0 Z"/></g>', "motor": "visibilidade"})
    g2 = G.GerenteDesenho(cache=esp_r, filho_persistente=False)
    try:
        _pedir_gerente(app, g2, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=4, revisao_salva=4, executor=exec_pes)
    finally:
        g2.fechar()
    assert len(esp_r.arquivos) == 2 and all(a is not None and Path(a).resolve() == arq.resolve() for a in esp_r.arquivos)
    assert cont["ser"] == 0 and cont["elem"] == 0


def test_mutante2_arquivo_mudou_tamanho_ou_mtime_muda_chave(tmp_path):
    """Mutante 2: mudanca de tamanho (mesmo mtime) ou de mtime (mesmo tamanho) altera a chave."""
    arq = tmp_path / "muda.ifc"
    f, ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1)
    c, bytes_orig, st0 = M.CacheDesenho(tmp_path / "cache"), arq.read_bytes(), arq.stat()
    k0 = c.chave(f, ped, arquivo=arq.resolve())

    arq.write_bytes(bytes_orig + b"\n/* pad */\n")
    os.utime(arq, ns=(st0.st_atime_ns, st0.st_mtime_ns))
    assert arq.stat().st_size != st0.st_size and arq.stat().st_mtime_ns == st0.st_mtime_ns
    assert c.chave(f, ped, arquivo=arq.resolve()) != k0

    arq.write_bytes(bytes_orig)
    os.utime(arq, ns=(st0.st_atime_ns, st0.st_mtime_ns + 1_000_000_000))
    assert arq.stat().st_size == st0.st_size and c.chave(f, ped, arquivo=arq.resolve()) != k0

    os.utime(arq, ns=(st0.st_atime_ns, st0.st_mtime_ns + 123_456))
    if arq.stat().st_mtime_ns != st0.st_mtime_ns:
        assert c.chave(f, ped, arquivo=arq.resolve()) != k0

    meta["paredes"][0].Name = "PAREDE_REGRAVADA"
    f.write(str(arq))
    assert c.chave(f, ped, arquivo=arq.resolve()) != k0


def test_mutante3_modelo_editado_nao_salvo_usa_grafo_e_muda_chave(app, tmp_path, monkeypatch):
    """Mutante 3: modelo editado e nao salvo usa grafo; editar elemento muda chave com arquivo igual."""
    arq = tmp_path / "editado.ifc"
    f, ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    w0, st_disco, cont, c = meta["paredes"][0], arq.stat(), _espiar_grafo(monkeypatch), M.CacheDesenho(tmp_path / "cd")
    k_g0 = c.chave(f, ped, arquivo=None)
    assert cont["ser"] > 0 and cont["elem"] > 0
    w0.Name = "PAREDE_MEMORIA_1"
    assert c.chave(f, ped, arquivo=None) != k_g0
    w0.Name = "PAREDE_T25B_0000"
    assert c.chave(f, ped, arquivo=None) == k_g0

    esp, chamadas = _CacheEspiao(tmp_path / "cg"), []
    exec_p = lambda q: (chamadas.append(q), {"ok": True, "svg": f"<svg n='{len(chamadas)}'/>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []})[1]
    g = G.GerenteDesenho(cache=esp, filho_persistente=False)
    try:
        cont["ser"] = cont["elem"] = 0
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=1, revisao_salva=1, executor=exec_p)
        assert cont["ser"] == 0 and cont["elem"] == 0 and esp.arquivos[-1] is not None
        w0.Name = "EDITADA_SEM_SALVAR_1"
        cont["ser"] = cont["elem"] = 0
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=2, revisao_salva=1, executor=exec_p)
        assert cont["ser"] > 0 and cont["elem"] > 0 and esp.arquivos[-1] is None and len(chamadas) == 2 and esp.chaves[-1] != esp.chaves[-2]
        w0.Name = "EDITADA_SEM_SALVAR_2"
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=3, revisao_salva=1, executor=exec_p)
        assert len(chamadas) == 3 and esp.chaves[-1] != esp.chaves[-2]
    finally:
        g.fechar()
    assert (arq.stat().st_size, arq.stat().st_mtime_ns) == (st_disco.st_size, st_disco.st_mtime_ns)


@pytest.mark.parametrize("rev,rev_salva,com_caminho", [(1, None, True), (None, None, True), (None, 1, True), (2, 1, True), (1, 2, True), (1, 1, False)])
def test_mutante4_revisao_salva_none_ou_diferente_nunca_usa_arquivo(app, tmp_path, monkeypatch, rev, rev_salva, com_caminho):
    """Mutante 4: revisao_salva None/diferente ou sem caminho nunca usa o modo arquivo."""
    arq = tmp_path / "gate.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    caminho = arq if com_caminho else None
    assert G._resolver_ifc_aberto(caminho, rev, rev_salva) is None
    cont, esp = _espiar_grafo(monkeypatch), _CacheEspiao(tmp_path / "cg")
    exec_p = lambda _q: {"ok": True, "svg": "<svg/>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []}
    g = G.GerenteDesenho(cache=esp, filho_persistente=False)
    try:
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=caminho, revisao=rev, revisao_salva=rev_salva, executor=exec_p)
    finally:
        g.fechar()
    assert esp.arquivos == [None] and cont["ser"] > 0 and cont["elem"] > 0
    assert esp.chaves[0] != M.CacheDesenho(tmp_path / "cmp").chave(f, esp.pedidos[0], arquivo=arq.resolve())


def test_mutante5_pedido_diferente_com_arquivo_igual_muda_chave(tmp_path, monkeypatch):
    """Mutante 5: elementos, vista, opcoes, contexto ou versao diferentes mudam chave (sem tocar grafo)."""
    arq = tmp_path / "pedido.ifc"
    f, ped, meta = _criar_ifc_sintetico(arq, n_paredes=4, props=1, com_vistas=True)
    cont, c = _espiar_grafo(monkeypatch), M.CacheDesenho(tmp_path / "cache")
    k0 = c.chave(f, ped, arquivo=arq.resolve())
    assert c.chave(f, {**ped, "threads": 1}, arquivo=arq.resolve()) == k0 == c.chave(f, {**ped, "threads": 8}, arquivo=arq.resolve())
    variantes = [
        {**ped, "elementos": ped["elementos"][:-1]},
        {**ped, "elementos": list(reversed(ped["elementos"]))},
        {**ped, "elementos": [[999999, meta["paredes"][0].GlobalId], *ped["elementos"][1:]]},
        {**ped, "vista": {**ped["vista"], "altura_corte_m": 1.8}},
        {**ped, "vista": {**ped["vista"], "tipo": "CORTE"}},
        {**ped, "vista": {**ped["vista"], "guid": "OUTRA_VISTA_GUID"}},
        {**ped, "vista": {**ped["vista"], "pavimento": "OUTRO_PAV_GUID"}},
        {**ped, "vista": {**ped["vista"], "escala": 0.001}},
        {**ped, "moveis_como_caixa": True}, {**ped, "pesados": "silhueta"},
        {**ped, "caixas_coords": {meta["paredes"][0].id(): [1.0, 0.0, 0.0, 2.0, 0.2, 3.0]}},
        {**ped, "contexto": {"unidades": "MILLI"}},
    ]
    for v in variantes:
        assert c.chave(f, v, arquivo=arq.resolve()) != k0
    monkeypatch.setattr(M, "VERSAO_MODULO", "t25b-outra-versao")
    assert c.chave(f, ped, arquivo=arq.resolve()) != k0 and cont["ser"] == 0 and cont["elem"] == 0


def test_mutante6_relativo_absoluto_link_e_inexistente(tmp_path, monkeypatch):
    """Mutante 6: relativo/absoluto/link = mesma chave; outro caminho = diferente; inexistente cai para grafo."""
    arq = tmp_path / "orig.ifc"
    f, ped, _ = _criar_ifc_sintetico(arq, n_paredes=2, props=1)
    sub, link = tmp_path / "sub", tmp_path / "atalho.ifc"
    sub.mkdir()
    link.symlink_to(arq)
    cont, c = _espiar_grafo(monkeypatch), M.CacheDesenho(tmp_path / "cache")
    k_abs = c.chave(f, ped, arquivo=arq.resolve())
    k_alias, k_link = c.chave(f, ped, arquivo=sub / ".." / arq.name), c.chave(f, ped, arquivo=link)
    monkeypatch.chdir(sub)
    k_rel = c.chave(f, ped, arquivo=Path("..") / arq.name)
    assert k_abs == k_alias == k_link == k_rel and cont["ser"] == 0 and cont["elem"] == 0
    copia, st = tmp_path / "copia.ifc", arq.stat()
    shutil.copy2(arq, copia)
    os.utime(copia, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert c.chave(f, ped, arquivo=copia.resolve()) != k_abs
    k_ausente = c.chave(f, ped, arquivo=tmp_path / "nao_existe.ifc")
    assert cont["ser"] > 0 and cont["elem"] > 0 and k_ausente == c.chave(f, ped, arquivo=None)


def test_mutante7_chave_arquivo_nunca_igual_chave_grafo(tmp_path):
    """Mutante 7: prefixo de modo impede colisao entre cache por arquivo e cache por grafo."""
    arq = tmp_path / "modo.ifc"
    f, ped, _ = _criar_ifc_sintetico(arq, n_paredes=2, props=1)
    st, c = arq.stat(), M.CacheDesenho(tmp_path / "cache")
    ped_adv = {"elementos": [], "vista": {}, "modo": "arquivo", "arquivo": str(arq.resolve()), "tamanho": st.st_size, "mtime_ns": st.st_mtime_ns}
    for p in (ped, {"elementos": [], "vista": {}}, {}, ped_adv):
        k_arq, k_grf = c.chave(f, p, arquivo=arq.resolve()), c.chave(f, p, arquivo=None)
        assert _eh_sha256_hex(k_arq) and _eh_sha256_hex(k_grf) and k_arq != k_grf
    k_a, k_g = c.chave(f, ped, arquivo=arq.resolve()), c.chave(f, ped, arquivo=None)
    assert c.guardar(k_a, {"svg": "<svg>A</svg>"}) and c.guardar(k_g, {"svg": "<svg>G</svg>"})
    assert c.obter(k_a)["svg"] == "<svg>A</svg>" and c.obter(k_g)["svg"] == "<svg>G</svg>"


def test_tempo_mutante8_gil_4_threads_pulso_10ms(ifc_grande, tmp_path, monkeypatch):
    """[TESTE DE TEMPO] Mutante 8: 4 threads em chave por arquivo nao travam pulso 10 ms > 100 ms (20 ms x 5)."""
    arq, f, ped = ifc_grande
    cont = _espiar_grafo(monkeypatch)
    c, parar, gaps, erros, chaves, fim = M.CacheDesenho(tmp_path / "cache"), threading.Event(), [], [], [], time.monotonic() + 0.15

    def pulso():
        ant = time.perf_counter()
        while not parar.is_set():
            time.sleep(0.010)
            agora = time.perf_counter()
            gaps.append(agora - ant)
            ant = agora

    def trab():
        try:
            while True:
                chaves.append(c.chave(f, ped, arquivo=arq.resolve()))
                if time.monotonic() >= fim:
                    break
        except BaseException as exc:  # pragma: no cover
            erros.append(exc)

    tp, ts = threading.Thread(target=pulso), [threading.Thread(target=trab) for _ in range(4)]
    tp.start()
    for t in ts: t.start()
    for t in ts: t.join(timeout=30)
    parar.set()
    tp.join(timeout=5)
    assert not erros and len(chaves) >= 4 and len(set(chaves)) == 1 and len(gaps) >= 5
    assert cont["ser"] == 0 and cont["elem"] == 0
    maior_ms = max(gaps) * 1000.0
    assert maior_ms <= 100.0, f"GIL travou pulso de 10 ms por {maior_ms:.1f} ms (limite 100 ms = 20 ms x 5)"


# Mutantes derrubados:
# 1. Serializar grafo com modelo salvo, chave divergente em 3 chamadas/2 processos, ou chamadores sem repassar arquivo: test_mutante1_*
# 2. Ignorar tamanho ou st_mtime_ns (incluindo sub-segundo) quando o arquivo muda no disco: test_mutante2_arquivo_mudou_tamanho_ou_mtime_muda_chave
# 3. Servir chave do arquivo para modelo editado nao salvo ou ignorar edicao em memoria: test_mutante3_modelo_editado_nao_salvo_usa_grafo_e_muda_chave
# 4. Abrir modo arquivo com revisao_salva None, revisao None, revisao != revisao_salva ou sem caminho: test_mutante4_revisao_salva_none_ou_diferente_nunca_usa_arquivo
# 5. Ignorar elementos, vista, opcoes, contexto ou versao no modo arquivo (ou incluir threads): test_mutante5_pedido_diferente_com_arquivo_igual_muda_chave
# 6. Nao normalizar relativo/absoluto/link, omitir caminho resolvido, ou falhar em arquivo inexistente: test_mutante6_relativo_absoluto_link_e_inexistente
# 7. Omitir prefixo de modo permitindo colisao entre chave de arquivo e chave de grafo: test_mutante7_chave_arquivo_nunca_igual_chave_grafo
# 8. Travar o GIL > 100 ms (20 ms x 5 no CI) com 4 threads e IFC sintetico grande: test_tempo_mutante8_gil_4_threads_pulso_10ms
