# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T25b (rodada 3): defeitos 1 a 3 da REVISAO2.md e desenho de leitura unica.
- Contrato: `CacheDesenho.chave(ifc, pedido, cancelar=None, *, arquivo=None, assinatura=None) -> str`
  usa `assinatura` sem chamar `os.stat`/`Path.stat`; sem `assinatura` = modo grafo. `assinatura_arquivo(caminho)`.
- (1) gerente->refino: mutacao entre pedir()/_motor_padrao e refinar_pesados nao grava V1 sob V2.
- (2a) arq None + arquivo V2 surgindo antes de preparar nao grava V2 sob chave de grafo.
- (2b) symlink redirecionado (a.ifc -> b.ifc, mesmo stat) nao grava b.ifc sob chave de a.ifc.
- (3) mutacao V1->V2 entre leitura da sig e cache.chave em refino/planta/corte nao serve V2 em V1.
- (Desenho) auxiliar.preparar recebe a mesma sig (nao re-stat), disparando Divergente se o disco mudou.
"""
from __future__ import annotations

import inspect, os, threading
from pathlib import Path

import pytest
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from s06_t15i_aux import auxiliar, corte, local, planta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app import vistas_ifc  # noqa: E402
from openbim_app.desenho import cache as M, gerente as G, refino  # noqa: E402


def _eh_sha256_hex(v: str) -> bool: return isinstance(v, str) and len(v) == 64 and all(ch in "0123456789abcdef" for ch in v)
def _ok_svg(svg: str, pesados=()): return {"ok": True, "svg": svg, "n_paths": 1, "tempos": {}, "caixas": [], "em_cache": [], "pesados": list(pesados)}
def _restaurar_ifc(arq: Path, conteudo: bytes, st_ref) -> None: arq.write_bytes(conteudo); os.utime(arq, ns=(st_ref.st_atime_ns, st_ref.st_mtime_ns))
def _gerar(modo: str, f, meta: dict, *, caminho_ifc, cache, executor):
    return (planta.gerar_planta(f, meta["gid_planta"], caminho_ifc=caminho_ifc, cache=cache, executor=executor) if modo == "planta"
            else corte.gerar_corte(f, meta["gid_corte"], caminho_ifc=caminho_ifc, cache=cache, executor=executor))


def _criar_ifc(caminho: Path, *, salvar: bool = True):
    exigir()
    import ifcopenshell.api as api
    f = api.run("project.create_file", version="IFC4")
    proj = api.run("root.create_entity", f, ifc_class="IfcProject", name="Proj_R3")
    api.run("unit.assign_unit", f)
    ctx = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site_R3")
    bld = api.run("root.create_entity", f, ifc_class="IfcBuilding", name="Bld_R3")
    pav = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Pav_R3")
    pav.Elevation = 0.0
    for pai, filho in ((proj, site), (site, bld), (bld, pav)):
        api.run("aggregate.assign_object", f, relating_object=pai, products=[filho])
    paredes = []
    for i in range(2):
        w = api.run("root.create_entity", f, ifc_class="IfcWall", name=f"PAREDE_R3_{i:04d}")
        api.run("spatial.assign_container", f, relating_structure=pav, products=[w])
        rep = api.run("geometry.add_wall_representation", f, context=body, length=2.0 + i * 0.2, height=3.0, thickness=0.2)
        api.run("geometry.assign_representation", f, product=w, representation=rep)
        ps = api.run("pset.add_pset", f, product=w, name="Pset_WallCommon")
        api.run("pset.edit_pset", f, pset=ps, properties={"P_0": f"V_{i}"})
        paredes.append(w)
    gid_p = vistas_ifc.criar_vista(f, "Planta_R3", "PLANTA", escala="1:100", origem=(0.0, 0.0, 0.0), tamanho=(10.0, 10.0, 3.0))
    api.run("spatial.assign_container", f, relating_structure=pav, products=[f.by_guid(gid_p)])
    gid_c = vistas_ifc.criar_vista(f, "Corte_R3", "CORTE", escala="1:100", origem=(-1.0, -1.0, -0.5), tamanho=(10.0, 6.0, 6.0))
    eixo = f.by_guid(gid_c).ObjectPlacement.RelativePlacement
    eixo.Axis = f.create_entity("IfcDirection", DirectionRatios=(0.0, -1.0, 0.0))
    eixo.RefDirection = f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
    f.by_guid(gid_c).Representation.Representations[0].Items[0].TreeRootExpression.Position.Location.Coordinates = (0.0, 0.0, -6.0)
    if salvar:
        f.write(str(caminho))
    ped = {
        "protocolo": 1, "op": "desenho", "elementos": [[w.id(), w.GlobalId] for w in paredes],
        "vista": {"tipo": "PLANTA", "guid": gid_p, "altura_corte_m": 1.2, "pavimento": pav.GlobalId, "escala": 1.0},
        "moveis_como_caixa": False, "caixas_coords": {paredes[0].id(): [0.0, 0.0, 0.0, 2.0, 0.2, 3.0]}, "contexto": {"unidades": "METRE"},
    }
    return f, ped, {"paredes": paredes, "gid_planta": gid_p, "gid_corte": gid_c}


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


class _IfcEspiao:
    def __init__(self, ifc): self._ifc, self.chamadas = ifc, 0
    def by_guid(self, g: str): self.chamadas += 1; return self._ifc.by_guid(g)
    def by_id(self, i: int): self.chamadas += 1; return self._ifc.by_id(i)
    def by_type(self, t: str): self.chamadas += 1; return self._ifc.by_type(t)


class _CacheEspiao(M.CacheDesenho):
    def __init__(self, pasta: Path, *, ao_obter=None, antes_chave=None):
        super().__init__(pasta)
        self.arquivos, self.assinaturas, self.chaves, self.pedidos = [], [], [], []
        self.guardadas, self.guardou = {}, 0
        self._ao_obter, self._antes_chave = ao_obter, antes_chave

    def chave(self, ifc, pedido: dict, cancelar: threading.Event | None = None, *, arquivo=None, assinatura=None) -> str:
        self.arquivos.append(arquivo)
        self.assinaturas.append(assinatura)
        self.pedidos.append(dict(pedido))
        if self._antes_chave is not None:
            self._antes_chave(arquivo, assinatura)
        kw = {k: v for k, v in (("arquivo", arquivo), ("assinatura", assinatura)) if v is not None}
        ch = super().chave(ifc, pedido, cancelar=cancelar, **kw)
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
    g.pronto.connect(_ok); g.falhou.connect(_err)
    QTimer.singleShot(10_000, loop.quit)
    try:
        g.pedir(tipo, ifc, gid, **kw)
        loop.exec()
    finally:
        g.pronto.disconnect(_ok); g.falhou.disconnect(_err)
    assert fim and fim[0][0] == "pronto", f"gerente nao concluiu com pronto: {fim!r}"
    return fim[0][1]


def _mutar_ifc(arq: Path, bytes_orig: bytes, st0, marca: bytes = b"\n/* V2 */\n"):
    arq.write_bytes(bytes_orig + marca)
    os.utime(arq, ns=(st0.st_atime_ns, st0.st_mtime_ns + 2_000_000_000))
    st1 = arq.stat()
    assert st1.st_size != st0.st_size and st1.st_mtime_ns != st0.st_mtime_ns
    return st1


def _instalar_refino_falso(monkeypatch):
    exec_real = auxiliar.executar

    def _fake(preparado, *args, executor=None, **kw):
        q = preparado.pedido
        if executor is None and q.get("op") == "peca_visivel":
            tag = "V2_NOVA" if b"/* V2 */" in Path(q["arquivo"]).read_bytes() else "V1_VELHA"
            gid = q["elementos"][0][1]
            return {"ok": True, "grupo": f'<g ifc:guid="{gid}" data-v="{tag}"><path d="M0 0L2 0Z"/></g>', "tempos": {}}
        return exec_real(preparado, *args, executor=executor, **kw)

    monkeypatch.setattr(auxiliar, "executar", _fake)


def _exec_checa_sig(tag_mem: str = "MEMORIA_V1", tag_disco: str = "DISCO_V2", registro: list | None = None):
    def _exec(q):
        if q.get("op") != "desenho":
            return local.executar(q)
        if registro is not None:
            registro.append(dict(q))
        if "assinatura" in q:
            try:
                st = os.stat(q["arquivo"])
                atual = [int(st.st_size), int(st.st_mtime_ns)]
            except OSError:
                atual = None
            if atual != list(q["assinatura"]):
                return {"ok": False, "erro": {"tipo": "Divergente", "mensagem": "assinatura divergiu", "rastro": ""}}
            return _ok_svg(f"<svg>{tag_disco}</svg>")
        return _ok_svg(f"<svg>{tag_mem}</svg>")
    return _exec


def test_contrato_chave_assinatura_sem_stat_proprio(tmp_path, monkeypatch):
    """DESENHO #2: chave(..., arquivo=, assinatura=) nao faz os.stat/Path.stat; sem assinatura = modo grafo."""
    sig_fn = inspect.signature(M.CacheDesenho.chave)
    for nome in ("arquivo", "assinatura"):
        assert nome in sig_fn.parameters, f"CacheDesenho.chave precisa aceitar {nome}="
        p = sig_fn.parameters[nome]
        assert p.kind == inspect.Parameter.KEYWORD_ONLY and p.default is None

    arq = tmp_path / "modelo.ifc"
    f, ped, _ = _criar_ifc(arq)
    arq_res = arq.resolve()
    bytes_v1, st1 = arq_res.read_bytes(), arq_res.stat()
    sig1 = M.assinatura_arquivo(arq_res)
    assert sig1 == (int(st1.st_size), int(st1.st_mtime_ns))
    loop_a, loop_b = tmp_path / "loop_a.ifc", tmp_path / "loop_b.ifc"
    loop_a.symlink_to(loop_b); loop_b.symlink_to(loop_a)
    for invalido in (tmp_path / "ausente.ifc", tmp_path, loop_a, "x\x00y.ifc", 123):
        assert M.assinatura_arquivo(invalido) is None

    c, ifc_esp, cont = M.CacheDesenho(tmp_path / "cache"), _IfcEspiao(f), _espiar_grafo(monkeypatch)
    k_grafo = c.chave(f, ped)
    cont["ser"] = cont["elem"] = 0

    os_stat_real, path_stat_real, stats = os.stat, Path.stat, {"os": 0, "path": 0}
    monkeypatch.setattr(os, "stat", lambda *a, **kw: (stats.__setitem__("os", stats["os"] + 1), os_stat_real(*a, **kw))[1])
    monkeypatch.setattr(Path, "stat", lambda self, *a, **kw: (stats.__setitem__("path", stats["path"] + 1), path_stat_real(self, *a, **kw))[1])

    k1 = c.chave(ifc_esp, ped, arquivo=arq_res, assinatura=sig1)
    assert _eh_sha256_hex(k1) and k1 != k_grafo and k1 == c.chave(ifc_esp, ped, arquivo=str(arq_res), assinatura=sig1)
    assert stats == {"os": 0, "path": 0} and cont["ser"] == 0 and cont["elem"] == 0 and ifc_esp.chamadas == 0

    arq_res.write_bytes(bytes_v1 + b"\n/* V2 */\n")
    os.utime(arq_res, ns=(st1.st_atime_ns, st1.st_mtime_ns + 2_000_000_000))
    sig2 = (len(bytes_v1) + len(b"\n/* V2 */\n"), int(st1.st_mtime_ns + 2_000_000_000))
    assert c.chave(ifc_esp, ped, arquivo=arq_res, assinatura=sig1) == k1
    k2 = c.chave(ifc_esp, ped, arquivo=arq_res, assinatura=sig2)
    k_fict = c.chave(ifc_esp, ped, arquivo=tmp_path / "ficticio.ifc", assinatura=(1234, 567890))
    assert k2 != k1 and k_fict != k1 and k_fict != k_grafo
    assert stats == {"os": 0, "path": 0} and cont["ser"] == 0 and cont["elem"] == 0 and ifc_esp.chamadas == 0

    assert c.chave(f, ped, arquivo=None, assinatura=sig1) == k_grafo
    assert stats == {"os": 0, "path": 0} and cont["ser"] > 0 and cont["elem"] > 0


