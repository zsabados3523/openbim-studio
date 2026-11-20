# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oraculo F0-S06-T25 rodada 2: defeitos de cancelamento/determinismo/GIL e travas de mutantes."""
from __future__ import annotations

import json, os, subprocess, sys, threading, time
from pathlib import Path
from types import SimpleNamespace

import pytest
import s06_t07_aux as X
import s06_t07c_aux as C
from s05_conteudo_aux import _limpa, exigir  # noqa: F401  (fixture autouse)
from s06_t15i_aux import auxiliar, corte, local, planta

from openbim_app.desenho import cache as M, refino

CASA_SIMPLES = Path(__file__).resolve().parent / "amostras" / "casa-simples.ifc"
RAIZ_APP = Path(__file__).resolve().parent.parent / "app"


def _ifc_api():
    exigir()
    import ifcopenshell, ifcopenshell.api
    return ifcopenshell, ifcopenshell.api


def _ifc_minimo(n_props: int = 0, *, vista_props: int = 0):
    ifc, api = _ifc_api()
    f = api.run("project.create_file", version="IFC4")
    api.run("root.create_entity", f, ifc_class="IfcProject", name="P")
    api.run("unit.assign_unit", f)
    w = api.run("root.create_entity", f, ifc_class="IfcWall", name="W0")
    if n_props > 0:
        ps = api.run("pset.add_pset", f, product=w, name="Pset_Grande")
        api.run("pset.edit_pset", f, pset=ps, properties={f"K{i:04d}": i for i in range(n_props)})
    anot = None
    if vista_props > 0:
        anot = api.run("root.create_entity", f, ifc_class="IfcAnnotation", name="V0")
        pv = api.run("pset.add_pset", f, product=anot, name="Pset_Vista")
        api.run("pset.edit_pset", f, pset=pv, properties={f"V{i:04d}": i for i in range(vista_props)})
    vista = {"tipo": "PLANTA", "guid": anot.GlobalId} if anot is not None else {}
    return ifc, f, w, anot, {"protocolo": 1, "op": "desenho", "elementos": [[w.id(), w.GlobalId]], "vista": vista}


class _CacheEspiaoGuardar(M.CacheDesenho):
    def __init__(self, pasta: Path):
        super().__init__(pasta)
        self.chaves = self.guardou = 0

    def chave(self, ifc, pedido: dict, cancelar: threading.Event | None = None) -> str:
        self.chaves += 1
        return super().chave(ifc, pedido, cancelar=cancelar)

    def guardar(self, chave: str, dados: dict) -> bool:
        self.guardou += 1
        return super().guardar(chave, dados)


class _IfcEspiao:
    def __init__(self, ifc, *, disparar_guid: str | None = None, ev: threading.Event | None = None):
        self._ifc, self._disparar_guid, self._ev = ifc, disparar_guid, ev
        self.chamadas, self.guids = 0, []

    def by_guid(self, guid: str):
        self.chamadas += 1
        self.guids.append(str(guid))
        if self._disparar_guid is not None and str(guid) == self._disparar_guid and self._ev is not None:
            self._ev.set()
        return self._ifc.by_guid(guid)

    def by_id(self, ident: int):
        self.chamadas += 1
        return self._ifc.by_id(ident)

    def by_type(self, tipo: str):
        self.chamadas += 1
        return self._ifc.by_type(tipo)


def _checar_cancel_pos_chave(pasta: Path, esp: _CacheEspiaoGuardar, fn):
    with pytest.raises(auxiliar.DesenhoCancelado):
        fn()
    assert esp.chaves == 1 and esp.guardou == 0 and not list(pasta.rglob("*"))


def test_defeito1_planta_cancelar_apos_chave_nao_grava(tmp_path):
    """(1) Planta: cancelar apos chave e antes de guardar levanta DesenhoCancelado e nao grava."""
    exigir()
    f, pavs = X.estrutura("IFC4")
    X.conter(f, pavs[0], X.caixa(f, "IfcWall", "p1", 0.0, 0.0, 0.0, 2.0, 0.2, 2.0))
    gid, pasta, ev = X.vista(f, "PLANTA", pavs[0], nome="VP"), tmp_path / "cp", threading.Event()
    esp = _CacheEspiaoGuardar(pasta)
    exec_fake = lambda _q: (ev.set(), {"ok": True, "svg": "<svg/>", "n_paths": 1, "tempos": {}})[1]
    _checar_cancel_pos_chave(pasta, esp, lambda: planta.gerar_planta(f, gid, cache=esp, cancelar=ev, executor=exec_fake))


