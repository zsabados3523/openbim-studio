# SPDX-License-Identifier: AGPL-3.0-or-later
"""Carregador de malhas do IFC (S03-T05 parte A; processo separado na S03-T08-B1). Python puro, sem Qt.

Especificação: docs/state/arquivo/lotes-1-a-28/LOTE_OPUS_4/resultado.md §1.2 e §1.3 e arquivo/lotes-1-a-28/LOTE_OPUS_6/resultado.md §2.2 D3. Quem abre o IFC e gera
os triângulos (`ifcopenshell.geom.iterator`, um iterador por bloco) é um processo filho (`processo_malhas.py`);
a thread interna só lê as mensagens, vigia o filho e entrega `LoteMalha` (só numpy) por uma fila limitada.
Durante a carga o pai não abre o arquivo (`manter_arquivo=True` abre depois que o filho terminou).
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field, replace

import numpy as np

try:
    from . import foto_arquivo
except ImportError:  # pragma: no cover  (módulo importado fora do pacote)
    import foto_arquivo

try:  # o formato vive fora do pacote (a S04 também o usa); `prototypes/` precisa estar no caminho
    from formato_malha import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
except ImportError:  # pragma: no cover  (módulo executado fora do pacote)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from formato_malha import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
log = logging.getLogger("openbim.viewport")
MAX_BYTES_LOTE = 8 * 1024 * 1024
CINZA = (204, 204, 204, 255)
ORANGE = (255, 140, 0, 255)  # caixa substituta (D4)
FATIA_S = 0.05
MOTIVO_SEM_GEOMETRIA = "o conversor não achou geometria nesta peça"
MOTIVO_CORTE = "esta carga já tinha peças lentas demais; a peça foi mostrada como caixa sem tentar de novo"


@dataclass(frozen=True)
class ResumoCarga:
    estado: str  # "concluido" | "cancelado" | "erro"
    erro: str | None
    produtos_total: int = 0
    produtos_com_malha: int = 0
    triangulos: int = 0
    vertices: int = 0
    lotes: int = 0
    sem_malha: list = field(default_factory=list)  # (id_step, guid, classe, motivo)
    tempos: dict = field(default_factory=dict)  # abrir_s, listar_s, geometria_s, total_s
    threads: int = 1
    tamanho_bloco: int = 0
    mensagens: list = field(default_factory=list)
    pico_filho_mb: float = 0.0  # maior pico de memória entre os processos filhos (informado por eles)
    simplificadas: list = field(default_factory=list)  # (id_step, guid, classe, nome, motivo, segundos): viraram caixa


class _Cancelado(Exception):
    pass


def _unitarias(n):
    c = np.linalg.norm(n, axis=1, keepdims=True)
    return np.where(c > 1e-12, n / np.where(c > 1e-12, c, 1.0), np.array([0.0, 0.0, 1.0]))


def produto_para_numpy(geo, paleta):
    """Geometria do iterador -> (pos float64 (n,3), normal float32 (n,3), cor uint8 (n,4), indices uint32 (3m,)) ou None."""
    # D2 (LOTE_OPUS_6 §2.2): vetores prontos do IfcOpenShell (int32 e float64) em vez de tuplas; ~17x mais rápido.
    faces = np.frombuffer(geo.faces_buffer, dtype=np.int32).astype(np.int64).reshape(-1, 3)
    if len(faces) == 0:
        return None
    pos = np.frombuffer(geo.verts_buffer, dtype=np.float64).reshape(-1, 3).copy()  # cópia: não depende do buffer do iterador
    normais = np.frombuffer(geo.normals_buffer, dtype=np.float64).reshape(-1, 3)
    mids = np.frombuffer(geo.material_ids_buffer, dtype=np.int32).astype(np.int64)
    k = len(paleta) - 1  # última linha = cinza
    tm = np.where((mids < 0) | (mids >= k), k, mids) if len(mids) == len(faces) else np.full(len(faces), k)
    if len(normais) != len(pos):  # sem normais: normal de cada face, vértices separados
        tri = pos[faces]
        nf = _unitarias(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]))
        return (tri.reshape(-1, 3), np.repeat(nf, 3, axis=0).astype(np.float32),
                paleta[np.repeat(tm, 3)], np.arange(3 * len(faces), dtype=np.uint32))
    normais = _unitarias(normais).astype(np.float32)
    if np.all(tm == tm[0]):
        return pos, normais, np.tile(paleta[tm[0]], (len(pos), 1)), faces.ravel().astype(np.uint32)
    p = len(paleta)  # vértice usado por cores diferentes é duplicado
    chave = (faces * p + tm[:, None]).ravel()
    uniq, inv = np.unique(chave, return_inverse=True)
    orig = uniq // p
    return pos[orig], normais[orig], paleta[uniq % p], inv.astype(np.uint32)


def paleta_da_peca(geo):
    linhas = []
    for m in geo.materials:
        try:
            d = m.diffuse
            alfa = 1.0 - float(m.transparency) if m.has_transparency() else 1.0
            rgba = [d.r(), d.g(), d.b(), alfa]
        except Exception:
            linhas.append(CINZA)
            continue
        linhas.append(tuple(int(x) for x in np.clip(np.rint(np.array(rgba) * 255.0), 0, 255)))
    linhas.append(CINZA)
    return np.array(linhas, dtype=np.uint8).reshape(-1, 4)


def montar_lote(indice, prods, desl, feitos, total):
    """prods: lista de (id_step, guid, pos64, normal, cor, indices) em ordem de id."""
    nv = sum(len(p[2]) for p in prods)
    verts = np.empty(nv, dtype=DTYPE_VERTICE)
    objs = np.empty(len(prods), dtype=DTYPE_OBJETO)
    partes_idx = []
    iv = ii = 0
    for j, (idp, guid, pos, nor, cor, idx) in enumerate(prods):
        n = len(pos)
        p32 = (pos - desl).astype(np.float32)  # subtrai em float64, depois converte
        verts["pos"][iv:iv + n] = p32
        verts["normal"][iv:iv + n] = nor
        verts["cor"][iv:iv + n] = cor
        partes_idx.append((idx + np.uint32(iv)).astype(np.uint32))
        objs[j] = (idp, guid.encode("ascii"), ii, len(idx), iv, n, p32.min(axis=0), p32.max(axis=0))
        iv, ii = iv + n, ii + len(idx)
    indices = np.concatenate(partes_idx).astype(np.uint32)
    for a in (verts, indices, objs):
        a.flags.writeable = False
    return LoteMalha(indice, verts, indices, objs, desl, feitos, total)


class CarregadorMalhas:
    # D1 (LOTE_OPUS_6 §2.2): a híbrida tenta a biblioteca rápida e cai na "opencascade" nos recortes de abertura.
    # Curiosidade: has_geometry_library() responde falso para esse nome, mas o iterador o aceita.
    def __init__(self, caminho, threads=None, tamanho_bloco=1000, fila_max=4,
                 excluir=("IfcFeatureElementSubtraction", "IfcSpace"),
                 biblioteca="hybrid-cgal-simple-opencascade", max_bytes_lote=MAX_BYTES_LOTE, manter_arquivo=False,
                 limite_peca_s=20.0, limite_abrir_s=600.0, max_pecas_condenadas=20, max_espera_s=120.0):
        self.caminho = str(caminho)
        self.biblioteca = str(biblioteca)
        self.max_bytes_lote = int(max_bytes_lote)
        self.manter_arquivo = bool(manter_arquivo)
        self.limite_peca_s = None if limite_peca_s is None else float(limite_peca_s)  # None desliga
        self.limite_abrir_s = None if limite_abrir_s is None else float(limite_abrir_s)
        # S04-T16: orçamento da carga (peças mostradas como caixa por lentidão ou queda; segundos gastos em esperas)
        self.max_pecas_condenadas = int(max_pecas_condenadas)
        self.max_espera_s = float(max_espera_s)
        # T08-D: no máximo 8 fios por padrão (cada fio a mais custa ~70 MB no filho e quase não ganha tempo)
        self.threads = int(threads) if threads else max(1, min(8, (os.cpu_count() or 2) - 1))
        self.tamanho_bloco = int(tamanho_bloco)
        self.excluir = tuple(excluir)
        self._fila = queue.Queue(maxsize=max(1, int(fila_max)))
        self._cancelar = threading.Event()
        self._pronto = threading.Event()  # resumo montado
        self._resumo = None
        self._entregue = False
        self._lock = threading.Lock()
        self._thread = None
        self._arquivo = None
        self._lotes_produzidos = 0
        self._descartados = 0
        self._fase = None  # última fase informada pelo filho
        self._produtos = {}  # id_step -> (guid, classe, nome, família), de `inicio`
        self._conv = 0  # mensagens "convertendo" do filho atual (qual bloco está em curso)
        self._feitos = set()  # ids avisados em `feitos` pelo filho atual
        self._atual = None  # peça em conversão no modo uma peça por vez

    # ---- interface pública ----
    @property
    def arquivo(self):
        return self._arquivo

    @property
    def lotes_produzidos(self):
        return self._lotes_produzidos

    def iniciar(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._trabalhar, name="carregador-malhas", daemon=True)
        self._thread.start()

    def cancelar(self):
        self._cancelar.set()

    def aguardar(self, timeout=None):
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def obter(self, timeout=0.0):
        fim = time.perf_counter() + (timeout or 0.0)
        while True:
            if self._cancelar.is_set():  # depois de cancelar() só o resumo sai
                self._esvaziar()
                if self._pronto.wait(max(0.0, fim - time.perf_counter())):
                    return self._entregar_resumo()
                return None
            restante = fim - time.perf_counter()
            try:  # nunca `timeout=None` (esperaria para sempre): sem tempo sobrando, só olha a fila
                return self._fila.get(timeout=min(FATIA_S, restante)) if restante > 0 else self._fila.get_nowait()
            except queue.Empty:
                pass
            if self._pronto.is_set() and self._fila.empty():
                return self._entregar_resumo()
            if time.perf_counter() >= fim:
                return None

    # ---- internos ----
    def _esvaziar(self):
        try:
            while True:
                self._fila.get_nowait()
                self._descartados += 1
        except queue.Empty:
            pass

    def _entregar_resumo(self):
        with self._lock:
            if self._entregue:
                return None
            self._entregue = True
            r = self._resumo
            if self._descartados and r.estado == "concluido":  # cancelar() jogou lotes fora: não é "concluido"
                r = replace(r, estado="cancelado",
                            mensagens=r.mensagens + [f"{self._descartados} lote(s) descartado(s) pelo cancelamento"])
            return r

    def _checar(self):
        if self._cancelar.is_set():
            raise _Cancelado()

    def _colocar(self, lote):
        while True:
            self._checar()
            try:
                self._fila.put(lote, timeout=FATIA_S)
                return
            except queue.Full:
                pass

    def _trabalhar(self):
        """Thread leitora e vigia: cria o filho (processo_malhas), lê as mensagens e alimenta a fila."""
        t0 = time.perf_counter()
        est = {"estado": "erro", "erro": None, "produtos_total": 0, "ids": set(), "tri": 0, "vert": 0,
               "lotes": 0, "sem": [], "t": {"abrir_s": 0.0, "listar_s": 0.0, "geometria_s": 0.0}, "msgs": [],
               "pico_filho": 0.0, "foto": None, "resolvidos": set(), "simp": [], "desl": None, "acusadas": 0, "espera": 0.0}
        try:
            est["foto"] = foto_arquivo.tirar(self.caminho, com_soma=self.manter_arquivo)  # antes de qualquer filho; a soma (lê o arquivo todo) só vale com manter_arquivo
            self._ler(est)
            est["estado"] = "concluido"
        except _Cancelado:
            est["estado"] = "cancelado"
        except BaseException as e:  # nenhuma exceção escapa da thread
            est["estado"], est["erro"] = "erro", f"{type(e).__name__}: {str(e) or 'erro desconhecido'}"
        try:
            est["t"]["total_s"] = time.perf_counter() - t0
            if est["estado"] == "concluido" and self.manter_arquivo:  # só depois que o filho terminou (picos não se somam)
                try:
                    import ifcopenshell
                    trocou = foto_arquivo.mudou(self.caminho, est["foto"], com_soma=True)
                    if trocou:
                        raise RuntimeError(trocou)
                    self._arquivo = ifcopenshell.open(self.caminho)
                except Exception as e:
                    est["msgs"].append(f"não foi possível manter o arquivo aberto: {e}")
            self._resumo = ResumoCarga(
                est["estado"], est["erro"], est["produtos_total"], len(est["ids"]), est["tri"], est["vert"],
                est["lotes"], est["sem"], est["t"], self.threads, self.tamanho_bloco, est["msgs"] + self._linhas_resumo(est["simp"]),
                est["pico_filho"], est["simp"])
        finally:  # o resumo existe ou não, quem espera nunca fica preso
            self._pronto.set()

    def _linhas_resumo(self, simp):
        cortadas = sum(1 for s in simp if s[4] == MOTIVO_CORTE)
        por_limite = sum(1 for s in simp if "limite" in s[4])
        linhas = []
        if por_limite:
            lim = f"{self.limite_peca_s:g}" if self.limite_peca_s is not None else "o limite"
            linhas.append(f"{por_limite} peça(s) foram mostradas como caixa porque passaram de {lim} s")
        if len(simp) - por_limite - cortadas:
            linhas.append(f"{len(simp) - por_limite - cortadas} peça(s) foram mostradas como caixa porque o conversor caiu nelas")
        if cortadas:
            linhas.append(f"{cortadas} peça(s) foram mostradas como caixa de uma vez porque esta carga já tinha peças lentas demais")
        return linhas

    # ---- leitura e vigia dos filhos (D3 e D4) ----
    def _ler(self, est):
        """Fase rápida (blocos, várias threads). Peça lenta ou queda do filho no bloco: se o orçamento da carga estourou, as
        pendentes viram caixa de uma vez; senão vem o modo isolado (1 thread, UM iterador para as pendentes) e, se ele também
        parar, o modo uma peça por vez (um iterador por peça; o filho avisa qual está em conversão). A peça em conversão quando
        esse filho para ou cai é a acusada: ela já estava sozinha no iterador, é a confirmação. Nada supõe a ordem de entrega
        do iterador. A acusada e toda peça ainda pendente do arquivo com o mesmo item mapeado viram caixa. Orçamento (acusadas
        confirmadas ou segundos de espera): conferido em toda falha do modo normal e, nos outros modos, só depois da 1ª acusada.
        Mais de 20 falhas seguidas sem peça nova resolvida: as pendentes viram caixa (erro só se não houver o que cortar)."""
        iso, modo, primeiro, seguidos, antes = set(), "normal", True, 0, 0
        while True:
            if primeiro:
                ids, isolado = None, False
            else:
                iso -= est["resolvidos"]
                if iso:
                    ids, isolado = sorted(iso), True
                else:
                    modo = "normal"
                    ids, isolado = [i for i in sorted(self._produtos) if i not in est["resolvidos"]], False
                    if not ids:
                        return
            falha = self._rodar(est, ids, isolado, isolado and modo == "peca")
            primeiro = False
            progresso, antes = len(est["resolvidos"]) > antes, len(est["resolvidos"])
            if falha is None:
                for i in (ids or []):  # rede de segurança da regra de ouro: o filho terminou e não entregou
                    if i not in est["resolvidos"]:
                        g, c, _n, _f = self._produtos[i]
                        est["sem"].append((i, g, c, "o conversor não devolveu a peça"))
                        est["resolvidos"].add(i)
                seguidos, antes = 0, len(est["resolvidos"])
                continue
            seguidos = 0 if progresso else seguidos + 1
            est["espera"] += falha["seg"]
            pend = [i for i in falha["bloco"] if i not in est["resolvidos"]]
            if not pend:  # o filho caiu depois de entregar tudo (S03-T08-G): nada a isolar
                continue
            if seguidos > 20:  # sem progresso: corta o bloco em vez de terminar em erro
                self._caixas(est, [(i, MOTIVO_CORTE, 0.0) for i in pend])
                seguidos, antes = 0, len(est["resolvidos"])
                continue
            if (not isolado or est["acusadas"] >= 1) and self._estourou(est):  # antes de acusar esta peça
                self._caixas(est, [(i, MOTIVO_CORTE, 0.0) for i in pend])
                seguidos, antes = 0, len(est["resolvidos"])
                continue
            if not isolado:
                iso, modo = set(pend), "iso"  # várias threads: não dá para saber qual peça travou
                continue
            if modo != "peca":
                modo = "peca"  # um iterador para várias peças: também não dá para saber; agora uma peça por iterador
                continue
            culpada = falha["atual"]
            if culpada not in pend:  # não dá para dizer qual peça travou (ou ela já foi resolvida): nova rodada
                continue
            est["acusadas"] += 1
            fam = self._produtos[culpada][3]
            irmas = [i for i in sorted(self._produtos) if i != culpada and i not in est["resolvidos"]
                     and fam is not None and self._produtos[i][3] == fam]  # o arquivo inteiro, não só o bloco
            lim = (f"passou do limite de {self.limite_peca_s:g} s" if falha["motivo"] == "limite"
                   else "o conversor caiu nesta peça" + _texto_saida(falha.get("codigo")))
            lote = [(culpada, lim, falha["seg"])] + [
                (i, "mesma peça-base de uma que passou do limite" if falha["motivo"] == "limite"
                 else "mesma peça-base de uma em que o conversor caiu", 0.0) for i in irmas]
            self._caixas(est, lote)
            seguidos, antes = 0, len(est["resolvidos"])

    def _estourou(self, est):
        """Orçamento da carga (S04-T16): peças acusadas e confirmadas (cópias não contam) ou segundos de espera acima do máximo."""
        return est["acusadas"] > self.max_pecas_condenadas or est["espera"] > self.max_espera_s

    def _rodar(self, est, ids, isolado, por_peca=False):
        """Um filho de conversão. Devolve None se terminou (`fim`); senão dict com motivo ("limite" ou "queda"),
        segundos de espera, produtos do bloco em curso e, no modo uma peça por vez, a peça em conversão ("atual")."""
        try:
            from . import processo_malhas
        except ImportError:  # pragma: no cover
            import processo_malhas
        params = {"caminho": self.caminho, "threads": 1 if isolado else self.threads, "tamanho_bloco": self.tamanho_bloco,
                  "excluir": self.excluir, "biblioteca": self.biblioteca, "max_bytes_lote": self.max_bytes_lote,
                  "ids": ids, "isolado": isolado, "desl": est["desl"], "por_peca": por_peca, "foto": est["foto"]}
        self._conv, self._feitos, self._fase, self._atual = 0, set(), None, None

        def limite():
            return self.limite_peca_s if self._fase == "convertendo" else self.limite_abrir_s

        r = self._executar(est, processo_malhas.entrada, params, lambda t, d: self._tratar(t, d, est), limite)
        if r is None:
            return None
        if self._fase != "convertendo":  # falha ao abrir/listar: não há como isolar peça
            raise RuntimeError(f"o conversor falhou ao abrir o arquivo ({r['motivo']}, {r['seg']:.0f} s"
                               f"{_texto_saida(r.get('codigo'))})")
        todos = ids if ids is not None else sorted(self._produtos)
        tb = self.tamanho_bloco if self.tamanho_bloco > 0 and not isolado else max(len(todos), 1)
        r["bloco"] = todos[max(self._conv - 1, 0) * tb:self._conv * tb]
        r["atual"] = self._atual
        return r

    def _executar(self, est, alvo, params, ao_receber, limite):
        """Cria o filho, lê as mensagens e vigia o tempo desde a última. `ao_receber` devolve True na última.
        Devolve None se terminou, ou {"motivo", "seg"} se estourou o limite ("limite") ou caiu ("queda")."""
        ctx = multiprocessing.get_context("spawn")  # também no Linux: igual nos dois sistemas, sem cópia com Qt ativo
        rx, tx = ctx.Pipe(duplex=False)  # um canal por filho; Queue seria corrompida ao matar o filho
        filho = ctx.Process(target=alvo, args=(tx, params), name="obim-malhas", daemon=True)
        try:
            self._checar()
            filho.start()
            tx.close()  # só o filho guarda a ponta de escrita: se ele morrer, o pai vê o fim do canal
            ultimo = time.perf_counter()
            while True:
                self._checar()
                if not rx.poll(FATIA_S):
                    lim = limite()
                    seg = time.perf_counter() - ultimo
                    if lim is not None and seg >= lim:
                        return {"motivo": "limite", "seg": seg}
                    continue
                try:
                    tipo, dados = rx.recv()
                except (EOFError, OSError):
                    filho.join(2)
                    codigo = filho.exitcode
                    log.warning("O processo de geometria caiu (código de saída %s) %.1f s depois da última mensagem",
                                codigo, time.perf_counter() - ultimo)
                    return {"motivo": "queda", "seg": time.perf_counter() - ultimo, "codigo": codigo}
                if ao_receber(tipo, dados):
                    return None
                ultimo = time.perf_counter()  # o tempo gasto na fila cheia (contrapressão) não conta contra o filho
        finally:
            if filho.is_alive() and filho.pid is not None:
                try:
                    try:
                        from . import processo_malhas as pm
                    except ImportError:  # pragma: no cover
                        import processo_malhas as pm
                    est["pico_filho"] = max(est["pico_filho"], pm.pico_memoria_mb(
                        filho.pid if sys.platform != "win32" else filho.sentinel))
                except Exception:
                    pass
            if filho.pid is not None:
                if filho.is_alive():
                    filho.kill()
                filho.join(2)
            for c in (rx, tx):
                try:
                    c.close()
                except OSError:
                    pass

    def _caixas(self, est, itens):
        """Peças [(id, motivo, segundos)] viram caixa laranja de 12 triângulos. Os pontos vêm de um filho sem a
        biblioteca de geometria (limite de 5 s); a peça que ele não entregar vai para `sem_malha` com o motivo."""
        try:
            from . import processo_malhas as pm
        except ImportError:  # pragma: no cover
            import processo_malhas as pm
        achados, falhas = {}, {}

        def receber(tipo, dados):
            if tipo == "fase":
                self._fase = dados
            elif tipo == "caixa":
                self._fase = "caixa"
                achados[dados[0]] = (np.asarray(dados[1], dtype=np.float64), np.asarray(dados[2], dtype=np.float64))
            elif tipo == "caixa_erro":
                falhas[dados[0]] = dados[1]
            elif tipo == "erro":
                raise RuntimeError(dados)
            return tipo == "fim"

        self._fase = None
        params = {"caminho": self.caminho, "ids": [i for i, _, _ in itens], "foto": est["foto"]}
        try:
            r = self._executar(est, pm.entrada_caixa, params, receber,
                               lambda: pm.LIMITE_CAIXA_S + 1.0 if self._fase == "caixa" else self.limite_abrir_s)
            if r is not None:
                log.warning("O processo da caixa substituta não terminou: %s%s", r["motivo"], _texto_saida(r.get("codigo")))
        except RuntimeError as exc:  # o que faltar vai para sem_malha; o motivo fica no registro
            log.warning("O processo da caixa substituta falhou: %s", exc)
        for i, motivo, seg in itens:
            g, c, n, _f = self._produtos[i]
            if i not in achados:  # regra de ouro: nada some; sem a posição certa não se desenha cubo na origem
                est["sem"].append((i, g, c, "não foi possível calcular a caixa da peça (" + falhas.get(
                    i, "o processo da caixa falhou ou passou do tempo") + ")"))
                est["resolvidos"].add(i)
                continue
            mn, mx = achados[i]
            if est["desl"] is None:
                est["desl"] = np.rint((mn + mx) / 2.0).astype(np.float64)
                est["desl"].flags.writeable = False
            lote = montar_lote(est["lotes"], [(i, g, *_malha_caixa(mn, mx))], est["desl"], len(est["resolvidos"]) + 1,
                                est["produtos_total"])
            est["simp"].append((i, g, c, n, motivo, float(seg)))
            self._contar_lote(est, lote)
            self._colocar(lote)

    def _contar_lote(self, est, lote):
        est["lotes"] += 1
        est["ids"].update(int(i) for i in lote.objetos["id_step"])
        est["resolvidos"].update(int(i) for i in lote.objetos["id_step"])
        est["tri"] += len(lote.indices) // 3
        est["vert"] += len(lote.vertices)
        self._lotes_produzidos += 1

    def _tratar(self, tipo, dados, est):
        """Aplica uma mensagem do filho de conversão. Devolve True na última (`fim`)."""
        if tipo == "fase":
            self._fase = dados
            self._conv += dados == "convertendo"
        elif tipo == "inicio":
            if not self._produtos:  # só o primeiro filho manda a tabela completa
                est["produtos_total"] = dados["total"]
                self._produtos = {i: (g, c, n, f) for i, g, c, n, f in dados["produtos"]}
        elif tipo == "lote":
            # cópia própria (o oráculo exige OWNDATA; o recebido aponta para o buffer do canal); a proteção do filho
            # se perde no canal, então o deslocamento também é copiado e protegido (§1.3 item 1)
            dados = replace(dados, vertices=dados.vertices.copy(), indices=dados.indices.copy(),
                            objetos=dados.objetos.copy(), deslocamento=np.array(dados.deslocamento, dtype=np.float64))
            for a in (dados.vertices, dados.indices, dados.objetos, dados.deslocamento):
                a.flags.writeable = False
            desl = dados.deslocamento
            if est["desl"] is None:
                est["desl"] = desl  # as reinicializações recebem o mesmo deslocamento
            self._contar_lote(est, dados)
            dados = replace(dados, indice_lote=est["lotes"] - 1, produtos_feitos=len(est["resolvidos"]),
                            produtos_total=est["produtos_total"])
            self._colocar(dados)
        elif tipo == "feitos":
            self._feitos.add(dados)
        elif tipo == "atual":  # modo uma peça por vez: a peça que o filho vai converter agora
            self._atual = dados
        elif tipo == "sem_malha":
            est["sem"].extend(dados)
            est["resolvidos"].update(d[0] for d in dados)
        elif tipo == "nota":  # o filho explica por que vai cair (ele não tem registro próprio)
            log.warning("Processo de geometria: %s", dados)
        elif tipo == "erro":
            raise RuntimeError(dados)
        elif tipo == "fim":
            for k, v in dados["tempos"].items():
                est["t"][k] = est["t"].get(k, 0.0) + v
            est["msgs"] = dados["mensagens"]
            est["pico_filho"] = max(est["pico_filho"], dados["pico_memoria_mb"])
            return True
        return False


def _texto_saida(codigo):
    """Sufixo com o código de saída do filho, para as mensagens de queda (vazio se não houver)."""
    return "" if codigo is None else f", código de saída {codigo}"


def _malha_caixa(mn, mx):
    """Caixa (mínimo, máximo) em metros -> (pos float64, normal, cor laranja, índices): 24 vértices, 12 triângulos."""
    lim = (mn, mx)
    pos, nor = [], []
    for a in range(3):
        b, c = (a + 1) % 3, (a + 2) % 3
        for s in (0, 1):
            quad = []
            for ub, uc in ((0, 0), (1, 0), (1, 1), (0, 1)):
                v = [0, 0, 0]
                v[a], v[b], v[c] = s, ub, uc
                quad.append(v)
            if s == 0:
                quad.reverse()  # normal para fora
            n = [0.0, 0.0, 0.0]
            n[a] = 1.0 if s else -1.0
            pos += [[lim[v[k]][k] for k in range(3)] for v in quad]
            nor += [n] * 4
    idx = np.array([[4 * q, 4 * q + 1, 4 * q + 2, 4 * q, 4 * q + 2, 4 * q + 3] for q in range(6)], dtype=np.uint32).ravel()
    return (np.array(pos, dtype=np.float64), np.array(nor, dtype=np.float32),
            np.tile(np.array(ORANGE, dtype=np.uint8), (24, 1)), idx)