@pytest.mark.parametrize("ponto", ["pedir_para_motor", "gerente_para_refino"])
def test_defeito1_gerente_refino_mutacao_nao_grava_v1_sob_v2(app, tmp_path, monkeypatch, ponto):
    """REVISAO2 #1: mutacao V1->V2 entre pedir()/_motor_padrao e refinar_pesados nunca grava V1_VELHA sob V2."""
    arq = tmp_path / f"ger_ref_{ponto}.ifc"
    f, _ped, meta = _criar_ifc(arq)
    w0, bytes_v1, st1 = meta["paredes"][0], arq.read_bytes(), arq.stat()
    svg_sil = f'<svg xmlns:ifc="x"><g ifc:guid="{w0.GlobalId}" data-silhueta="1"><path d="M0 0L1 0Z"/></g></svg>'
    _instalar_refino_falso(monkeypatch)
    mutou = [False]
    _muta = lambda: None if mutou[0] else (mutou.__setitem__(0, True), _mutar_ifc(arq, bytes_v1, st1))
    alvo_mod, alvo_attr = (G, "_motor_padrao") if ponto == "pedir_para_motor" else (refino, "refinar_pesados")
    real = getattr(alvo_mod, alvo_attr)
    monkeypatch.setattr(alvo_mod, alvo_attr, lambda *a, **kw: (_muta(), real(*a, **kw))[1])

    esp = _CacheEspiao(tmp_path / f"c_{ponto}")
    pesados = [{"id": w0.id(), "guid": w0.GlobalId, "faces": 120}]
    g = G.GerenteDesenho(cache=esp, filho_persistente=False)
    try:
        _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=2, revisao_salva=2, executor=lambda _q: _ok_svg(svg_sil, pesados))
    finally:
        g.fechar()
    assert mutou[0]

    chamou_v2 = [0]
    exec_v2 = lambda _q: (chamou_v2.__setitem__(0, chamou_v2[0] + 1), {"ok": True, "grupo": f'<g ifc:guid="{w0.GlobalId}" data-v="V2_NOVA"><path d="M0 0L3 0Z"/></g>', "tempos": {}})[1]
    out2 = refino.refinar_pesados(f, esp.pedidos[0], {"svg": svg_sil, "pesados": pesados}, executor=exec_v2, cache=esp, caminho_ifc=arq)
    assert chamou_v2[0] == 1 and 'data-v="V1_VELHA"' not in out2["svg"] and 'data-v="V2_NOVA"' in out2["svg"]


