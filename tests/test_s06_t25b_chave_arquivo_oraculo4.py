# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T25b (rodada 4, escopo estreito): defeitos 1 e 2 minimo da REVISAO3.md.
- (A) Defeito 1: corte.py -> selecao.selecionar -> auxiliar.preparar recebe e usa a mesma
  assinatura_ifc do pedir() (zero stat extra; mutacao V1->V2 entre pedir e selecionar nao
  envenena SessaoSelecao nem o cache; Divergente no corte nao reaproveita caixas de V2),
  cobrindo cenarios A e B da REVISAO3 com local.executar real.
- (B) Defeito 2 minimo: auxiliar.preparar com caminho_ifc invalido (symlink circular,
  byte nulo, tipo invalido) + assinatura nao levanta excecao nao tratada e cai em memoria.
"""
from __future__ import annotations

import os, sys, threading
from pathlib import Path

import ifcopenshell
import pytest
import s06_t07_aux as X
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from s06_t15i_aux import ExecutorEspiao, _criar_corte_xyz, auxiliar, corte, local, selecao

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtCore")
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa: E402

from openbim_app.desenho import cache as M, gerente as G  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QCoreApplication.instance() or QCoreApplication([])


class _CacheEspiao(M.CacheDesenho):
    def __init__(self, pasta: Path):
        super().__init__(pasta)
        self.assinaturas, self.chaves, self.pedidos, self.guardadas = [], [], [], {}

    def chave(self, ifc, pedido: dict, cancelar: threading.Event | None = None, *, arquivo=None, assinatura=None) -> str:
        self.assinaturas.append(assinatura)
        self.pedidos.append(dict(pedido))
        kw = {k: v for k, v in (("arquivo", arquivo), ("assinatura", assinatura)) if v is not None}
        ch = super().chave(ifc, pedido, cancelar=cancelar, **kw)
        self.chaves.append(ch)
        return ch

    def guardar(self, chave: str, dados: dict) -> bool:
        self.guardadas[chave] = dict(dados)
        return super().guardar(chave, dados)


def _pedir_gerente(app, g: G.GerenteDesenho, tipo: str, ifc, gid: str, **kw):
    fim, loop = [], QEventLoop()
    _ok = lambda ch, dados: (fim.append(("pronto", dados)), loop.quit())
    _err = lambda ch, msg: (fim.append(("falhou", msg)), loop.quit())
    g.pronto.connect(_ok); g.falhou.connect(_err)
    QTimer.singleShot(15_000, loop.quit)
    try:
        g.pedir(tipo, ifc, gid, **kw)
        loop.exec()
    finally:
        g.pronto.disconnect(_ok); g.falhou.disconnect(_err)
    assert fim and fim[0][0] == "pronto", f"gerente nao concluiu com pronto: {fim!r}"
    return fim[0][1]


def _criar_modelo_corte(arq: Path):
    """V1: W0 cruza faixa do corte (y in [0.2, 0.4]); W1 fora da faixa (y in [3.0, 3.2]) mas na margem segura."""
    exigir()
    f, pavs = X.estrutura("IFC4", n_pav=1)
    w0 = X.caixa(f, "IfcWall", "W0", 0.0, 0.2, 0.0, 2.0, 0.2, 3.0)
    w1 = X.caixa(f, "IfcWall", "W1", 0.0, 3.0, 0.0, 2.0, 0.2, 3.0)
    X.conter(f, pavs[0], w0, w1)
    gid_corte = _criar_corte_xyz(f, "Corte_R4", -0.5, 3.0, -0.5, 1.0, -0.5, 3.5)
    f.write(str(arq))
    return f, {"w0": w0, "w1": w1, "gid_corte": gid_corte}


def _gerar_bytes_v2(arq_v1: Path, tmp_dir: Path, posicoes: dict[int, tuple[float, float, float]], marca: bytes) -> bytes:
    f2 = ifcopenshell.open(str(arq_v1))
    for id_step, coords in posicoes.items():
        f2.by_id(id_step).ObjectPlacement.RelativePlacement.Location.Coordinates = coords
    tmp = tmp_dir / f"tmp_{abs(hash(marca))}.ifc"
    f2.write(str(tmp))
    dados = tmp.read_bytes() + marca
    tmp.unlink(missing_ok=True)
    return dados


def _mutar_para(arq: Path, bytes_v2: bytes, st_ref) -> tuple[int, int]:
    arq.write_bytes(bytes_v2)
    os.utime(arq, ns=(st_ref.st_atime_ns, st_ref.st_mtime_ns + 2_000_000_000))
    st2 = arq.stat()
    assert st2.st_size != st_ref.st_size and st2.st_mtime_ns != st_ref.st_mtime_ns
    return int(st2.st_size), int(st2.st_mtime_ns)


def _veio_de_path_resolve() -> bool:
    frame = sys._getframe(2)
    for _ in range(3):
        if frame is None:
            return False
        if frame.f_code.co_name == "resolve" and frame.f_code.co_filename.endswith("pathlib.py"):
            return True
        frame = frame.f_back
    return False


def _eh_alvo(caminho, nome_arq: str) -> bool:
    try:
        return Path(caminho).name == nome_arq
    except (TypeError, ValueError):
        return False


def _asserir_cache_sem_chaves_arquivo(tmp_path: Path, nome: str, f, esp_cache: _CacheEspiao, arq_res: Path, sig_v1, sig_v2):
    cmp = M.CacheDesenho(tmp_path / nome)
    for ped in esp_cache.pedidos:
        assert cmp.chave(f, ped, arquivo=arq_res, assinatura=sig_v1) not in esp_cache.guardadas
        assert cmp.chave(f, ped, arquivo=arq_res, assinatura=sig_v2) not in esp_cache.guardadas


def _rodar_cenario_gerente(app, tmp_path: Path, monkeypatch, nome: str, posicoes_v2):
    arq = tmp_path / f"{nome}.ifc"
    f, meta = _criar_modelo_corte(arq)
    w0, w1, gid_corte = meta["w0"], meta["w1"], meta["gid_corte"]
    st1 = arq.stat()
    arq_res, sig_v1 = M.resolver_assinatura(arq)
    bytes_v2 = _gerar_bytes_v2(arq, tmp_path, posicoes_v2(w0, w1), f"\n/* {nome} */\n".encode())
    ctrl = corte.gerar_corte(f, gid_corte, executor=local.executar, motor_visivel=True)
    assert ctrl.n_paths > 0 and ctrl.selecao.ids == (w0.id(),)

    mutou, sig_v2_ref, motor_real = [False], [None], G._motor_padrao
    def _motor_muta(*a, **kw):
        if not mutou[0]:
            mutou[0] = True
            sig_v2_ref[0] = _mutar_para(arq, bytes_v2, st1)
        return motor_real(*a, **kw)

    monkeypatch.setattr(G, "_motor_padrao", _motor_muta)
    esp_cache, esp_exec = _CacheEspiao(tmp_path / f"cache_{nome}"), ExecutorEspiao(local.executar)
    g = G.GerenteDesenho(cache=esp_cache, filho_persistente=False)
    try:
        req1 = _pedir_gerente(app, g, "corte", f, gid_corte, caminho_ifc=arq, revisao=1, revisao_salva=1, executor=esp_exec)
        req2 = _pedir_gerente(app, g, "corte", f, gid_corte, caminho_ifc=None, revisao=1, revisao_salva=None, executor=esp_exec)
    finally:
        g.fechar()
    return f, meta, ctrl, arq_res, sig_v1, sig_v2_ref[0], mutou[0], esp_cache, esp_exec, req1, req2


def test_defeito1_corte_selecao_usa_mesma_assinatura_do_pedir_sem_stat_extra(app, tmp_path, monkeypatch):
    """Defeito 1: corte -> selecao -> auxiliar.preparar usa a assinatura_ifc do pedir() com zero os.stat extra."""
    arq = tmp_path / "corte_zero_stat.ifc"
    f, meta = _criar_modelo_corte(arq)
    w0, gid_corte = meta["w0"], meta["gid_corte"]
    arq_res, sig_v1 = M.resolver_assinatura(arq)
    assert arq_res is not None and sig_v1 is not None

    os_stat_real, path_stat_real = os.stat, Path.stat
    contagem = {"ativo": False, "stats_arq": 0}
    monkeypatch.setattr(os, "stat", lambda path, *a, **kw: (contagem.__setitem__("stats_arq", contagem["stats_arq"] + 1) if (contagem["ativo"] and _eh_alvo(path, arq.name) and not _veio_de_path_resolve()) else None, os_stat_real(path, *a, **kw))[1])
    monkeypatch.setattr(Path, "stat", lambda self, *a, **kw: (contagem.__setitem__("stats_arq", contagem["stats_arq"] + 1) if (contagem["ativo"] and _eh_alvo(self, arq.name) and not _veio_de_path_resolve()) else None, path_stat_real(self, *a, **kw))[1])

    motor_real = G._motor_padrao
    def _motor_contando(*a, **kw):
        contagem["ativo"] = True
        try:
            return motor_real(*a, **kw)
        finally:
            contagem["ativo"] = False

    monkeypatch.setattr(G, "_motor_padrao", _motor_contando)
    pedidos, stats_no_exec = [], {}
    def _exec_fake(q):
        pedidos.append(dict(q))
        stats_no_exec[q.get("op")] = contagem["stats_arq"]
        if q.get("op") == "caixas":
            return {"ok": True, "caixas_envolventes": {str(w0.id()): [0.0, 0.2, 0.0, 2.0, 0.4, 3.0]}, "falhas_geometria": [], "passagens_iterator": 1, "erros_iterator": []}
        return {"ok": True, "svg": "<svg><path d='M0 0L1 0'/></svg>", "n_paths": 1, "tempos": {}, "caixas": []}

    g = G.GerenteDesenho(cache=_CacheEspiao(tmp_path / "c_zero"), filho_persistente=False)
    try:
        res = _pedir_gerente(app, g, "corte", f, gid_corte, caminho_ifc=arq, revisao=1, revisao_salva=1, executor=_exec_fake)
    finally:
        g.fechar()

    caixas_peds = [p for p in pedidos if p.get("op") == "caixas"]
    desenho_peds = [p for p in pedidos if p.get("op") == "desenho"]
    assert res["n_paths"] == 1
    assert len(caixas_peds) == 1 and caixas_peds[0].get("assinatura") == list(sig_v1)
    assert len(desenho_peds) == 1 and desenho_peds[0].get("assinatura") == list(sig_v1)
    assert stats_no_exec.get("caixas") == 0, f"os.stat extra em corte->selecao->preparar: {stats_no_exec}"
    assert stats_no_exec.get("desenho") == 0, f"os.stat extra antes de desenho: {stats_no_exec}"


def test_defeito1_cenario_a_v2_fora_da_faixa_nao_devolve_vazio_nem_envenena_sessao(app, tmp_path, monkeypatch):
    """REVISAO3 Cenario A: V2 tira paredes da faixa entre pedir() e _motor_padrao; nao devolve SVG vazio nem envenena SessaoSelecao."""
    f, _meta, ctrl, arq_res, sig_v1, sig_v2, mutou, esp_cache, esp_exec, req1, req2 = _rodar_cenario_gerente(
        app, tmp_path, monkeypatch, "cenario_a", lambda w0, _w1: {w0.id(): (0.0, 4.0, 0.0)},
    )
    caixas_peds = [p for p in esp_exec.chamadas if p.get("op") == "caixas"]
    assert mutou and caixas_peds and caixas_peds[0].get("assinatura") == list(sig_v1)
    assert req1["n_paths"] == ctrl.n_paths and req1["svg"] == ctrl.svg
    assert req2["n_paths"] == ctrl.n_paths and req2["svg"] == ctrl.svg
    _asserir_cache_sem_chaves_arquivo(tmp_path, "cmp_a", f, esp_cache, arq_res, sig_v1, sig_v2)


def test_defeito1_cenario_b_v2_troca_elementos_divergente_nao_reaproveita_caixas_v2(app, tmp_path, monkeypatch):
    """REVISAO3 Cenario B: V2 troca W0 por W1 entre pedir() e _motor_padrao; Divergente nao reaproveita caixas de V2 nem envenena cache."""
    f, meta, ctrl, arq_res, sig_v1, sig_v2, mutou, esp_cache, esp_exec, req1, req2 = _rodar_cenario_gerente(
        app, tmp_path, monkeypatch, "cenario_b", lambda w0, w1: {w0.id(): (0.0, 4.0, 0.0), w1.id(): (0.0, 0.2, 0.0)},
    )
    w0, w1 = meta["w0"], meta["w1"]
    caixas_peds = [p for p in esp_exec.chamadas if p.get("op") == "caixas"]
    desenho_mem = [p for p in esp_exec.pedidos_desenho if "assinatura" not in p]
    assert mutou and caixas_peds and desenho_mem
    assert caixas_peds[0].get("assinatura") == list(sig_v1)
    assert all([w1.id(), w1.GlobalId] not in p.get("elementos", []) for p in desenho_mem)
    assert desenho_mem[-1].get("elementos") == [[w0.id(), w0.GlobalId]]
    assert req1["n_paths"] == ctrl.n_paths and req1["svg"] == ctrl.svg
    assert req2["n_paths"] == ctrl.n_paths and req2["svg"] == ctrl.svg
    _asserir_cache_sem_chaves_arquivo(tmp_path, "cmp_b", f, esp_cache, arq_res, sig_v1, sig_v2)


def test_defeito1_gerar_corte_direto_mutacao_entre_sig_e_selecao_nao_envenena(tmp_path, monkeypatch):
    """Defeito 1 em chamada direta corte.gerar_corte: mutacao V1->V2 entre resolver_assinatura e selecao.selecionar."""
    arq = tmp_path / "corte_direto_b.ifc"
    f, meta = _criar_modelo_corte(arq)
    w0, w1, gid_corte = meta["w0"], meta["w1"], meta["gid_corte"]
    st1 = arq.stat()
    _, sig_v1 = M.resolver_assinatura(arq)
    bytes_v2_b = _gerar_bytes_v2(arq, tmp_path, {w0.id(): (0.0, 4.0, 0.0), w1.id(): (0.0, 0.2, 0.0)}, b"\n/* V2_DIR */\n")
    ctrl = corte.gerar_corte(f, gid_corte, executor=local.executar, motor_visivel=True)

    mutou, sel_real = [False], selecao.selecionar
    monkeypatch.setattr(selecao, "selecionar", lambda *a, **kw: (None if mutou[0] else (mutou.__setitem__(0, True), _mutar_para(arq, bytes_v2_b, st1)), sel_real(*a, **kw))[1])
    sessao = selecao.SessaoSelecao()
    esp_cache, esp_exec = _CacheEspiao(tmp_path / "cache_dir"), ExecutorEspiao(local.executar)

    r1 = corte.gerar_corte(f, gid_corte, caminho_ifc=arq, sessao_selecao=sessao, cache=esp_cache, executor=esp_exec, motor_visivel=True)
    r2 = corte.gerar_corte(f, gid_corte, caminho_ifc=None, sessao_selecao=sessao, cache=esp_cache, executor=esp_exec, motor_visivel=True)

    caixas_peds = [p for p in esp_exec.chamadas if p.get("op") == "caixas"]
    assert mutou[0] and caixas_peds and caixas_peds[0].get("assinatura") == list(sig_v1)
    assert r1.selecao.ids == (w0.id(),) and r1.n_paths == ctrl.n_paths and r1.svg == ctrl.svg
    assert r2.selecao.ids == (w0.id(),) and r2.n_paths == ctrl.n_paths and r2.svg == ctrl.svg


@pytest.mark.parametrize("caso", ["symlink_circular", "byte_nulo", "tipo_invalido"])
def test_defeito2_preparar_caminho_invalido_com_assinatura_cai_em_memoria(tmp_path, caso):
    """Defeito 2 minimo: auxiliar.preparar com caminho_ifc invalido e assinatura nao explode; cai em modo memoria."""
    arq = tmp_path / f"prep_inv_{caso}.ifc"
    f, meta = _criar_modelo_corte(arq)
    w0, gid_corte = meta["w0"], meta["gid_corte"]
    ped = {"op": "caixas", "elementos": [[w0.id(), w0.GlobalId]], "vista": {"guid": gid_corte}}

    if caso == "symlink_circular":
        loop_a, loop_b = tmp_path / "loop_a.ifc", tmp_path / "loop_b.ifc"
        loop_a.symlink_to(loop_b); loop_b.symlink_to(loop_a)
        invalido = loop_a
    elif caso == "byte_nulo":
        invalido = "invalido\x00.ifc"
    else:
        invalido = 123

    with auxiliar.preparar(f, ped, caminho_ifc=invalido, assinatura=(123, 456)) as prep:
        arq_mem = Path(prep.pedido["arquivo"])
        assert "assinatura" not in prep.pedido
        assert arq_mem.parent == prep.pasta and arq_mem.is_file() and arq_mem.stat().st_size > 0
        pasta = prep.pasta
    assert not pasta.exists()
