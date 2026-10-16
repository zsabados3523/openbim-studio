# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fluxo A da F0-S04-T11: comandos sobre o IFC (`ifcopenshell.api`) e janela PySide6 com a viewport do `obimcore`.
Contrato em CONTRATO.md (LOTE_OPUS_9 §1.1, §1.4 regras 1 a 8, §2, §4 etapa 3). Medidas sempre em metros; nomes em português.
Uma trava do modelo (regra 7) vai da abertura da transação até o retorno de `Cena.atualizar`; leitores de outras threads só leem sem esperar."""
import json
import locale
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element as E
import ifcopenshell.util.placement as P
import ifcopenshell.util.representation as R
import ifcopenshell.util.unit as U
import numpy as np

api = ifcopenshell.api.run
FOGO = "Pset_WallCommon.FireRating"
TRANSACAO = {"criar_tipo", "criar_parede", "criar_paredes_lote", "editar_propriedades", "mudar_comprimento", "mover", "apagar"}
CAMERA = {"orbitar": ("orbitar", "dx dy"), "camera_mover": ("mover", "dx dy"), "aproximar": ("aproximar", "fator"), "enquadrar": ("enquadrar", ""),
          "animar_orbita": ("animar_orbita", "graus_por_s"), "parar_animacao": ("parar_animacao", "")}
LIVRES = {"selecionar", "camera", "esperar", *CAMERA}  # sem trava e sem transação
BLOCO = 500  # produtos por `malhas` na abertura


def _modelo_novo():
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    cadeia = [api("root.create_entity", f, ifc_class=c, name=n) for c, n in (("IfcProject", "Projeto"), ("IfcSite", "Terreno"), ("IfcBuilding", "Edificio"), ("IfcBuildingStorey", "Pavimento 1"))]
    api("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})  # SI: metro
    _contextos(f)
    for pai, filho in zip(cadeia, cadeia[1:]):
        api("aggregate.assign_object", f, products=[filho], relating_object=pai)
    return f


def _contextos(f):  # (Body, Axis); cria o que faltar (dentro da transação aberta, se houver)
    modelo = R.get_context(f, "Model") or api("context.add_context", f, context_type="Model")
    plano = R.get_context(f, "Plan") or api("context.add_context", f, context_type="Plan")
    corpo = R.get_context(f, "Model", "Body", "MODEL_VIEW") or api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=modelo)
    eixo = R.get_context(f, "Plan", "Axis", "GRAPH_VIEW") or api("context.add_context", f, context_type="Plan", context_identifier="Axis", target_view="GRAPH_VIEW", parent=plano)
    return corpo, eixo


class ModeloOcupado(RuntimeError):
    """Outro escritor está no meio de um comando (trava do modelo ocupada)."""


class FluxoA:
    def __init__(self, caminho_ifc=None, janela=True, saida=None):
        self.saida = Path(saida) if saida else Path(tempfile.mkdtemp(prefix="fluxo_a_"))
        self.saida.mkdir(parents=True, exist_ok=True)
        self.caminho_ifc = None if caminho_ifc is None else str(caminho_ifc)
        self.ifc = ifcopenshell.open(self.caminho_ifc) if self.caminho_ifc else _modelo_novo()
        self.esc = U.calculate_unit_scale(self.ifc)  # tamanho da unidade do projeto em metros (a API recebe metros; camadas e deslocamentos convertemos aqui)
        self.ifc.set_history_size(100000)  # o padrão (64 desfazeres, medido) não cobre o roteiro R (~600 transações)
        self.trava, self.historico, self._refazer = threading.Lock(), [], []
        self.ultimo, self.sequencias, self._cache, self._passos, self._painel, self._g = {"criados": [], "alterados": [], "apagados": [], "geometria": []}, [], {}, {}, "(nada selecionado)", 0
        self.cena = self.janela_principal = self._ponte = self._app = self._rhi = self.selecionado = self._ult_guid = self._arquivo_ifc = None
        self._tam = (640, 480)  # tamanho lógico do contêiner, guardado pela thread da janela (as outras threads nunca chamam `_cont`)
        self._t_cam = 0.0  # instante (relógio do núcleo) do último comando de câmera, tomado depois de a Cena voltar; `selecionar` espera 2 quadros depois dele
        self._desl = None  # deslocamento da cena (float64, metros): o centro da caixa do 1o lote com geometria, igual para a sessão toda (RG-07)
        self._relogio = lambda: time.perf_counter() * 1000  # sem janela; com janela, o relógio do núcleo (o mesmo de Cena.relogio())
        if janela:
            self._criar_janela()

    def _criar_janela(self):
        import obimcore
        import shiboken6
        from openbim_app.localidade import criar_aplicacao
        from PySide6.QtCore import QObject, Qt, Signal
        from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QWidget

        class Ponte(QObject):  # painel atualizado de outra thread: só por sinal (fila do Qt)
            texto = Signal(str)

        self._app = criar_aplicacao(sys.argv[:1])
        locale.setlocale(locale.LC_NUMERIC, "C")
        self._relogio = obimcore.agora
        self._rhi = os.environ.get("RHI", "d3d11" if sys.platform == "win32" else "gl")
        self.cena = obimcore.Cena(self._rhi != "d3d11")
        self.janela_principal, centro = QMainWindow(), QWidget()
        lay, self._cont, self._rotulo, self._ponte = QHBoxLayout(centro), shiboken6.wrapInstance(self.cena.viewport_ptr(), QWidget), QLabel(self._painel), Ponte()
        self._cont.setMinimumSize(640, 480)
        self._rotulo.setMinimumWidth(260)
        self._rotulo.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self._cont, 1)
        lay.addWidget(self._rotulo)
        self._ponte.texto.connect(self._rotulo.setText)
        self.janela_principal.setCentralWidget(centro)
        self.cena.iniciar()
        self.janela_principal.show()
        if not self._bombear(lambda: len(self.cena.relogio()) > 0, 10000):
            raise RuntimeError("a viewport não apresentou o primeiro quadro em 10 s")

    def _bombear(self, cond=None, ms=0):  # processa eventos da janela (só na thread dela); com `cond`, espera até ela valer
        gui, fim = self._na_janela(), time.perf_counter() + ms / 1000
        while True:
            if gui:
                self._app.processEvents()
                self._tam = (self._cont.width(), self._cont.height())
            if cond is None or cond():
                return True
            if time.perf_counter() >= fim:
                return False
            time.sleep(0.0005)

    def _na_janela(self):  # esta é a thread da janela (a principal, com janela)?
        return self._app is not None and threading.current_thread() is threading.main_thread()

    def fechar(self):
        if self.cena is not None:
            self.cena.parar()
            self.janela_principal.close()

    def _ler(self, e, chave):
        v = E.get_pset(e, *chave.split(".", 1)) if "." in chave else getattr(e, chave, None)
        return None if v is None else str(v)

    def _sem_esperar(self, fn):  # roda `fn` só se a trava estiver livre (nunca espera); trava ocupada: devolve None
        if self.trava.acquire(blocking=False):
            try:
                return fn()
            finally:
                self.trava.release()

    def ler_propriedade(self, guid, chave):  # trava ocupada: o último valor mostrado, sem tocar no ifc
        def ler():
            e = self._produto(guid, False)
            self._cache[(guid, chave)] = None if e is None else self._ler(e, chave)
        self._sem_esperar(ler)
        return self._cache.get((guid, chave))

    def _texto_painel(self):  # quem chama segura a trava
        if (e := self._produto(self.selecionado, False)) is None:
            return "(nada selecionado)"
        return f"{e.is_a()}\nNome: {self._ler(e, 'Name')}\nGlobalId: {self.selecionado}\nResistência ao fogo: {self._ler(e, FOGO) or '-'}"

    def painel_texto(self):  # trava ocupada: o último texto mostrado
        self._painel = self._sem_esperar(self._texto_painel) or self._painel
        return self._painel

    def _publicar(self, texto):  # sinal Qt: na thread da janela é direto, nas outras vai para a fila
        self._painel = texto
        self._ponte is not None and self._ponte.texto.emit(texto)

    def _publicar_ultimo(self, det, guids):  # quem chama segura a trava; `ultimo` é um dict NOVO, `_ult_guid` só troca se o comando devolveu GlobalIds
        self.ultimo = pub = dict(det)
        guids and setattr(self, "_ult_guid", guids[-1])
        return pub

    def executar(self, cmd, espera=None):
        return self.executar_detalhado(cmd, espera)[0]

    def executar_detalhado(self, cmd, espera=None):  # (GlobalIds, detalhe do PRÓPRIO comando: dict novo a cada chamada, sem estado compartilhado entre threads)
        nome = cmd.get("cmd") if isinstance(cmd, dict) else None
        fn = self._camera if nome in CAMERA else getattr(self, "_c_" + str(nome), None)
        if fn is None:
            raise ValueError(f"comando desconhecido: {nome!r}")
        t0 = self._relogio()
        u = {"criados": [], "alterados": [], "apagados": [], "geometria": [], "sequencia": None, "painel": None}
        pub = det = None

        def detalhe():  # tempo do comando tomado ANTES de soltar a trava; o detalhe é deste comando
            u["t_comando_ms"] = self._relogio()
            return {k: (list(v) if isinstance(v, list) else v) for k, v in u.items() if k in ("criados", "alterados", "apagados", "geometria", "sequencia", "t_comando_ms", "t_painel_ms")} | {"t0_ms": t0}
        if nome in LIVRES:
            guids = fn(cmd, u)
            det = detalhe()
            if self.trava.acquire(blocking=False):  # trava ocupada por outro escritor: não publica e nunca espera
                try:
                    pub = self._publicar_ultimo(det, guids)
                finally:
                    self.trava.release()
        else:
            if not (self.trava.acquire(blocking=False) if espera == 0 else self.trava.acquire(timeout=-1 if espera is None else espera)):
                raise ModeloOcupado("o modelo está ocupado por outro comando")
            try:  # a Cena.atualizar roda dentro de `_transacao` e de `_desfaz_ou_refaz`, ainda com a trava
                guids = self._transacao(fn, cmd, u) if nome in TRANSACAO else fn(cmd, u)
                det = detalhe()
                pub = self._publicar_ultimo(det, guids)  # `ultimo` e `_ult_guid` antes de soltar: o próximo escritor resolve "ultimo" certo
            finally:
                self.trava.release()  # só depois de Cena.atualizar (ou do erro)
        if u["painel"] is not None:
            self._publicar(u["painel"])
            if nome == "editar_propriedades" and (self._app is None or self._na_janela()):  # fora da thread da janela não há pintura para medir: nada de número falso
                self._bombear()
                det["t_painel_ms"] = self._relogio()
                pub is None or pub.update(t_painel_ms=det["t_painel_ms"])  # só no dict deste comando
        elif nome == "selecionar":
            self._publicar(self.painel_texto())
        return guids, det

    def _enviar(self, u, remover):  # a malha só do que mudou + UMA Cena.atualizar (sem janela: nada); sequência anotada só se a cena aceitou
        if self.cena is not None:
            u["sequencia"] = int(self.cena.atualizar(self._lote(u["geometria"]) if u["geometria"] else None, remover))
            self.sequencias.append(u["sequencia"])

    def _transacao(self, fn, cmd, u):
        sel = self.selecionado
        self.ifc.begin_transaction()
        try:
            fn(cmd, u)
            self.ifc.end_transaction()
        except BaseException:
            self.ifc.discard_transaction()  # antes do commit: desfaz só a transação aberta (ifc.undo() desfaria a anterior)
            self.selecionado = sel
            raise
        guids = list(dict.fromkeys(u["criados"] + u["alterados"] + u["apagados"]))
        self.historico.append({"guids": guids, "alterados": list(u["alterados"]), "geometria": list(u["geometria"])})
        try:
            self._enviar(u, u["apagados"])
        except BaseException:  # depois do commit: volta a transação, o registro e a seleção; o commit apagou o refazer do ifcopenshell, então o do fluxo também
            self.historico.pop()
            self.ifc.undo()
            self._refazer.clear()
            self.selecionado = sel
            raise
        self._g += u.pop("dg", 0)  # paredes criadas: contador que desfazer NÃO devolve (nem o comando que falhou)
        self._refazer.clear()
        return guids

    def _lote(self, guids):  # malhas do núcleo -> LoteMalha (sombreado chapado: 3 vértices por triângulo, normal da face; posições relativas ao deslocamento da cena)
        import obimcore
        from formato_malha import DTYPE_OBJETO, DTYPE_VERTICE, LoteMalha
        mal = obimcore.malhas(self.ifc, list(guids))
        gs = [g for g in guids if len(mal[g]["indices"])]
        if not gs:
            return None
        pos = [np.asarray(mal[g]["posicoes"], np.float64).reshape(-1, 3)[np.asarray(mal[g]["indices"], np.int64).reshape(-1, 3)].reshape(-1, 3) for g in gs]
        if self._desl is None:  # coordenada UTM (Y ~ 7,4 milhões de m) não cabe em float32: o 1o lote fixa o centro da cena, arredondado ao metro (como a S03)
            caixa = np.concatenate(pos)
            self._desl = np.rint((caixa.min(0) + caixa.max(0)) / 2.0)
        pos = [p - self._desl for p in pos]  # em float64; só depois vira float32
        n = np.array([len(p) for p in pos])
        ini, todos = np.cumsum(n) - n, np.concatenate(pos)
        t = todos.reshape(-1, 3, 3)
        nor = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        nor = np.repeat(nor / np.maximum(np.linalg.norm(nor, axis=1, keepdims=True), 1e-12), 3, axis=0)
        v, o = np.empty(len(todos), DTYPE_VERTICE), np.empty(len(gs), DTYPE_OBJETO)
        v["pos"], v["normal"], v["cor"] = todos, nor, np.repeat([np.clip(np.rint(np.asarray(mal[g]["cor"], float).reshape(4) * 255), 0, 255) for g in gs], n, axis=0)
        for j, g in enumerate(gs):  # um índice por vértice (0, 1, 2, ... no lote todo)
            o[j] = (0, g.encode("ascii"),  # id STEP 0: o núcleo não precisa dele (tabela do núcleo, `id_step`)
                 ini[j], n[j], ini[j], n[j], pos[j].min(0), pos[j].max(0))
        return LoteMalha(len(self.sequencias), v, np.arange(len(todos), dtype=np.uint32), o, self._desl.copy(), len(gs), len(gs))

    def _produto(self, alvo, erro=True):  # elemento pelo GlobalId (ou "ultimo"); sem `erro`, None se não existe
        g = self._ult_guid if alvo == "ultimo" else alvo
        try:
            return self.ifc.by_guid(g)
        except Exception:
            if erro:
                raise ValueError(f"alvo inválido ou inexistente: {alvo!r}") from None

    def _tipo(self, nome):
        return next((t for t in self.ifc.by_type("IfcWallType") if t.Name == nome), None)

    def _c_criar_tipo(self, c, u):
        nome, camadas = str(c["nome"]), [float(x) for x in c["camadas_m"]]
        if not camadas or min(camadas) <= 0 or self._tipo(nome):
            raise ValueError(f"tipo inválido ou já existente: {nome!r}")
        t = api("root.create_entity", self.ifc, ifc_class="IfcWallType", name=nome)
        conj = api("material.add_material_set", self.ifc, name=nome, set_type="IfcMaterialLayerSet")
        for i, esp in enumerate(camadas, 1):
            cam = api("material.add_layer", self.ifc, layer_set=conj, material=api("material.add_material", self.ifc, name=f"{nome} camada {i}"))
            api("material.edit_layer", self.ifc, layer=cam, attributes={"LayerThickness": esp / self.esc})
        api("material.assign_material", self.ifc, products=[t], material=conj)
        u["criados"] = [t.GlobalId]

    def _representacoes(self, w, comp, alt, esp):  # Body (extrusão comprimento x espessura x altura) e Axis; o 1o comando que precisa dos contextos os cria, dentro da própria transação
        corpo, eixo = _contextos(self.ifc)
        for rep in (api("geometry.add_wall_representation", self.ifc, context=corpo, length=comp, height=alt, thickness=esp),
                    api("geometry.add_axis_representation", self.ifc, context=eixo, axis=[(0.0, 0.0), (comp, 0.0)])):
            if rep.RepresentationIdentifier == "Body":
                sol = rep.Items[0]
                sol.Depth = round(sol.Depth, 6)  # a conversão de metros para a unidade do projeto deixa ruído (2799.9999999999995 mm): fica o valor exato
            api("geometry.assign_representation", self.ifc, product=w, representation=rep)

    def _paredes(self, c, n, u):
        tipo = self._tipo(c["tipo"])
        comp, alt, esp = (float(c[k]) for k in ("comprimento", "altura", "espessura"))
        pavs = self.ifc.by_type("IfcBuildingStorey")
        if tipo is None or min(comp, alt, esp) <= 0 or not pavs or n < 1:
            raise ValueError(f"parede inválida (tipo {c['tipo']!r} inexistente, medida <= 0 ou modelo sem pavimento)")
        ws, conj = [], E.get_material(tipo, should_inherit=False)  # conjunto de camadas do tipo: cada parede ganha o seu IfcMaterialLayerSetUsage (T11c)
        for k in range(n):
            g, w = self._g + k, api("root.create_entity", self.ifc, ifc_class="IfcWall", name="Parede")
            self._representacoes(w, comp, alt, esp)
            m = np.eye(4)
            m[:2, 3] = (g % 50) * 5.0, (g // 50) * 4.0
            api("geometry.edit_object_placement", self.ifc, product=w, matrix=m)
            if conj is not None and conj.is_a("IfcMaterialLayerSet"):  # tipo sem conjunto de camadas: parede sem material (nada a atribuir)
                api("material.assign_material", self.ifc, products=[w], type="IfcMaterialLayerSetUsage", material=conj)
            ws.append(w)
        api("type.assign_type", self.ifc, related_objects=ws, relating_type=tipo, should_map_representations=False)  # uma chamada só para o lote: evita custo quadrático (lote Opus 23 A1)
        api("spatial.assign_container", self.ifc, products=ws, relating_structure=min(pavs, key=lambda s: s.Name or ""))
        u["criados"], u["geometria"] = [w.GlobalId for w in ws], [w.GlobalId for w in ws]
        u["dg"] = n

    _c_criar_parede, _c_criar_paredes_lote = (lambda self, c, u: self._paredes(c, 1, u)), (lambda self, c, u: self._paredes(c, int(c["quantidade"]), u))

    def _c_editar_propriedades(self, c, u):
        w = self._produto(c["alvo"])
        self.selecionado = w.GlobalId  # marca antes; o painel mostra o valor novo
        if c.get("nome") is not None:
            api("attribute.edit_attributes", self.ifc, product=w, attributes={"Name": str(c["nome"])})
        for chave, valor in c.get("propriedades", {}).items():
            pset, prop = chave.split(".", 1)
            ps = E.get_pset(w, pset)
            api("pset.edit_pset", self.ifc, pset=self.ifc.by_id(ps["id"]) if ps else api("pset.add_pset", self.ifc, product=w, name=pset), properties={prop: valor})
        u["alterados"], u["painel"] = [w.GlobalId], self._texto_painel()

    def _c_mudar_comprimento(self, c, u):
        if self.ifc.schema == "IFC2X3":  # só IFC4 em diante: a curva do perfil é IfcIndexedPolyCurve
            raise ValueError("mudar_comprimento só funciona em IFC4 ou mais novo (o modelo é IFC2X3)")
        w, comp = self._produto(c["alvo"]), float(c["comprimento"])
        reps = {r.RepresentationIdentifier: r for r in (w.Representation.Representations if w.Representation else [])}
        if "Body" not in reps or comp <= 0 or not reps["Body"].Items[0].is_a("IfcExtrudedAreaSolid"):
            raise ValueError("a parede não tem representação Body extrudada ou o comprimento é inválido")
        sol, esc = reps["Body"].Items[0], self.esc
        ys = [p[1] for p in sol.SweptArea.OuterCurve.Points.CoordList]  # IFC4: IfcIndexedPolyCurve, como add_wall_representation monta
        alt, esp = sol.Depth * esc, (max(ys) - min(ys)) * esc
        for antiga in [reps[i] for i in ("Body", "Axis") if i in reps]:
            api("geometry.unassign_representation", self.ifc, product=w, representation=antiga)
            api("geometry.remove_representation", self.ifc, representation=antiga)
        self._representacoes(w, comp, alt, esp)
        u["alterados"], u["geometria"] = [w.GlobalId], [w.GlobalId]

    def _c_mover(self, c, u):
        w = self._produto(c["alvo"])
        m = P.get_local_placement(w.ObjectPlacement) if w.ObjectPlacement else np.eye(4)
        m[:3, 3] += np.array([float(c["dx"]), float(c["dy"]), float(c["dz"])]) / self.esc
        api("geometry.edit_object_placement", self.ifc, product=w, matrix=m, is_si=False)
        u["alterados"], u["geometria"] = [w.GlobalId], [w.GlobalId]

    def _c_apagar(self, c, u):
        w = self._produto(c["alvo"])
        u["apagados"] = [w.GlobalId]
        api("root.remove_product", self.ifc, product=w)
        if self.selecionado == u["apagados"][0]:
            self.selecionado, u["painel"] = None, "(nada selecionado)"

    def _desfaz_ou_refaz(self, u, desfazer):
        de, para = (self.historico, self._refazer) if desfazer else (self._refazer, self.historico)
        if not de:
            return []
        reg = de[-1]  # o registro só sai da pilha depois de o undo()/redo() dar certo (e da cena aceitar)
        existe = lambda: {g: bool(self._produto(g, False)) for g in reg["guids"]}  # noqa: E731
        antes = existe()
        (self.ifc.undo if desfazer else self.ifc.redo)()
        try:
            depois = existe()  # a cena segue o ESTADO RESULTANTE: sai o que sumiu; vai só a malha do que o comando original mexeu na geometria ou do que acabou de aparecer (propriedade nunca manda malha)
            u["criados"], u["apagados"], u["alterados"] = ([g for g in reg["guids"] if depois[g] and not antes[g]], [g for g in reg["guids"] if antes[g] and not depois[g]], list(reg["alterados"]))
            u["geometria"] = [g for g in reg["guids"] if depois[g] and (g in reg["geometria"] or not antes[g]) and getattr(self.ifc.by_guid(g), "Representation", None) is not None]
            self._enviar(u, [g for g in reg["guids"] if not depois[g]])
        except BaseException:
            (self.ifc.redo if desfazer else self.ifc.undo)()  # volta o modelo; o registro nunca saiu da pilha de origem
            raise
        de.pop()
        para.append(reg)
        if self.selecionado:
            u["painel"] = self._texto_painel()
        return list(reg["guids"])

    _c_desfazer, _c_refazer = (lambda self, c, u: self._desfaz_ou_refaz(u, True)), (lambda self, c, u: self._desfaz_ou_refaz(u, False))

    def _c_abrir(self, c, u):
        todos, vistos = [p.GlobalId for p in self.ifc.by_type("IfcProduct") if p.Representation], []
        for i in range(0, len(todos) if self.cena is not None else 0, BLOCO):
            if (lote := self._lote(todos[i:i + BLOCO])) is not None:
                u["sequencia"] = int(self.cena.adicionar_lote(lote))
                self.sequencias.append(u["sequencia"])
                vistos += [g.decode() for g in lote.objetos["guid"]]
        return todos if self.cena is None else vistos

    def _c_gravar(self, c, u):
        from openbim_app.localidade import garantir_numerico_c
        garantir_numerico_c()  # o Qt pode ter posto a vírgula decimal de volta (T26)
        self._arquivo_ifc = self.saida / c["arquivo"]
        self._arquivo_ifc.parent.mkdir(parents=True, exist_ok=True)
        self.ifc.write(str(self._arquivo_ifc))
        return []

    def _c_selecionar(self, c, u):
        if self.cena is None:
            return []
        if self._na_janela():
            self._tam = (self._cont.width(), self._cont.height())  # fora da thread da janela, nenhum método do contêiner: vale o tamanho guardado por ela
        x, y = ((self._tam[0] if k == "x" else self._tam[1]) / 2 if c[k] == "centro" else float(c[k]) for k in "xy")
        if self._t_cam > 0 and not self._bombear(lambda: sum(t >= self._t_cam for t, _ in self.cena.relogio()) >= 2, 10000):  # a câmera só vale depois que a thread de desenho a aplica; o 1o quadro ainda pode ser da câmera antiga, o 2o já a tem
            raise TimeoutError("nenhum quadro com a câmera nova em 10 s")
        g = self.cena.selecionar(x, y)  # pixels lógicos (os do mouse do Qt)
        self.selecionado = g
        return [g] if g else []

    def _camera(self, c, u):  # orbitar, camera_mover, aproximar, enquadrar, animar_orbita, parar_animacao: um método da Cena com os argumentos do cartão
        met, chaves = CAMERA[c["cmd"]]
        r = [] if self.cena is None else getattr(self.cena, met)(*(float(c[k]) for k in chaves.split())) or []
        if self.cena is not None and c["cmd"] in ("enquadrar", "orbitar", "camera_mover", "aproximar"):
            self._t_cam = self._relogio()  # depois de a Cena voltar (antes, o 1o quadro pode ser da câmera velha)
        return r

    def _c_camera(self, c, u):  # `alvo` vem em coordenadas do MUNDO; a cena está em mundo menos o deslocamento (RG-07)
        if self.cena is not None:
            a = {k: ([float(x) for x in c[k]] if k == "alvo" else float(c[k])) for k in ("alvo", "distancia", "azimute", "elevacao") if k in c}
            if "alvo" in a:
                if self._desl is None:  # câmera antes de qualquer malha: o deslocamento da cena nasce do alvo (o 1º lote o usa)
                    self._desl = np.rint(np.asarray(a["alvo"], np.float64))
                a["alvo"] = [float(x) for x in np.asarray(a["alvo"], np.float64) - self._desl]
            self.cena.definir_camera(**a)
            self._t_cam = self._relogio()
        return []

    _c_esperar = lambda self, c, u: self._bombear(lambda: False, float(c["ms"])) or []  # noqa: E731  (bombeia eventos até passar o tempo)

    def _quadro(self, seq, t_ini, t_cmd, limite_ms=10000):  # tempo do 1o quadro apresentado com sequência >= seq (até 10 s)
        achado = []
        if not self._bombear(lambda: bool(achado.extend(t for t, s in self.cena.relogio() if t >= t_ini and s >= seq) or achado), limite_ms):
            raise TimeoutError(f"nenhum quadro com a sequência {seq} em {limite_ms} ms")
        return max(min(achado), t_cmd)  # o quadro não pode vir antes de o comando voltar (corrida de microssegundos)

    def executar_roteiro(self, caminho_json):
        roteiro = json.loads(Path(caminho_json).read_text(encoding="utf-8"))
        with self.trava:  # a contagem lê o modelo: com a trava presa, solta antes do 1º comando
            base = sum(1 for p in self.ifc.by_type("IfcProduct") if p.Representation)  # produtos com geometria antes do roteiro
        self._passos, passos = {}, []
        for p in roteiro["passos"]:
            args, reps = {k: v for k, v in p.items() if k not in ("id", "n")}, []
            for r in range(int(p.get("n", 1))):
                cmd = dict(args)
                if isinstance(a := cmd.get("alvo"), dict):  # {"passo": id, "k": n}: n-ésimo GlobalId criado pelo passo (k omitido: o índice da repetição)
                    if not 0 <= (k := a.get("k", r)) < len(lista := self._passos.get(str(a["passo"]), [])):
                        raise ValueError(f"alvo {a!r}: o passo não criou tantos elementos")
                    cmd["alvo"] = lista[k]
                if isinstance(cmd.get("nome"), str):
                    cmd["nome"] = cmd["nome"].replace("{r}", str(r))
                guids, u = self.executar_detalhado(cmd)  # o detalhe do próprio comando (não `ultimo`)
                tq = self._quadro(u["sequencia"], u["t0_ms"], u["t_comando_ms"]) if self.cena is not None and u["sequencia"] is not None and (u["geometria"] or u["apagados"] or cmd["cmd"] == "abrir") else u["t_comando_ms"]
                rep = {"r": r, "guids": guids, **{k: u[k] for k in ("criados", "alterados", "apagados", "geometria", "sequencia", "t0_ms", "t_comando_ms", "t_painel_ms") if k in u}, "t_quadro_ms": tq,
                       "ms_total": tq - u["t0_ms"], "triangulos_cena": None if self.cena is None else int(self.cena.estatisticas()["triangulos"])}
                if cmd["cmd"] in ("esperar", "criar_paredes_lote"):
                    rep["relogio"] = None if self.cena is None else [[float(t), int(s)] for t, s in self.cena.relogio() if u["t0_ms"] <= t <= tq]
                reps.append(rep)
                self._passos.setdefault(str(p["id"]), []).extend(u["criados"])
                self._bombear()  # entre repetições, nunca dentro de transação
            passos.append({"id": p["id"], "cmd": p["cmd"], "reps": reps})
        med = {"fluxo": "A", "versao": 1, "plataforma": sys.platform, "rhi": self._rhi, "base": {"arquivo": self.caminho_ifc, "produtos": base}, "passos": passos,
               "metas": None if self.cena is None else _metas(passos), "arquivo_medicao": str(self.saida / "medicao.json"), "arquivo_ifc": None if self._arquivo_ifc is None else str(self._arquivo_ifc)}
        Path(med["arquivo_medicao"]).write_text(json.dumps(med, ensure_ascii=False, indent=1), encoding="utf-8")
        return med


def _metas(passos):  # M2, M2b, M3, M4 e M5 do lote 9 §2.2 e §2.3, dos tempos brutos (percentil linear); M1 e M6 ficam para o fluxo B
    por = {p["id"]: p["reps"] for p in passos}
    meta = lambda pid, f, lim: (lambda v: {"passo": pid, "n": len(v), "mediana_ms": float(np.median(v)), "p95_ms": float(np.percentile(v, 95)), "max_ms": float(v.max()), "limite_ms": lim,  # noqa: E731
                                           "ok": bool(np.percentile(v, 95) < lim)} if len(v) else None)(np.array([f(r) for r in por.get(pid, [])], float))
    m = {"M2": meta("3", lambda r: r["ms_total"], 200), "M2b": meta("4b", lambda r: r["ms_total"], 200), "M3": meta("4a", lambda r: r["t_painel_ms"] - r["t0_ms"], 50),
         "M4": meta("5b", lambda r: r["ms_total"], 20000), "M5": None, "M1": None, "M6": None}
    if por.get("5b") and por.get("4c"):
        lote, parado = por["5b"][0], por["4c"][0]
        t, tp, ini, fim = (np.array([x[0] for x in lote["relogio"]], float), np.array([x[0] for x in parado["relogio"]], float), lote["t0_ms"], lote["t_quadro_ms"])
        jan = [int(((t >= ini + 1000 * k) & (t < ini + 1000 * (k + 1))).sum()) for k in range(int((fim - ini) // 1000))]
        maior, par = float(np.diff(np.r_[ini, t, fim]).max()), float(np.diff(tp).max()) if len(tp) > 1 else 0.0
        m["M5"] = {"passo": "5b", "n": len(t), "limite_ms": 200, "quadros_por_janela_min": min(jan) if jan else None, "janelas": jan, "maior_intervalo_ms": maior, "maior_intervalo_parado_ms": par,
                   "ok": bool(all(n >= 20 for n in jan) and (jan or len(t) >= 20 * (fim - ini) / 1000) and maior < 200 and maior <= 3 * max(33.3, par))}
    return m