@pytest.mark.parametrize("modo", ["planta", "corte"])
def test_defeito2_arq_none_v2_surgindo_antes_de_preparar_nao_envenena_grafo(tmp_path, modo):
    """REVISAO2 #2a + DESENHO #4: sig None nunca passa caminho_ifc ao preparar; arquivo V2 surgindo nao envenena grafo."""
    arq_ausente = tmp_path / f"surge_{modo}.ifc"
    f, _ped, meta = _criar_ifc(arq_ausente, salvar=False)
    surgiu, pedidos_1, chamou_2 = [False], [], [0]

    def _ao_obter(_ch, res):
        if res is None and not surgiu[0]:
            surgiu[0] = True
            f.write(str(arq_ausente))
            arq_ausente.write_bytes(arq_ausente.read_bytes() + b"\n/* V2 */\n")

    def _exec1(q):
        if q.get("op") != "desenho":
            return local.executar(q)
        pedidos_1.append(dict(q))
        do_disco = "assinatura" in q or Path(q["arquivo"]).resolve() == arq_ausente.resolve()
        return _ok_svg("<svg>DO_ARQUIVO_V2</svg>" if do_disco else "<svg>DA_MEMORIA_V1</svg>")

    exec2 = lambda q: local.executar(q) if q.get("op") != "desenho" else (chamou_2.__setitem__(0, chamou_2[0] + 1), _ok_svg("<svg>SENTINELA</svg>"))[1]
    esp = _CacheEspiao(tmp_path / f"c_{modo}", ao_obter=_ao_obter)
    r1 = _gerar(modo, f, meta, caminho_ifc=arq_ausente, cache=esp, executor=_exec1)
    r2 = _gerar(modo, f, meta, caminho_ifc=None, cache=esp, executor=exec2)
    assert surgiu[0] and len(pedidos_1) == 1
    assert "assinatura" not in pedidos_1[0] and Path(pedidos_1[0]["arquivo"]).resolve() != arq_ausente.resolve()
    assert r1.svg == "<svg>DA_MEMORIA_V1</svg>" and r2.svg == "<svg>DA_MEMORIA_V1</svg>" and chamou_2[0] == 0


