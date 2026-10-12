# SPDX-License-Identifier: AGPL-3.0-or-later
"""Processo filho que converte o IFC em malhas (S03-T08-B1; LOTE_OPUS_6.md §2.2 D3). Python puro, sem Qt.

O filho abre o arquivo, lista os produtos, converte com `ifcopenshell.geom.iterator` e manda mensagens
`(tipo, dados)` por um `Pipe` de mão única: `fase`, `inicio`, `lote`, `feitos`, `sem_malha`, `erro`, `fim`.
Quem lê e vigia é a thread do `CarregadorMalhas`. O filho nunca importa Qt.
Ganchos de teste (só valem se a variável existir): OBIM_TESTE_PECA_LENTA="<guid>=<s>[,<guid>=<s>]" e
OBIM_TESTE_MATAR_FILHO="<guid>" (o filho sai com código 3 nessa peça).
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

try:
    from .carregador import DTYPE_VERTICE, _montar_lote, _paleta, _produto_para_numpy
except ImportError:  # pragma: no cover  (módulo importado fora do pacote)
    from carregador import DTYPE_VERTICE, _montar_lote, _paleta, _produto_para_numpy


def pico_memoria_mb(ident=None) -> float:
    """Pico de memória de um processo, sem psutil. Sem argumento: o próprio processo.
    Com `ident`: pid no Linux; no Windows, o identificador (handle) do processo, p.ex. `Process.sentinel`."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                 "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

        pmc = PMC()
        pmc.cb = ctypes.sizeof(pmc)
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.GetCurrentProcess.argtypes = []
        f = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo  # B-2: tipos declarados (pseudo-handle -1)
        f.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        f.restype = wintypes.BOOL
        if not f(k.GetCurrentProcess() if ident is None else wintypes.HANDLE(ident), ctypes.byref(pmc), pmc.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return pmc.PeakWorkingSetSize / 2**20
    if ident is not None:  # Linux: VmHWM (pico do conjunto residente) em kB
        with open(f"/proc/{int(ident)}/status") as a:
            for linha in a:
                if linha.startswith("VmHWM:"):
                    return int(linha.split()[1]) / 1024.0
        return 0.0
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # KB no Linux


def _dividir(p, max_bytes):
    """Peça cujos vértices passam de `max_bytes`: vários pedaços (mesmo id), cada um com no máximo `max_bytes`."""
    idp, guid, pos, nor, cor, idx = p
    if len(pos) * DTYPE_VERTICE.itemsize <= max_bytes:
        return [p]
    por_pedaco = max(1, max_bytes // DTYPE_VERTICE.itemsize // 3)  # triângulos; pior caso: 3 vértices cada
    tri = idx.reshape(-1, 3)
    saida = []
    for a in range(0, len(tri), por_pedaco):
        uniq, inv = np.unique(tri[a:a + por_pedaco], return_inverse=True)
        saida.append((idp, guid, pos[uniq], nor[uniq], cor[uniq], inv.astype(np.uint32).ravel()))
    return saida


def _agrupar(prods, max_bytes):
    """Parte a lista em grupos de no máximo `max_bytes` de vértices (peça maior que isso é dividida antes)."""
    grupos, atual, bytes_ = [], [], 0
    for q in prods:
        for p in _dividir(q, max_bytes):
            b = len(p[2]) * DTYPE_VERTICE.itemsize
            if atual and bytes_ + b > max_bytes:
                grupos.append(atual)
                atual, bytes_ = [], 0
            atual.append(p)
            bytes_ += b
    if atual:
        grupos.append(atual)
    return grupos


def _familia(p):
    """Id do item mapeado (representação-fonte) usado pelo produto, ou None."""
    try:
        for rep in p.Representation.Representations:
            for item in rep.Items:
                if item.is_a("IfcMappedItem"):
                    return item.MappingSource.id()
    except Exception:
        pass
    return None


def _lentas():
    saida = {}
    for par in os.environ.get("OBIM_TESTE_PECA_LENTA", "").split(","):
        if "=" in par:
            g, s = par.rsplit("=", 1)
            saida[g.strip()] = float(s)
    return saida


class _Enviador:
    def __init__(self, tx):
        self.tx = tx

    def __call__(self, tipo, dados=None):
        try:
            self.tx.send((tipo, dados))
        except (OSError, EOFError, ValueError):  # canal quebrado: o pai se foi, o filho sai
            os._exit(4)


def entrada(tx, params):
    """Ponto de entrada do filho (nível do módulo, exigido pelo "spawn")."""
    enviar = _Enviador(tx)
    try:
        import locale
        if locale.localeconv()["decimal_point"] != ".":
            locale.setlocale(locale.LC_NUMERIC, "C")
        if locale.localeconv()["decimal_point"] != ".":
            raise RuntimeError("o separador decimal do processo de conversão não é o ponto")
        _converter(enviar, params)
    except BaseException as e:  # nada escapa sem aviso
        enviar("erro", f"{type(e).__name__}: {e}" or "erro desconhecido")


def _converter(enviar, params):
    import ifcopenshell
    import ifcopenshell.geom

    lentas, matar = _lentas(), os.environ.get("OBIM_TESTE_MATAR_FILHO")
    tempos = {"abrir_s": 0.0, "listar_s": 0.0, "geometria_s": 0.0}
    enviar("fase", "abrindo")
    t = time.perf_counter()
    arq = ifcopenshell.open(params["caminho"])
    tempos["abrir_s"] = time.perf_counter() - t
    enviar("fase", "listando")
    t = time.perf_counter()
    excluir = tuple(params["excluir"])
    produtos = [p for p in arq.by_type("IfcProduct")
                if p.Representation is not None and not any(p.is_a(c) for c in excluir)]
    produtos.sort(key=lambda p: p.id())
    total = len(produtos)
    enviar("inicio", {"total": total, "produtos": [(p.id(), p.GlobalId, p.is_a(), p.Name, _familia(p)) for p in produtos]})
    tempos["listar_s"] = time.perf_counter() - t
    cfg = ifcopenshell.geom.settings()
    cfg.set("use-world-coords", True)
    cfg.set("weld-vertices", False)
    tb = params["tamanho_bloco"] if params["tamanho_bloco"] > 0 else max(total, 1)
    desl, feitos, indice = None, 0, 0
    t = time.perf_counter()
    for ini in range(0, total, tb):
        bloco = produtos[ini:ini + tb]
        enviar("fase", "convertendo")
        prods, sem = _bloco(ifcopenshell, cfg, arq, bloco, params, enviar, lentas, matar)
        feitos += len(bloco)
        if sem:
            enviar("sem_malha", sem)
        for grupo in _agrupar(prods, params["max_bytes_lote"]):
            if desl is None:  # centro da caixa do primeiro lote, em float64, arredondado ao metro
                mn = np.min([p[2].min(axis=0) for p in grupo], axis=0)
                mx = np.max([p[2].max(axis=0) for p in grupo], axis=0)
                desl = np.rint((mn + mx) / 2.0).astype(np.float64)
                desl.flags.writeable = False
            enviar("lote", _montar_lote(indice, grupo, desl, feitos, total))
            indice += 1
    tempos["geometria_s"] = time.perf_counter() - t
    try:
        mensagens = str(ifcopenshell.get_log()).splitlines()[-50:]
    except Exception:
        mensagens = []
    enviar("fim", {"tempos": tempos, "pico_memoria_mb": pico_memoria_mb(), "mensagens": mensagens})


def _bloco(ifcopenshell, cfg, arq, bloco, params, enviar, lentas, matar):
    """Converte os produtos de um bloco. Devolve (lista ordenada por id, lista de sem malha)."""
    porid = {p.id(): p for p in bloco}
    achados, sem = {}, []

    def falhou(ids, motivo):
        sem.extend((i, porid[i].GlobalId, porid[i].is_a(), motivo) for i in ids)

    try:
        it = ifcopenshell.geom.iterator(cfg, arq, params["threads"], include=bloco, geometry_library=params["biblioteca"])
        try:
            if not it.initialize():
                log = " | ".join(str(ifcopenshell.get_log()).splitlines()[-3:])
                falhou(list(porid), "initialize() falhou" + (f": {log}" if log else ""))
                return [], sem
            while True:
                s = it.get()
                r = _produto_para_numpy(s.geometry, _paleta(s.geometry))
                if r is not None and s.id in porid:
                    achados[s.id] = r
                guid = porid[s.id].GlobalId if s.id in porid else None
                if guid is not None and guid == matar:
                    os._exit(3)
                if guid in lentas:
                    time.sleep(lentas[guid])
                if guid is not None:
                    enviar("feitos", s.id)
                if not it.next():
                    break
        finally:
            del it
    except Exception as e:
        falhou([i for i in porid if i not in achados], f"erro no iterador: {type(e).__name__}: {e}")
    else:
        falhou([i for i in porid if i not in achados], "o iterador não devolveu geometria")
    return [(i, porid[i].GlobalId, *achados[i]) for i in sorted(achados)], sem
