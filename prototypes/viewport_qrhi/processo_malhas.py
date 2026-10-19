# SPDX-License-Identifier: AGPL-3.0-or-later
"""Processo filho que converte o IFC em malhas (S03-T08-B1; arquivo/lotes-1-a-28/LOTE_OPUS_6/resultado.md §2.2 D3). Python puro, sem Qt.

O filho abre o arquivo, lista os produtos, converte com `ifcopenshell.geom.iterator` e manda mensagens
`(tipo, dados)` por um `Pipe` de mão única: `fase`, `bloco` e `bloco_fim` (memória do filho no início e no fim da conversão de cada bloco), `inicio`, `lote`, `feitos`, `atual`, `sem_malha`, `erro`, `fim`.
Quem lê e vigia é a thread do `CarregadorMalhas`. O filho nunca importa Qt.
Ganchos de teste (só valem se a variável existir): OBIM_TESTE_PECA_LENTA="<guid>=<s>[,<guid>=<s>]" e
OBIM_TESTE_MATAR_FILHO="<guid>" (o filho sai com código 3 nessa peça) e OBIM_TESTE_FALHAR_CAIXA="<guid>" (o filho da
caixa falha só nessa peça) e OBIM_TESTE_MATAR_NO_FIM=1 (o filho em modo isolado sai com código 3 depois do último
`lote` e antes do `fim`) e OBIM_TESTE_CRESCER_MB="<guid>=<mb>[,<guid>=<mb>]" (a peça aloca e escreve essa memória até o fim do bloco).
Modos: normal (blocos, várias threads), isolado (`isolado`: 1 thread, UM iterador para os ids pedidos) e uma peça por vez
(`isolado` e `por_peca`: um iterador por peça; antes de cada peça o filho manda `atual` com o id dela, e a peça em conversão
quando o filho para ou cai é a acusada).
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

try:
    from .carregador import DTYPE_VERTICE, MOTIVO_SEM_GEOMETRIA, montar_lote, paleta_da_peca, produto_para_numpy
except ImportError:  # pragma: no cover  (módulo importado fora do pacote)
    from carregador import DTYPE_VERTICE, MOTIVO_SEM_GEOMETRIA, montar_lote, paleta_da_peca, produto_para_numpy


def pico_memoria_mb(ident=None, atual=False) -> float:
    """Pico de memória de um processo, sem psutil. Sem argumento: o próprio processo.
    Com `ident`: pid no Linux; no Windows, o identificador (handle) do processo, p.ex. `Process.sentinel`.
    Com `atual=True` (T29c): a memória residente de agora, não o pico (Linux VmRSS; Windows WorkingSetSize)."""
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
        return (pmc.WorkingSetSize if atual else pmc.PeakWorkingSetSize) / 2**20
    if sys.platform.startswith("linux") and (ident is not None or atual):  # VmHWM (pico) ou VmRSS (atual), em kB
        with open(f"/proc/{'self' if ident is None else int(ident)}/status") as a:
            for linha in a:
                if linha.startswith("VmRSS:" if atual else "VmHWM:"):
                    return int(linha.split()[1]) / 1024.0
        return 0.0
    if ident is not None:  # macOS e outros: `ps` existe no sistema; dá o conjunto residente atual (não o pico), em kB
        import subprocess
        saida = subprocess.run(["ps", "-o", "rss=", "-p", str(int(ident))], capture_output=True, text=True, timeout=5).stdout
        return int(saida.split()[0]) / 1024.0 if saida.split() else 0.0
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (2**20 if sys.platform == "darwin" else 1024.0)  # bytes no macOS, KB no Linux


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


_RETIDO = []  # memória do gancho OBIM_TESTE_CRESCER_MB: guardada até o fim do bloco


def _crescer():
    """OBIM_TESTE_CRESCER_MB="<guid>=<mb>[,<guid>=<mb>...]": ao converter a peça, o filho aloca e escreve essa memória (T29c)."""
    saida = {}
    for par in os.environ.get("OBIM_TESTE_CRESCER_MB", "").split(","):
        if "=" in par:
            g, mb = par.rsplit("=", 1)
            saida[g.strip()] = int(float(mb))
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
        enviar("erro", f"{type(e).__name__}: {str(e) or 'erro desconhecido'}")


def _conferir_foto(params):
    """Para a carga se o arquivo não é mais o da foto tirada pelo pai (F0-RG-04). Confere só tamanho e data (barato)."""
    try:
        from . import foto_arquivo
    except ImportError:  # pragma: no cover
        import foto_arquivo
    motivo = foto_arquivo.mudou(params["caminho"], params.get("foto"))
    if motivo:
        raise RuntimeError(motivo)


def _converter(enviar, params):
    import ifcopenshell
    import ifcopenshell.geom

    lentas, matar = _lentas(), os.environ.get("OBIM_TESTE_MATAR_FILHO")
    crescer = _crescer()
    tempos = {"abrir_s": 0.0, "listar_s": 0.0, "geometria_s": 0.0}
    enviar("fase", "abrindo")
    _conferir_foto(params)
    t = time.perf_counter()
    arq = ifcopenshell.open(params["caminho"])
    tempos["abrir_s"] = time.perf_counter() - t
    _conferir_foto(params)  # mudou enquanto lia? então o que foi lido pode misturar duas versões
    enviar("fase", "listando")
    t = time.perf_counter()
    excluir = tuple(params["excluir"])
    produtos = [p for p in arq.by_type("IfcProduct")
                if p.Representation is not None and not any(p.is_a(c) for c in excluir)]
    produtos.sort(key=lambda p: p.id())
    if params.get("ids") is not None:  # reinício: só os produtos pedidos (o pai já tem a tabela completa)
        pedidos = set(params["ids"])
        produtos = [p for p in produtos if p.id() in pedidos]
    total = len(produtos)
    tabela = [(p.id(), p.GlobalId, p.is_a(), p.Name, _familia(p)) for p in produtos] if params.get("ids") is None else []
    enviar("inicio", {"total": total, "produtos": tabela})
    tempos["listar_s"] = time.perf_counter() - t
    cfg = ifcopenshell.geom.settings()
    cfg.set("use-world-coords", True)
    cfg.set("weld-vertices", False)
    isolado = bool(params.get("isolado"))  # modo isolado: um único iterador (1 thread), cada peça entregue na hora
    tb = params["tamanho_bloco"] if params["tamanho_bloco"] > 0 and not isolado else max(total, 1)
    estado = {"desl": params.get("desl"), "indice": 0}  # o pai passa o deslocamento do primeiro lote às reinicializações

    def emitir(prods, feitos):
        for grupo in _agrupar(prods, params["max_bytes_lote"]):
            if estado["desl"] is None:  # centro da caixa do primeiro lote, em float64, arredondado ao metro
                mn = np.min([p[2].min(axis=0) for p in grupo], axis=0)
                mx = np.max([p[2].max(axis=0) for p in grupo], axis=0)
                estado["desl"] = np.rint((mn + mx) / 2.0).astype(np.float64)
                estado["desl"].flags.writeable = False
            enviar("lote", montar_lote(estado["indice"], grupo, estado["desl"], feitos, total))
            estado["indice"] += 1

    feitos = 0
    t = time.perf_counter()
    if isolado:  # UM iterador para todas as peças pedidas (S04-T16), ou um por peça (`por_peca`); cada peça sai assim que fica pronta
        enviar("fase", "convertendo")
        buffer, t_buf = [], 0.0

        def soltar():
            nonlocal buffer
            if buffer:
                emitir(buffer, 0)
                buffer = []

        def juntar(q):  # agrupa por tempo (0,2 s) para não criar um lote por peça
            nonlocal t_buf
            if not buffer:
                t_buf = time.perf_counter()
            buffer.append(q)
            if time.perf_counter() - t_buf >= 0.2:
                soltar()

        if params.get("por_peca"):
            sem = []
            for p in produtos:
                enviar("atual", p.id())  # antes de criar o iterador: a conversão da peça começa em initialize()
                sem.extend(_bloco(ifcopenshell, cfg, arq, [p], params, enviar, lentas, matar, juntar, crescer)[1])
        else:
            _, sem = _bloco(ifcopenshell, cfg, arq, produtos, params, enviar, lentas, matar, juntar, crescer)
        soltar()
        if sem:
            enviar("sem_malha", sem)
        if os.environ.get("OBIM_TESTE_MATAR_NO_FIM"):  # gancho de teste (S03-T08-G): cai depois do último lote
            os._exit(3)
    else:
        for ini in range(0, total, tb):
            bloco = produtos[ini:ini + tb]
            _RETIDO.clear()  # fim do bloco anterior: a memória do gancho de crescimento volta ao sistema
            enviar("fase", "convertendo")  # antes de criar o iterador: a primeira peça é convertida em initialize()
            enviar("bloco", {"rss_mb": pico_memoria_mb(atual=True)})  # memória de partida do bloco (regra R-A, T29c)
            prods, sem = _bloco(ifcopenshell, cfg, arq, bloco, params, enviar, lentas, matar, None, crescer)
            enviar("bloco_fim", {"rss_mb": pico_memoria_mb(atual=True)})  # o pai pode estar atrasado na fila: a medida vem do filho
            feitos += len(bloco)
            if sem:
                enviar("sem_malha", sem)
            emitir(prods, feitos)
    tempos["geometria_s"] = time.perf_counter() - t
    try:
        mensagens = str(ifcopenshell.get_log()).splitlines()[-50:]
    except Exception:
        mensagens = []
    enviar("fim", {"tempos": tempos, "pico_memoria_mb": pico_memoria_mb(), "mensagens": mensagens})


def _bloco(ifcopenshell, cfg, arq, bloco, params, enviar, lentas, matar, entregar=None, crescer=None):
    """Converte os produtos de um bloco com UM iterador. Devolve (lista ordenada por id, lista de sem malha).
    Com `entregar` (modo isolado) cada peça sai logo depois do aviso `feitos` e a lista devolvida fica vazia."""
    porid = {p.id(): p for p in bloco}
    achados, sem = {}, []

    def falhou(ids, motivo):
        sem.extend((i, porid[i].GlobalId, porid[i].is_a(), motivo) for i in ids)

    try:
        it = ifcopenshell.geom.iterator(cfg, arq, params["threads"], include=bloco, geometry_library=params["biblioteca"])
        try:
            if not it.initialize():
                log = " | ".join(str(ifcopenshell.get_log()).splitlines()[-3:])
                falhou(list(porid), MOTIVO_SEM_GEOMETRIA if entregar else
                       "initialize() falhou" + (f": {log}" if log else ""))
                return [], sem
            while True:
                s = it.get()
                r = produto_para_numpy(s.geometry, paleta_da_peca(s.geometry))
                if r is not None and s.id in porid:
                    achados[s.id] = None if entregar else r
                guid = porid[s.id].GlobalId if s.id in porid else None
                if guid is not None and guid == matar:
                    os._exit(3)
                if guid in lentas:
                    time.sleep(lentas[guid])
                if crescer and guid in crescer:  # gancho de teste (T29c): escreve de verdade, senão a memória não é residente
                    _RETIDO.append(np.ones(crescer[guid] * 2**20, dtype=np.uint8))
                if guid is not None:
                    enviar("feitos", s.id)
                    if entregar and r is not None and s.id in porid:
                        entregar((s.id, guid, *r))
                if not it.next():
                    break
        finally:
            del it
    except Exception as e:
        if entregar and len(porid) > 1:  # não dá para dizer qual peça deu erro: cai, e o pai confirma uma a uma
            enviar("nota", f"erro em um bloco de {len(porid)} peças ({type(e).__name__}: {e}); o filho cai para o pai testar uma a uma")
            os._exit(3)
        falhou([i for i in porid if i not in achados], f"o conversor falhou nesta peça: {type(e).__name__}: {e}")
    else:
        falhou([i for i in porid if i not in achados], "o conversor não devolveu geometria para esta peça")
    return [] if entregar else [(i, porid[i].GlobalId, *achados[i]) for i in sorted(achados)], sem


# ---- caixa substituta (D4): filho sem a biblioteca de geometria, só leitura de pontos do IFC ----
LIMITE_CAIXA_S = 5.0
CUBO_M = 0.5


def _pontos_item(util_p, item, m, saida, t_fim):
    """Pontos (arquivo) de um item levados pela matriz `m`. Só malhas, itens mapeados e extrusões simples."""
    if time.perf_counter() > t_fim:
        raise TimeoutError("limite da caixa")
    if item.is_a("IfcMappedItem"):
        mm = m @ util_p.get_mappeditem_transformation(item)
        for sub in item.MappingSource.MappedRepresentation.Items:
            _pontos_item(util_p, sub, mm, saida, t_fim)
    elif item.is_a("IfcPolygonalFaceSet") or item.is_a("IfcTriangulatedFaceSet"):
        p = np.array(item.Coordinates.CoordList, dtype=np.float64).reshape(-1, 3)
        saida.append(p @ m[:3, :3].T + m[:3, 3])
    elif item.is_a("IfcExtrudedAreaSolid"):
        perfil = item.SweptArea
        if perfil.is_a("IfcRectangleProfileDef"):
            x, y = perfil.XDim / 2.0, perfil.YDim / 2.0
            p2 = [(-x, -y), (x, -y), (x, y), (-x, y)]
        elif perfil.is_a("IfcArbitraryClosedProfileDef") and perfil.OuterCurve.is_a("IfcPolyline"):
            p2 = [tuple(q.Coordinates)[:2] for q in perfil.OuterCurve.Points]
        elif perfil.is_a("IfcArbitraryClosedProfileDef") and perfil.OuterCurve.is_a("IfcIndexedPolyCurve"):
            curva = perfil.OuterCurve  # só trechos retos: com arco, os pontos da lista não limitam a curva
            if any(not sg.is_a("IfcLineIndex") for sg in (curva.Segments or ())):
                raise ValueError("curva com arco")
            p2 = [tuple(q)[:2] for q in curva.Points.CoordList]
        else:
            raise ValueError("perfil não suportado")
        if perfil.is_a("IfcParameterizedProfileDef") and perfil.Position is not None:  # posição própria do perfil (2D)
            q = util_p.get_axis2placement(perfil.Position)
            p2 = [tuple((q @ np.array([a, b, 0.0, 1.0]))[:2]) for a, b in p2]
        d = np.array(item.ExtrudedDirection.DirectionRatios, dtype=np.float64)
        d = d / np.linalg.norm(d) * item.Depth
        base = np.array([(a, b, 0.0) for a, b in p2], dtype=np.float64)
        mm = m @ (util_p.get_axis2placement(item.Position) if item.Position is not None else np.eye(4))
        for p in (base, base + d):
            saida.append(p @ mm[:3, :3].T + mm[:3, 3])
    else:
        raise ValueError(f"item {item.is_a()} sem pontos")


def _caixa_produto(util_p, prod, escala):
    """(mínimo, máximo) em metros, no mundo. Pontos da representação; falha ou estouro ao ler os pontos: cubo de 0,5 m na posição da peça; posição ilegível: a peça falha (vai para `sem_malha`)."""
    # S03-T08-G: posição ilegível = a peça falha (vai para `sem_malha`); nunca uma caixa em posição zero
    m = util_p.get_local_placement(prod.ObjectPlacement) if prod.ObjectPlacement is not None else np.eye(4)
    try:
        t_fim = time.perf_counter() + LIMITE_CAIXA_S
        pts = []
        reps = prod.Representation.Representations
        for rep in [r for r in reps if r.RepresentationIdentifier == "Body"] or list(reps):
            for item in rep.Items:
                _pontos_item(util_p, item, m, pts, t_fim)
        p = np.vstack(pts) * escala
        if not len(p) or not np.all(np.isfinite(p)):
            raise ValueError("sem pontos")
        return p.min(axis=0), p.max(axis=0), "pontos"
    except Exception:
        c = np.asarray(m[:3, 3], dtype=np.float64) * escala
        return c - CUBO_M / 2.0, c + CUBO_M / 2.0, "cubo"


def entrada_caixa(tx, params):
    """Filho da caixa substituta: manda `("caixa", (id, mínimo, máximo, método))` para cada id pedido."""
    enviar = _Enviador(tx)
    try:
        import ifcopenshell
        import ifcopenshell.util.placement as util_p
        import ifcopenshell.util.unit as util_u
        enviar("fase", "abrindo")
        _conferir_foto(params)
        arq = ifcopenshell.open(params["caminho"])
        _conferir_foto(params)
        escala = util_u.calculate_unit_scale(arq)  # unidade do arquivo -> metros
        falhar = os.environ.get("OBIM_TESTE_FALHAR_CAIXA")
        for i in params["ids"]:
            try:
                prod = arq.by_id(i)
                if falhar and prod.GlobalId == falhar:
                    raise RuntimeError("falha provocada pelo teste")
                mn, mx, metodo = _caixa_produto(util_p, prod, escala)
            except Exception as e:  # só esta peça falha; as outras seguem
                enviar("caixa_erro", (i, f"{type(e).__name__}: {e}"))
                continue
            enviar("caixa", (i, mn, mx, metodo))
        enviar("fim", None)
    except BaseException as e:
        enviar("erro", f"{type(e).__name__}: {str(e) or 'erro desconhecido'}")