@pytest.mark.parametrize("modo", ["planta", "corte"])
def test_defeito2_symlink_redirecionado_nao_envenena_alvo_antigo(tmp_path, modo):
    """REVISAO2 #2b + DESENHO #4: symlink resolvido uma vez; redirecionar para b.ifc (mesmo stat) nao envenena a.ifc."""
    arq_a, arq_b, link = tmp_path / f"a_{modo}.ifc", tmp_path / f"b_{modo}.ifc", tmp_path / f"link_{modo}.ifc"
    f, _ped, meta = _criar_ifc(arq_a)
    bytes_a, st_a = arq_a.read_bytes(), arq_a.stat()
    bytes_b = bytes_a.replace(b"PAREDE_R3_0000", b"PAREDE_BB_0000")
    assert bytes_b != bytes_a and len(bytes_b) == len(bytes_a)
    _restaurar_ifc(arq_b, bytes_b, st_a)
    assert M.assinatura_arquivo(arq_a) == M.assinatura_arquivo(arq_b)
    link.symlink_to(arq_a)
    redirecionou, pedidos_1, chamou_a2 = [False], [], [0]

    def _ao_obter(_ch, res):
        if res is None and not redirecionou[0]:
            redirecionou[0] = True
            link.unlink(); link.symlink_to(arq_b)

    def _exec_ab(q):
        if q.get("op") != "desenho":
            return local.executar(q)
        pedidos_1.append(dict(q))
        alvo = Path(q["arquivo"]).resolve()
        return _ok_svg("<svg>DESENHO_A</svg>" if alvo == arq_a.resolve() else ("<svg>DESENHO_B</svg>" if alvo == arq_b.resolve() else "<svg>MEMORIA</svg>"))

    exec_a2 = lambda q: local.executar(q) if q.get("op") != "desenho" else (chamou_a2.__setitem__(0, chamou_a2[0] + 1), _ok_svg("<svg>RECALC</svg>"))[1]
    esp = _CacheEspiao(tmp_path / f"cs_{modo}", ao_obter=_ao_obter)
    r1 = _gerar(modo, f, meta, caminho_ifc=link, cache=esp, executor=_exec_ab)
    r2 = _gerar(modo, f, meta, caminho_ifc=arq_a, cache=esp, executor=exec_a2)
    assert redirecionou[0] and len(pedidos_1) == 1 and Path(pedidos_1[0]["arquivo"]).resolve() == arq_a.resolve()
    assert r1.svg == "<svg>DESENHO_A</svg>" and r2.svg == "<svg>DESENHO_A</svg>" and chamou_a2[0] == 0