def test_defeito1_corte_cancelar_apos_chave_nao_grava(tmp_path):
    """(1) Corte: cancelar apos chave e antes de guardar levanta DesenhoCancelado e nao grava."""
    exigir()
    f, _g = C.modelo("IFC4")
    gid, pasta, ev = C.corte(f), tmp_path / "cc", threading.Event()
    esp = _CacheEspiaoGuardar(pasta)
    exec_fake = lambda q: local.executar(q) if q.get("op") != "desenho" else (ev.set(), {"ok": True, "svg": "<svg/>", "n_paths": 1, "tempos": {}})[1]
    _checar_cancel_pos_chave(pasta, esp, lambda: corte.gerar_corte(f, gid, cache=esp, cancelar=ev, executor=exec_fake))


def test_defeito1_refino_cancelar_apos_chave_nao_grava(tmp_path):
    """(1) Refino: cancelar apos chave e antes de guardar levanta DesenhoCancelado e nao grava."""
    ifc, _api = _ifc_api()
    f = ifc.open(str(CASA_SIMPLES))
    w = f.by_type("IfcWall")[0]
    ped = {"protocolo": 1, "op": "desenho", "elementos": [[w.id(), w.GlobalId]], "vista": {"tipo": "PLANTA"}}
    res = {"svg": f'<svg xmlns:ifc="x"><g ifc:guid="{w.GlobalId}" data-silhueta="1"><path d="M 0,0 L 1,0 Z"/></g></svg>', "pesados": [{"id": w.id(), "guid": w.GlobalId, "faces": 120}]}
    pasta, ev = tmp_path / "cr", threading.Event()
    esp = _CacheEspiaoGuardar(pasta)
    exec_fake = lambda _q: (ev.set(), {"ok": True, "grupo": f'<g ifc:guid="{w.GlobalId}"><path d="M 0,0 L 1,0 Z"/></g>', "tempos": {}})[1]
    _checar_cancel_pos_chave(pasta, esp, lambda: refino.refinar_pesados(f, ped, res, cache=esp, cancelar=ev, executor=exec_fake))


def test_defeito2_determinismo_set_frozenset_subprocessos():
    """(2) Determinismo com set/frozenset no pedido e em atributo de entidade (PYTHONHASHSEED=0,1,2,3)."""
    script = (
        "import json, sys, ifcopenshell; from openbim_app.desenho.cache import CacheDesenho\n"
        "c, f = CacheDesenho('/nao/usado'), ifcopenshell.open(sys.argv[1]); w = f.by_type('IfcWall')[0]\n"
        "ped = {'protocolo': 1, 'op': 'desenho', 'elementos': [[w.id(), w.GlobalId]], 'vista': {},\n"
        "       'tags': {'s0','s1','s2','s3','s4','s5','s6','s7'}, 'ftags': frozenset({'f0','f1','f2','f3','f4','f5','f6','f7'})}\n"
        "class Ent:\n"
        "    is_a = lambda s: 'IfcFake'; id = lambda s: 1; __len__ = lambda s: 2\n"
        "    attribute_name = lambda s, i: ('s', 'fs')[i]\n"
        "    __getitem__ = lambda s, i: ({'e0','e1','e2','e3','e4','e5','e6','e7'}, frozenset({'g0','g1','g2','g3','g4','g5','g6','g7'}))[i]\n"
        "class IfcStub:\n"
        "    by_guid = lambda s, g: Ent() if g == 'G1' else None; by_id = lambda s, i: None; by_type = lambda s, t: []\n"
        "print(json.dumps([c.chave(f, ped), c.chave(IfcStub(), {'elementos': [[1, 'G1']], 'vista': {}})]))\n"
    )
    ch_ped, ch_ent = [], []
    for seed in ("0", "1", "2", "3"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(RAIZ_APP)}
        proc = subprocess.run([sys.executable, "-c", script, str(CASA_SIMPLES)], capture_output=True, text=True, check=True, env=env, timeout=30)
        kp, ke = json.loads(proc.stdout.strip())
        ch_ped.append(kp)
        ch_ent.append(ke)
    assert len(set(ch_ped)) == 1 and len(set(ch_ent)) == 1, f"variou: ped={len(set(ch_ped))}, ent={len(set(ch_ent))}"


