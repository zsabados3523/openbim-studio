# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transação única IFC + lateral, desfazer e refazer (F0-S05-T04; ADR-002 §4.1, §4.2 e §4.8). Sem Qt, sem `obimcore`.
Uma transação nossa = um `Transaction` do ifcopenshell + as operações do lateral; fora dela `arquivo.transaction` é uma sentinela que recusa edição.
Tudo roda dentro de `SessaoModelo.escrever()`. O limite de memória é do T08 (`limite_bytes` é guardado; `descartados` fica em 0)."""
import sys
from collections import namedtuple
from contextlib import contextmanager
from functools import lru_cache
from types import SimpleNamespace

import ifcopenshell
import ifcopenshell.ifcopenshell_wrapper as W
from ifcopenshell.file import UndoSystemError


class EdicaoForaDeTransacao(RuntimeError):
    """Edição do modelo sem transação nossa aberta."""


class TransacaoAberta(RuntimeError):
    """Transação, desfazer ou refazer com outra transação aberta."""


class HistoricoQuebrado(RuntimeError):
    """O desfazer do ifcopenshell falhou ou terceiros mexeram na transação; o caminho é reabrir pela recuperação."""


Resumo = namedtuple("Resumo", "criados alterados apagados lado_criados lado_alterados lado_apagados")  # GlobalId; no lateral, (coleção, id)


class _Sentinela:  # repete o filtro da biblioteca: só entidade com id() diferente de 0 conta (file.py:136 a :149)
    def __init__(self, arquivo):
        self.arquivo = arquivo

    @staticmethod
    def _recusar():
        raise EdicaoForaDeTransacao("edição do modelo fora de uma transação (use Historico.transacao)")

    def store_edit(self, element, index, value):
        element.id() and self._recusar()

    def store_delete(self, element):
        self._recusar()
    batch = unbatch = store_delete

    def store_create(self, element):  # chamado depois de criar (file.py:661): o objeto criado sai
        if element.id():
            a = self.arquivo
            a.transaction = None
            try:
                a.remove(element)
            finally:
                a.transaction = self
            self._recusar()


class _Lado:  # o lateral dentro da transação: aplica na hora e guarda (coleção, id, antigo, novo) para desfazer
    def __init__(self, lateral):
        self._lat, self.ops = lateral, []

    def __getattr__(self, nome):  # criar, alterar, apagar
        if nome not in ("criar", "alterar", "apagar"):
            raise AttributeError(nome)

        def aplicar(c, i, *obj):
            antigo = self._lat.obter(c, i)
            getattr(self._lat, nome)(c, i, *obj)
            self.ops.append((c, i, antigo, self._lat.obter(c, i)))
        return aplicar


@lru_cache(maxsize=None)
def _subtipo(esquema, classe, alvo):  # a classe (por nome) é a alvo ou subtipo dela?
    d = W.schema_by_name(esquema).declaration_by_name(classe)
    while d is not None and d.name() != alvo:
        d = d.supertype()
    return d is not None


def _ids(v, achados):  # ids STEP das referências serializadas ({"id": n}) dentro de um valor
    if isinstance(v, dict) and v.get("id"):
        achados.add(v["id"])
    for x in v if isinstance(v, (list, tuple)) else ():
        _ids(x, achados)
    return achados


def _resumo_ifc(a, ops, avanco):  # ADR-002 §4.1: criados, alterados e apagados por GlobalId (dono de quem não tem GlobalId sobe pelos inversos)
    cria, apaga, info, edits, inv = set(), set(), {}, {}, set()
    for op in ops:
        k = op["action"]
        inv.update(op.get("inverses", ()))
        if k in ("create", "delete"):
            v = op["value"]
            (cria if k == "create" else apaga).add(v["id"])
            info[v["id"]] = v
        elif k == "edit":
            edits.setdefault(op["id"], []).append(op)
    nc, nd = cria - apaga, apaga - cria  # criada e apagada na mesma transação não conta
    if not avanco:
        nc, nd = nd, nc
    esq = a.schema_identifier

    def ent(i):
        try:
            return a.by_id(i)
        except RuntimeError:
            return None

    def objeto(i):  # GlobalId se o id é IfcObjectDefinition (existindo ou só nas operações), senão None
        e, v = ent(i), info.get(i)
        if e is not None:
            return e.GlobalId if e.is_a("IfcObjectDefinition") else None
        return v["GlobalId"] if v and _subtipo(esq, v["type"], "IfcObjectDefinition") else None

    def gids(ids):
        return {g for g in map(objeto, ids) if g}

    donos, visto = set(), set()

    def sobe(e):
        if e.id() in visto:
            return
        visto.add(e.id())
        if e.is_a("IfcObjectDefinition"):
            donos.add(e.GlobalId)
            return
        for i in a.get_inverse(e):
            if i.is_a("IfcRelationship"):  # a relação nunca é dona; só os objetos das listas dela
                for x in i:
                    xs = x if isinstance(x, tuple) else ()
                    donos.update(o.GlobalId for o in xs if o.id() and o.is_a("IfcObjectDefinition"))
            else:
                sobe(i)

    for i in nc | nd:
        if _subtipo(esq, info[i]["type"], "IfcRelationship"):
            achados = set()  # relação criada ou apagada: todos os objetos dela
            for k, v in info[i].items():
                k in ("id", "type") or _ids(v, achados)
            donos.update(gids(achados))
        elif (e := ent(i)) is not None:
            sobe(e)
    for i, lista in edits.items():
        e = ent(i)
        if i in nc or i in nd or e is None:
            continue
        if e.is_a("IfcRelationship"):  # objetos que entraram ou saíram das listas dela
            antes, depois = set(), set()
            for op in lista:
                _ids(op["old"], antes), _ids(op["new"], depois)
            donos.update(gids(antes ^ depois))
        else:
            sobe(e)
    for i in inv - nc - nd - set(edits):  # atingidos pelos inversos de um apagado (a relação aí só perdeu o próprio apagado)
        e = ent(i)
        if e is not None and not e.is_a("IfcRelationship"):
            sobe(e)
    criados, apagados = gids(nc), gids(nd)
    return tuple(sorted(criados)), tuple(sorted(donos - criados - apagados)), tuple(sorted(apagados))


def _resumo_lado(ops, avanco):
    est = {}
    for c, i, antigo, novo in ops:
        est[(c, i)] = (est.get((c, i), (antigo,))[0], novo)
    cr, ap, al = (tuple(sorted(k for k, (a, n) in est.items() if f(a, n))) for f in (
        lambda a, n: a is None and n is not None, lambda a, n: a is not None and n is None, lambda a, n: a is not None and n is not None))
    return (cr, al, ap) if avanco else (ap, al, cr)


class Historico:
    def __init__(self, sessao, lateral, limite_bytes=None, codificar=None, anotar=None):
        self._lat, self.limite_bytes, self._codificar, self._anotar = lateral, limite_bytes, codificar, anotar
        self._lh, self._lf, self._aberta, self._quebrado = [], [], False, False  # lateral: histórico e refazer (o IFC guarda as dele)
        with sessao.escrever() as esc:
            a = self._arquivo = esc.arquivo
            if a.transaction is not None:
                raise TransacaoAberta("o arquivo já tem uma transação aberta")
            a.set_history_size(sys.maxsize)  # só o nosso limite (T08) descarta passos, nunca o silencioso da biblioteca
            self._sent = a.transaction = _Sentinela(a)

    def _cod(self, ops):
        return self._codificar(ops) if self._codificar else None

    pode_desfazer = property(lambda s: bool(s._lh))
    pode_refazer = property(lambda s: bool(s._lf))
    quebrado = property(lambda s: s._quebrado)
    descartados = property(lambda s: 0)

    def _pre(self, esc):
        a = esc.arquivo  # TravaNaoSegura se vencido
        if self._aberta:
            raise TransacaoAberta("já há uma transação aberta")
        if self._quebrado:
            raise HistoricoQuebrado("histórico quebrado; reabra pela recuperação")
        if a.transaction is not self._sent:
            self._quebrar(a, "a transação do arquivo foi trocada por terceiros")
        return a

    def _quebrar(self, a, motivo, causa=None):
        self._quebrado = True
        a.transaction = self._sent
        raise HistoricoQuebrado(motivo) from causa

    @contextmanager
    def _livre(self, a):  # sem a sentinela (undo, redo, discard, fora do histórico)
        a.transaction = None
        try:
            yield
        finally:
            a.transaction = self._sent

    def _ifc(self, a, desfazer):
        with self._livre(a):
            try:
                (a.undo if desfazer else a.redo)()
            except UndoSystemError as e:
                self._quebrar(a, "o desfazer do ifcopenshell falhou", e)

    def _lado(self, ops, avanco):
        for c, i, antigo, novo in (ops if avanco else reversed(ops)):
            self._lat._repor(c, i, novo if avanco else antigo)

    @contextmanager
    def transacao(self, esc):
        a = self._pre(esc)
        self._aberta = True
        try:
            a.transaction = None
            a.begin_transaction()
            tx, t = a.transaction, SimpleNamespace(ifc=a, lado=_Lado(self._lat), resumo=None)
            try:
                yield t
                enc = self._cod(tx.operations)
                if a.transaction is not tx:
                    raise RuntimeError("a transação do arquivo foi trocada por terceiros")
            except BaseException as e:
                self._abortar(a, tx, t, e)
                raise
            a.end_transaction()
            a.transaction = self._sent
            self._lf.clear()
            try:
                t.resumo = Resumo(*_resumo_ifc(a, tx.operations, True), *_resumo_lado(t.lado.ops, True))
                self._anotar and self._anotar("transacao", enc, t.lado.ops)
                self._lh.append(t.lado.ops)
            except BaseException:  # o passo sai dos dois lados (e o refazer anterior já se perdeu no end_transaction)
                self._lado(t.lado.ops, False)
                self._ifc(a, True)
                a.future.pop()
                raise
        finally:
            self._aberta = False

    def _abortar(self, a, tx, t, causa):  # antes do end_transaction: discard (nunca undo) e o lateral volta
        self._lado(t.lado.ops, False)
        if a.transaction is not tx:
            self._quebrar(a, "a transação do arquivo foi trocada por terceiros", causa)
        try:
            a.discard_transaction()
        except Exception as e:  # noqa: BLE001  (o rollback do descarte falhou: o modelo pode estar pela metade)
            self._quebrar(a, "o descarte da transação falhou", e)
        a.transaction = self._sent

    def _mover(self, esc, desfazer):
        a = self._pre(esc)
        de, para = (self._lh, self._lf) if desfazer else (self._lf, self._lh)
        if not de:
            return None
        lado_ops, tr = de[-1], (a.history if desfazer else a.future)[-1]
        self._ifc(a, desfazer)  # IFC primeiro; se falhar o lateral não é mexido
        try:
            self._lado(lado_ops, not desfazer)
            resumo = Resumo(*_resumo_ifc(a, tr.operations, not desfazer), *_resumo_lado(lado_ops, not desfazer))
            self._anotar and self._anotar("desfazer" if desfazer else "refazer", self._cod(tr.operations), lado_ops)
            para.append(de.pop())
        except BaseException:  # tudo volta: modelo e lateral
            self._lado(lado_ops, desfazer)
            self._ifc(a, not desfazer)
            raise
        return resumo

    def desfazer(self, esc):
        return self._mover(esc, True)

    def refazer(self, esc):
        return self._mover(esc, False)

    @contextmanager
    def fora_do_historico(self, esc):  # só para o carimbo do pset OBIM_Projeto (T07): edição livre, sem desfazer nem diário
        a = self._pre(esc)
        self._aberta = True
        try:
            with self._livre(a):
                yield
        finally:
            self._aberta = False

    def encerrar(self):
        a = self._arquivo
        a.history.clear(), a.future.clear(), self._lh.clear(), self._lf.clear()
        a.transaction = None
        ifcopenshell.file.registry.pop(int(a.this), None)