def test_defeito3_refino_mutacao_entre_sig_e_chave_nao_serve_v2_em_v1(tmp_path):
    """REVISAO2 #3: mutacao V1->V2 entre leitura da sig e cache.chave em refino nao da hit em PECA_V2."""
    arq = tmp_path / "ref_d3.ifc"
    f, ped, meta = _criar_ifc(arq)
    w0, bytes_v1, st1, sig_v1 = meta["paredes"][0], arq.read_bytes(), arq.stat(), M.assinatura_arquivo(arq)
    st2 = _mutar_ifc(arq, bytes_v1, st1); bytes_v2 = arq.read_bytes()

    res = {"svg": f'<svg xmlns:ifc="x"><g ifc:guid="{w0.GlobalId}" data-silhueta="1"><path d="M0 0L1 0Z"/></g></svg>', "pesados": [{"id": w0.id(), "guid": w0.GlobalId, "faces": 120}]}
    esp = _CacheEspiao(tmp_path / "cr")
    refino.refinar_pesados(f, ped, res, cache=esp, caminho_ifc=arq, executor=lambda _q: {"ok": True, "grupo": f'<g ifc:guid="{w0.GlobalId}" data-v="PECA_V2"><path d="M0 0L2 0Z"/></g>', "tempos": {}})
    guardou_seed = esp.guardou

    _restaurar_ifc(arq, bytes_v1, st1)
    mutou, chamou_v1 = [False], [0]
    esp._antes_chave = lambda _a, _s: None if mutou[0] else (mutou.__setitem__(0, True), _restaurar_ifc(arq, bytes_v2, st2))
    exec_v1 = lambda _q: (chamou_v1.__setitem__(0, chamou_v1[0] + 1), {"ok": True, "grupo": f'<g ifc:guid="{w0.GlobalId}" data-v="PECA_V1"><path d="M0 0L1 0Z"/></g>', "tempos": {}})[1]
    out = refino.refinar_pesados(f, ped, res, cache=esp, caminho_ifc=arq, executor=exec_v1)
    assert mutou[0] and chamou_v1[0] == 1 and 'data-v="PECA_V2"' not in out["svg"] and 'data-v="PECA_V1"' in out["svg"]
    assert esp.assinaturas[-1] == sig_v1 and esp.guardou == guardou_seed