def test_defeito3_cancelar_ultimo_trecho_antes_return(tmp_path):
    """(3a) Cancelar disparado no ultimo elemento (<1000 nos) ainda levanta CacheCancelado antes do return."""
    _ifc, f, w, _anot, ped = _ifc_minimo(n_props=0)
    ev = threading.Event()
    with pytest.raises(M.CacheCancelado):
        M.CacheDesenho(tmp_path / "c").chave(_IfcEspiao(f, disparar_guid=w.GlobalId, ev=ev), ped, cancelar=ev)
    assert ev.is_set()


def test_defeito3_time_sleep_cede_gil_a_cada_intervalo_sem_relogio(tmp_path, monkeypatch):
    """(3b) time.sleep(0) cede o GIL a cada intervalo (>= nos//1000) sem depender do relogio."""
    _ifc, f, _w, _anot, ped = _ifc_minimo(n_props=2500)
    nos, sleeps, real_ser = [0], [], M._serializar

    def conta_ser(*args, **kwargs):
        nos[0] += 1
        return real_ser(*args, **kwargs)

    monkeypatch.setattr(M, "_serializar", conta_ser)
    monkeypatch.setattr(M, "time", SimpleNamespace(monotonic=lambda: 100.0, perf_counter=lambda: 100.0, sleep=sleeps.append, time=time.time))
    M.CacheDesenho(tmp_path / "c").chave(f, ped)
    assert nos[0] >= 5000 and all(s == 0 for s in sleeps)
    assert len(sleeps) >= nos[0] // 1000, f"poucos sleep(0): {len(sleeps)} para {nos[0]} nos"


def test_mutante4_prefixo_tamanho_hash_incremental(tmp_path, monkeypatch):
    """(4) Mutante: remover prefixo len(dados): permite colisao 'ab'+'c' vs 'a'+'bc'."""
    _ifc, f, _w, _anot, _ped = _ifc_minimo(n_props=0)
    real_dumps = M.json.dumps
    esp_dumps = lambda obj, *a, **kw: obj["entrada"] if isinstance(obj, dict) and set(obj) == {"entrada"} and isinstance(obj["entrada"], str) else real_dumps(obj, *a, **kw)
    monkeypatch.setattr(json, "dumps", esp_dumps)
    monkeypatch.setattr(M.json, "dumps", esp_dumps)
    c = M.CacheDesenho(tmp_path / "c")
    assert c.chave(f, {"protocolo": 1, "vista": {}, "elementos": ["ab", "c"]}) != c.chave(f, {"protocolo": 1, "vista": {}, "elementos": ["a", "bc"]})


def test_mutante5_intervalo_nos_1000_nao_5000(tmp_path, monkeypatch):
    """(5) Mutante: _INTERVALO_NOS=5000 falha (>= N/1000 checagens e <= 1000 nos entre duas)."""
    _ifc, f, _w, _anot, ped = _ifc_minimo(n_props=2000)
    nos, marcas, real_ser = [0], [], M._serializar

    def conta_ser(*args, **kwargs):
        nos[0] += 1
        return real_ser(*args, **kwargs)

    class EvEspiao(threading.Event):
        def is_set(self) -> bool:
            marcas.append(nos[0])
            return super().is_set()

    monkeypatch.setattr(M, "_serializar", conta_ser)
    M.CacheDesenho(tmp_path / "c").chave(f, ped, cancelar=EvEspiao())
    assert nos[0] >= 6000 and len(marcas) >= nos[0] / 1000
    assert max(b - a for a, b in zip(marcas, marcas[1:])) <= 1000


