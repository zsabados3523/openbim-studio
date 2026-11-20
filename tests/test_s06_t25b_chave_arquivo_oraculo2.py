# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T25b (rodada 2): invariantes da REVISAO.md (itens 1 a 4 e 6).
- (1) Retry Divergente em planta nao grava desenho em memoria sob chave do arquivo.
- (2) Refino (direto e via gerente) nunca grava peca do IFC em memoria sob chave do arquivo alterado/divergente.
- (3) TOCTOU: antes de cache.guardar, rechecar assinatura do arquivo (stat) igual a da chave; se mudou, nao guardar.
- (4) arquivo_resolvido/_resolver_arquivo (e _resolver_ifc_aberto) com symlink circular, byte nulo ou tipo invalido: cai no grafo sem excecao.
- (6) GerenteDesenho.pedir passa caminho ja resolvido em opcoes["caminho_ifc"].
"""
from __future__ import annotations

import os, threading
from pathlib import Path

import pytest
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from s06_t15i_aux import auxiliar, corte, local, planta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app import vistas_ifc  # noqa: E402
from openbim_app.desenho import cache as M, gerente as G, refino  # noqa: E402


def _ifc_api():
    exigir()
    import ifcopenshell, ifcopenshell.api
    return ifcopenshell, ifcopenshell.api


def _criar_ifc_sintetico(caminho: Path, n_paredes: int = 2, props: int = 1, *, com_vistas: bool = True):
    """Cria IFC4 sintetico via ifcopenshell.api e grava em `caminho`."""
    _ifc, api = _ifc_api()
    f = api.run("project.create_file", version="IFC4")
    proj = api.run("root.create_entity", f, ifc_class="IfcProject", name="Projeto_T25b_R2")
    api.run("unit.assign_unit", f)
    ctx = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Terreno_T25b_R2")
    bld = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Predio_T25b_R2")
    pav = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pav_T25b_R2")
    pav.Elevation = 0.0
    for pai, filho in ((proj, site), (site, bld), (bld, pav)):
        api.run("aggregate.assign_object", f, relating_object=pai, products=[filho])
    paredes = []
    for i in range(n_paredes):
        w = api.run("root.create_entity", f, ifc_class="IfcWall", name=f"PAREDE_R2_{i:04d}")
        api.run("spatial.assign_container", f, relating_structure=pav, products=[w])
        rep = api.run("geometry.add_wall_representation", f, context=body, length=2.0 + i * 0.2, height=3.0, thickness=0.2)
        api.run("geometry.assign_representation", f, product=w, representation=rep)
        if props > 0:
            ps = api.run("pset.add_pset", f, product=w, name="Pset_WallCommon")
            api.run("pset.edit_pset", f, pset=ps, properties={f"P_{j}": f"V_{i}_{j}" for j in range(props)})
        paredes.append(w)
    gid_planta = gid_corte = None
    if com_vistas:
        gid_planta = vistas_ifc.criar_vista(f, "Planta_R2", "PLANTA", escala="1:100", origem=(0.0, 0.0, 0.0), tamanho=(10.0, 10.0, 3.0))
        api.run("spatial.assign_container", f, relating_structure=pav, products=[f.by_guid(gid_planta)])
        gid_corte = vistas_ifc.criar_vista(f, "Corte_R2", "CORTE", escala="1:100", origem=(-1.0, -1.0, -0.5), tamanho=(10.0, 6.0, 6.0))
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


class _CacheEspiao(M.CacheDesenho):
    def __init__(self, pasta: Path, *, ao_obter=None):
        super().__init__(pasta)
        self.arquivos, self.chaves, self.pedidos = [], [], []
        self.guardadas: dict[str, dict] = {}
        self.guardou = 0
        self._ao_obter = ao_obter

    def chave(self, ifc, pedido: dict, cancelar: threading.Event | None = None, *, arquivo=None) -> str:
        self.arquivos.append(arquivo)
        self.pedidos.append(dict(pedido))
        ch = super().chave(ifc, pedido, cancelar=cancelar, arquivo=arquivo)
        self.chaves.append(ch)
        return ch

    def obter(self, chave: str) -> dict | None:
        res = super().obter(chave)
        if self._ao_obter is not None:
            self._ao_obter(chave, res)
        return res

    def guardar(self, chave: str, dados: dict) -> bool:
        self.guardou += 1
        self.guardadas[chave] = dict(dados)
        return super().guardar(chave, dados)


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


def _mutar_ifc(arq: Path, bytes_orig: bytes, st0, marca: bytes = b"\n/* V2 */\n"):
    arq.write_bytes(bytes_orig + marca)
    os.utime(arq, ns=(st0.st_atime_ns, st0.st_mtime_ns + 2_000_000_000))
    st1 = arq.stat()
    assert st1.st_size != st0.st_size and st1.st_mtime_ns != st0.st_mtime_ns
    return st1


def _instalar_refino_falso(monkeypatch):
    """Intercepta auxiliar.executar para op='peca_visivel' sem subprocesso, distinguindo V1 (memoria) de V2 (disco)."""
    exec_real = auxiliar.executar

    def _fake_executar(preparado, *args, executor=None, **kw):
        q = preparado.pedido
        if executor is None and q.get("op") == "peca_visivel":
            arq_q = Path(q["arquivo"])
            if "assinatura" in q:
                st = os.stat(arq_q)
                if [int(st.st_size), int(st.st_mtime_ns)] != list(q["assinatura"]):
                    raise auxiliar.Divergente("assinatura divergiu no refino")
            eh_v2 = b"/* V2 */" in arq_q.read_bytes()
            gid = q["elementos"][0][1]
            tag = "V2_NOVA" if eh_v2 else "V1_VELHA"
            return {"ok": True, "grupo": f'<g ifc:guid="{gid}" data-v="{tag}"><path d="M0 0L2 0Z"/></g>', "tempos": {}}
        return exec_real(preparado, *args, executor=executor, **kw)

    monkeypatch.setattr(auxiliar, "executar", _fake_executar)


def test_item1_planta_retry_divergente_nao_grava_sob_chave_arquivo(tmp_path):
    """(1) Retry Divergente em planta nao grava desenho em memoria sob chave do arquivo."""
    arq = tmp_path / "planta_div.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    esp, ch1, ch2 = _CacheEspiao(tmp_path / "cp"), [], []

    def exec_div(q):
        ch1.append(dict(q))
        if "assinatura" in q:
            return {"ok": False, "erro": {"tipo": "Divergente", "mensagem": "arquivo mudou", "rastro": ""}}
        return {"ok": True, "svg": "<svg>MEMORIA_EDITADA</svg>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []}

    r1 = planta.gerar_planta(f, meta["gid_planta"], caminho_ifc=arq, cache=esp, executor=exec_div)
    assert r1.svg == "<svg>MEMORIA_EDITADA</svg>" and len(ch1) == 2
    assert "assinatura" in ch1[0] and "assinatura" not in ch1[1]

    k_arq = M.CacheDesenho(tmp_path / "cmp").chave(f, r1.pedido, arquivo=arq.resolve())
    assert k_arq not in esp.guardadas and esp.obter(k_arq) is None

    def exec_arq(q):
        ch2.append(dict(q))
        return {"ok": True, "svg": "<svg>ARQUIVO_SALVO</svg>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []}

    r2 = planta.gerar_planta(f, meta["gid_planta"], caminho_ifc=arq, cache=esp, executor=exec_arq)
    assert len(ch2) == 1 and r2.svg == "<svg>ARQUIVO_SALVO</svg>"


def test_item2_refino_arquivo_mudou_no_loop_nao_envenena_chave_v2(tmp_path):
    """(2) Refino: arquivo muda durante P1; P2 gerada do IFC em memoria nunca grava sob chave V2."""
    arq = tmp_path / "refino_loop.ifc"
    f, ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    w0, w1 = meta["paredes"][0], meta["paredes"][1]
    bytes_v1, st1 = arq.read_bytes(), arq.stat()
    svg_sil = (
        f'<svg xmlns:ifc="x">'
        f'<g ifc:guid="{w0.GlobalId}" data-silhueta="1"><path d="M0 0L1 0Z"/></g>'
        f'<g ifc:guid="{w1.GlobalId}" data-silhueta="1"><path d="M0 0L1 0Z"/></g>'
        f'</svg>'
    )
    res = {"svg": svg_sil, "pesados": [{"id": w0.id(), "guid": w0.GlobalId, "faces": 100}, {"id": w1.id(), "guid": w1.GlobalId, "faces": 200}]}
    esp = _CacheEspiao(tmp_path / "cr")

    def exec_v1(q):
        gid = q["elementos"][0][1]
        if gid == w0.GlobalId:
            _mutar_ifc(arq, bytes_v1, st1)
            return {"ok": True, "grupo": f'<g ifc:guid="{gid}" data-v="P1"><path d="M0 0L1 0Z"/></g>', "tempos": {}}
        eh_v2 = b"/* V2 */" in Path(q["arquivo"]).read_bytes()
        tag = "V2_NOVA" if eh_v2 else "V1_VELHA"
        return {"ok": True, "grupo": f'<g ifc:guid="{gid}" data-v="{tag}"><path d="M0 0L2 0Z"/></g>', "tempos": {}}

    refino.refinar_pesados(f, ped, res, executor=exec_v1, cache=esp, caminho_ifc=arq)

    exec_v2 = lambda q: {"ok": True, "grupo": f'<g ifc:guid="{q["elementos"][0][1]}" data-v="V2_NOVA"><path d="M0 0L3 0Z"/></g>', "tempos": {}}
    out2 = refino.refinar_pesados(f, ped, res, executor=exec_v2, cache=esp, caminho_ifc=arq)
    assert 'data-v="V1_VELHA"' not in out2["svg"]
    assert f'<g ifc:guid="{w1.GlobalId}" data-v="V2_NOVA">' in out2["svg"]


def test_item2_gerente_planta_divergente_refino_nao_grava_sob_chave_arquivo(app, tmp_path, monkeypatch):
    """(2) Gerente: planta cai em retry Divergente; refino nao pode gravar peca em memoria sob chave do arquivo."""
    arq = tmp_path / "gerente_div.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    w0, bytes_v1, st1 = meta["paredes"][0], arq.read_bytes(), arq.stat()
    svg_sil = f'<svg xmlns:ifc="x"><g ifc:guid="{w0.GlobalId}" data-silhueta="1"><path d="M0 0L1 0Z"/></g></svg>'
    _instalar_refino_falso(monkeypatch)
    esp = _CacheEspiao(tmp_path / "cg")

    def exec_planta(q):
        if "assinatura" in q:
            _mutar_ifc(arq, bytes_v1, st1)
            return {"ok": False, "erro": {"tipo": "Divergente", "mensagem": "divergiu", "rastro": ""}}
        return {"ok": True, "svg": svg_sil, "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": [{"id": w0.id(), "guid": w0.GlobalId, "faces": 120}]}

    g = G.GerenteDesenho(cache=esp, filho_persistente=False)
    try:
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=2, revisao_salva=2, executor=exec_planta)
    finally:
        g.fechar()

    ped_planta = esp.pedidos[0]
    res_v2 = {"svg": svg_sil, "pesados": [{"id": w0.id(), "guid": w0.GlobalId, "faces": 120}]}
    exec_v2 = lambda q: {"ok": True, "grupo": f'<g ifc:guid="{w0.GlobalId}" data-v="V2_NOVA"><path d="M0 0L3 0Z"/></g>', "tempos": {}}
    out2 = refino.refinar_pesados(f, ped_planta, res_v2, executor=exec_v2, cache=esp, caminho_ifc=arq)
    assert 'data-v="V1_VELHA"' not in out2["svg"] and 'data-v="V2_NOVA"' in out2["svg"]


def test_item2_gerente_invalidar_em_voo_refino_nao_grava_sob_chave_v2(app, tmp_path, monkeypatch):
    """(2) Gerente: invalidar() + mudanca no disco durante planta impedem refino de gravar V1 sob chave V2."""
    arq = tmp_path / "gerente_inv.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    w0, bytes_v1, st1 = meta["paredes"][0], arq.read_bytes(), arq.stat()
    svg_sil = f'<svg xmlns:ifc="x"><g ifc:guid="{w0.GlobalId}" data-silhueta="1"><path d="M0 0L1 0Z"/></g></svg>'
    _instalar_refino_falso(monkeypatch)
    esp = _CacheEspiao(tmp_path / "ci")
    g = G.GerenteDesenho(cache=esp, filho_persistente=False)

    def exec_planta(_q):
        _mutar_ifc(arq, bytes_v1, st1)
        g.invalidar()
        return {"ok": True, "svg": svg_sil, "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": [{"id": w0.id(), "guid": w0.GlobalId, "faces": 120}]}

    try:
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=2, revisao_salva=2, executor=exec_planta)
    finally:
        g.fechar()

    ped_planta = esp.pedidos[0]
    res_v2 = {"svg": svg_sil, "pesados": [{"id": w0.id(), "guid": w0.GlobalId, "faces": 120}]}
    exec_v2 = lambda q: {"ok": True, "grupo": f'<g ifc:guid="{w0.GlobalId}" data-v="V2_NOVA"><path d="M0 0L3 0Z"/></g>', "tempos": {}}
    out2 = refino.refinar_pesados(f, ped_planta, res_v2, executor=exec_v2, cache=esp, caminho_ifc=arq)
    assert 'data-v="V1_VELHA"' not in out2["svg"] and 'data-v="V2_NOVA"' in out2["svg"]


def test_item3_toctou_planta_mutacao_entre_chave_e_preparar_nao_guarda(tmp_path):
    """(3) TOCTOU em planta: arquivo muda entre cache.chave (V1) e auxiliar.preparar (V2) -> nao grava sob chave V1."""
    arq = tmp_path / "toctou_p1.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    bytes_v1, st1, mutou = arq.read_bytes(), arq.stat(), [False]

    def _ao_obter(_ch, res):
        if res is None and not mutou[0]:
            mutou[0] = True
            _mutar_ifc(arq, bytes_v1, st1)

    esp = _CacheEspiao(tmp_path / "cp", ao_obter=_ao_obter)
    exec_v2 = lambda _q: {"ok": True, "svg": "<svg>DESENHO_V2</svg>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []}
    planta.gerar_planta(f, meta["gid_planta"], caminho_ifc=arq, cache=esp, executor=exec_v2)
    ch_v1 = esp.chaves[0]
    assert mutou[0] and ch_v1 not in esp.guardadas and esp.obter(ch_v1) is None


def test_item3_toctou_planta_mutacao_antes_de_guardar_nao_guarda(tmp_path):
    """(3) TOCTOU em planta: arquivo muda durante executor antes de cache.guardar -> recheca stat e nao guarda."""
    arq = tmp_path / "toctou_p2.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    bytes_v1, st1 = arq.read_bytes(), arq.stat()
    esp = _CacheEspiao(tmp_path / "cp")

    def exec_muta(_q):
        _mutar_ifc(arq, bytes_v1, st1)
        return {"ok": True, "svg": "<svg>DESENHO_CORRIDA</svg>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []}

    planta.gerar_planta(f, meta["gid_planta"], caminho_ifc=arq, cache=esp, executor=exec_muta)
    assert esp.guardou == 0 and esp.obter(esp.chaves[0]) is None


def test_item3_toctou_corte_mutacao_entre_chave_e_preparar_nao_guarda(tmp_path):
    """(3) TOCTOU em corte: arquivo muda entre cache.chave (V1) e auxiliar.preparar (V2) -> nao grava sob chave V1."""
    arq = tmp_path / "toctou_c1.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    bytes_v1, st1, mutou = arq.read_bytes(), arq.stat(), [False]

    def _ao_obter(_ch, res):
        if res is None and not mutou[0]:
            mutou[0] = True
            _mutar_ifc(arq, bytes_v1, st1)

    esp = _CacheEspiao(tmp_path / "cc", ao_obter=_ao_obter)
    exec_c = lambda q: local.executar(q) if q.get("op") != "desenho" else {"ok": True, "svg": "<svg>CORTE_V2</svg>", "n_paths": 1, "tempos": {}, "caixas": []}
    corte.gerar_corte(f, meta["gid_corte"], caminho_ifc=arq, cache=esp, executor=exec_c)
    ch_v1 = esp.chaves[0]
    assert mutou[0] and ch_v1 not in esp.guardadas and esp.obter(ch_v1) is None


def test_item3_toctou_corte_mutacao_antes_de_guardar_nao_guarda(tmp_path):
    """(3) TOCTOU em corte: arquivo muda durante executor antes de cache.guardar -> recheca stat e nao guarda."""
    arq = tmp_path / "toctou_c2.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    bytes_v1, st1 = arq.read_bytes(), arq.stat()
    esp = _CacheEspiao(tmp_path / "cc")

    def exec_c(q):
        if q.get("op") != "desenho":
            return local.executar(q)
        _mutar_ifc(arq, bytes_v1, st1)
        return {"ok": True, "svg": "<svg>CORTE_CORRIDA</svg>", "n_paths": 1, "tempos": {}, "caixas": []}

    corte.gerar_corte(f, meta["gid_corte"], caminho_ifc=arq, cache=esp, executor=exec_c)
    assert esp.guardou == 0 and esp.obter(esp.chaves[0]) is None


@pytest.mark.parametrize("caso", ["symlink_circular", "byte_nulo", "tipo_invalido"])
def test_item4_arquivo_invalido_cai_no_grafo_sem_excecao(tmp_path, monkeypatch, caso):
    """(4) Symlink circular, byte nulo e tipo invalido em arquivo_resolvido/_resolver_arquivo caem no grafo sem excecao."""
    arq = tmp_path / "valido.ifc"
    f, ped, _ = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=False)
    if caso == "symlink_circular":
        a, b = tmp_path / "loop_a.ifc", tmp_path / "loop_b.ifc"
        a.symlink_to(b)
        b.symlink_to(a)
        entrada = a
    elif caso == "byte_nulo":
        entrada = "foo\x00bar.ifc"
    else:
        entrada = 123

    c = M.CacheDesenho(tmp_path / "cache")
    k_grafo = c.chave(f, ped, arquivo=None)
    cont = _espiar_grafo(monkeypatch)

    assert M.arquivo_resolvido(entrada) is None
    assert M._resolver_arquivo(entrada) is None
    assert G._resolver_ifc_aberto(entrada, 1, 1) is None
    assert c.chave(f, ped, arquivo=entrada) == k_grafo
    assert cont["ser"] > 0 and cont["elem"] > 0


def test_item6_gerente_passa_caminho_ja_resolvido_imune_a_chdir(app, tmp_path, monkeypatch):
    """(6) GerenteDesenho.pedir grava caminho ja resolvido em opcoes['caminho_ifc'], imune a mudanca de CWD."""
    dir_a, dir_b = tmp_path / "dir_a", tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()
    arq = dir_a / "modelo.ifc"
    f, _ped, meta = _criar_ifc_sintetico(arq, n_paredes=2, props=1, com_vistas=True)
    link = dir_a / "atalho.ifc"
    link.symlink_to(arq)

    monkeypatch.chdir(dir_a)
    cont, esp = _espiar_grafo(monkeypatch), _CacheEspiao(tmp_path / "cg")
    opcoes_vistas, chamadas = {}, []

    def chave_estado(_tipo, _ifc, _guid, opcoes):
        opcoes_vistas.update(opcoes)
        os.chdir(dir_b)  # CWD muda antes da thread de fundo chamar gerar_planta
        return "chave-item6"

    exec_p = lambda q: (chamadas.append(dict(q)), {"ok": True, "svg": "<svg/>", "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": []})[1]
    g = G.GerenteDesenho(cache=esp, chave_estado=chave_estado, filho_persistente=False)
    try:
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=Path("atalho.ifc"), revisao=1, revisao_salva=1, executor=exec_p)
    finally:
        g.fechar()

    esperado = arq.resolve()
    assert "caminho_ifc" in opcoes_vistas
    assert Path(opcoes_vistas["caminho_ifc"]).is_absolute() and Path(opcoes_vistas["caminho_ifc"]) == esperado
    assert esp.arquivos == [esperado] and cont["ser"] == 0 and cont["elem"] == 0
    assert len(chamadas) == 1 and Path(chamadas[0]["arquivo"]) == esperado