@pytest.mark.parametrize("modo", ["planta", "corte"])
def test_defeito3_planta_corte_mutacao_entre_sig_e_chave_nao_serve_v2_em_v1(tmp_path, modo):
    """REVISAO2 #3: mutacao V1->V2 entre leitura da sig e cache.chave em planta/corte nao da hit em V2."""
    arq = tmp_path / f"d3_{modo}.ifc"
    f, _ped, meta = _criar_ifc(arq)
    bytes_v1, st1, sig_v1 = arq.read_bytes(), arq.stat(), M.assinatura_arquivo(arq)
    st2 = _mutar_ifc(arq, bytes_v1, st1); bytes_v2 = arq.read_bytes()

    esp = _CacheEspiao(tmp_path / f"c3_{modo}")
    _gerar(modo, f, meta, caminho_ifc=arq, cache=esp, executor=lambda q: local.executar(q) if q.get("op") != "desenho" else _ok_svg("<svg>DESENHO_V2</svg>"))
    ch_v2 = esp.chaves[-1]

    _restaurar_ifc(arq, bytes_v1, st1)
    idx_inicio, mutou = len(esp.assinaturas), [False]
    esp._antes_chave = lambda _a, _s: None if mutou[0] else (mutou.__setitem__(0, True), _restaurar_ifc(arq, bytes_v2, st2))
    r = _gerar(modo, f, meta, caminho_ifc=arq, cache=esp, executor=_exec_checa_sig())
    assert mutou[0] and r.svg == "<svg>MEMORIA_V1</svg>"
    assert esp.assinaturas[idx_inicio] == sig_v1 and esp.obter(ch_v2)["svg"] == "<svg>DESENHO_V2</svg>"


@pytest.mark.parametrize("modo", ["planta", "corte", "gerente_planta"])
def test_desenho_preparar_recebe_mesma_sig_e_dispara_divergente(app, tmp_path, monkeypatch, modo):
    """DESENHO #1,#3,#5: preparar recebe a mesma sig (V1); mutacao para V2 dispara Divergente e grava so grafo."""
    arq = tmp_path / f"prep_{modo}.ifc"
    f, _ped, meta = _criar_ifc(arq)
    bytes_v1, st1, sig_v1 = arq.read_bytes(), arq.stat(), M.assinatura_arquivo(arq)
    mutou, pedidos = [False], []
    _muta = lambda: None if mutou[0] else (mutou.__setitem__(0, True), _mutar_ifc(arq, bytes_v1, st1))

    if modo == "gerente_planta":
        real = G._motor_padrao
        monkeypatch.setattr(G, "_motor_padrao", lambda *a, **kw: (_muta(), real(*a, **kw))[1])
        esp = _CacheEspiao(tmp_path / f"cp_{modo}")
    else:
        esp = _CacheEspiao(tmp_path / f"cp_{modo}", ao_obter=lambda _ch, res: _muta() if res is None else None)

    exec_filho = _exec_checa_sig(registro=pedidos)
    if modo == "gerente_planta":
        g = G.GerenteDesenho(cache=esp, filho_persistente=False)
        try:
            svg = _pedir_gerente(app, g, "planta", f, meta["gid_planta"], caminho_ifc=arq, revisao=2, revisao_salva=2, executor=exec_filho)["svg"]
        finally:
            g.fechar()
    else:
        svg = _gerar(modo, f, meta, caminho_ifc=arq, cache=esp, executor=exec_filho).svg

    assert mutou[0] and pedidos and pedidos[0].get("assinatura") == list(sig_v1)
    assert len(pedidos) == 2 and "assinatura" not in pedidos[1] and svg == "<svg>MEMORIA_V1</svg>"
    assert esp.assinaturas[0] == sig_v1
    cmp = M.CacheDesenho(tmp_path / f"cmp_{modo}")
    ch_v1, ch_grafo = esp.chaves[0], cmp.chave(f, esp.pedidos[0])
    ch_v2 = cmp.chave(f, esp.pedidos[0], arquivo=arq.resolve(), assinatura=M.assinatura_arquivo(arq))
    assert ch_v1 not in esp.guardadas and ch_v2 not in esp.guardadas
    assert ch_grafo in esp.guardadas and esp.obter(ch_grafo)["svg"] == "<svg>MEMORIA_V1</svg>"