def test_mutante6_cancelar_inicio_e_durante_contexto(tmp_path, monkeypatch):
    """(6) Mutante: remover ctrl.checar() no inicio de chave() ou controle em _assinatura_contexto."""
    _ifc, f, w, anot, ped = _ifc_minimo(n_props=1, vista_props=1500)
    c, real_dumps, dumps_n = M.CacheDesenho(tmp_path / "c"), M.json.dumps, [0]

    def conta_dumps(*args, **kwargs):
        dumps_n[0] += 1
        return real_dumps(*args, **kwargs)

    monkeypatch.setattr(M.json, "dumps", conta_dumps)
    ev0 = threading.Event()
    ev0.set()
    for p in (ped, {**ped, "elementos": []}):
        w_ifc, dumps_n[0] = _IfcEspiao(f), 0
        with pytest.raises(M.CacheCancelado):
            c.chave(w_ifc, p, cancelar=ev0)
        assert w_ifc.chamadas == 0 and dumps_n[0] == 0
    for p in (ped, {**ped, "elementos": []}):
        ev_ctx = threading.Event()
        w_ifc, dumps_n[0] = _IfcEspiao(f, disparar_guid=anot.GlobalId, ev=ev_ctx), 0
        with pytest.raises(M.CacheCancelado):
            c.chave(w_ifc, p, cancelar=ev_ctx)
        assert dumps_n[0] == 0 and w.GlobalId not in w_ifc.guids


def test_cobertura7_relacoes_e_campo_entrada(tmp_path):
    """(7) Relacoes tipo, preenchimentos, preenche, partes, projecoes e campo entrada mudam a chave."""
    ifc, f, w, _anot, _ped = _ifc_minimo(n_props=0)
    wt = f.create_entity("IfcWallType", GlobalId=ifc.guid.new(), Name="TipoA", PredefinedType="STANDARD")
    f.create_entity("IfcRelDefinesByType", GlobalId=ifc.guid.new(), RelatedObjects=[w], RelatingType=wt)
    vao = f.create_entity("IfcOpeningElement", GlobalId=ifc.guid.new(), Name="VaoA")
    porta = f.create_entity("IfcDoor", GlobalId=ifc.guid.new(), Name="PortaA")
    f.create_entity("IfcRelFillsElement", GlobalId=ifc.guid.new(), RelatingOpeningElement=vao, RelatedBuildingElement=porta)
    parte = f.create_entity("IfcBuildingElementPart", GlobalId=ifc.guid.new(), Name="ParteA")
    f.create_entity("IfcRelAggregates", GlobalId=ifc.guid.new(), RelatingObject=w, RelatedObjects=[parte])
    proj = f.create_entity("IfcProjectionElement", GlobalId=ifc.guid.new(), Name="ProjA")
    f.create_entity("IfcRelProjectsElement", GlobalId=ifc.guid.new(), RelatingElement=w, RelatedFeatureElement=proj)
    c = M.CacheDesenho(tmp_path / "c")
    for alvo, rel_ent, novo in ((w, wt, "TipoB"), (vao, porta, "PortaB"), (porta, vao, "VaoB"), (w, parte, "ParteB"), (w, proj, "ProjB")):
        p = {"protocolo": 1, "vista": {}, "elementos": [[alvo.id(), alvo.GlobalId]]}
        k0, ant = c.chave(f, p), rel_ent.Name
        rel_ent.Name = novo
        assert c.chave(f, p) != k0
        rel_ent.Name = ant
        assert c.chave(f, p) == k0
    assert c.chave(f, {"protocolo": 1, "vista": {}, "elementos": [[w.id(), w.GlobalId]]}) != c.chave(f, {"protocolo": 1, "vista": {}, "elementos": [[w.id() + 9999, w.GlobalId]]})
    assert c.chave(f, {"protocolo": 1, "vista": {}, "elementos": [[999001, "G_AUS_1"]]}) != c.chave(f, {"protocolo": 1, "vista": {}, "elementos": [[999002, "G_AUS_2"]]})
