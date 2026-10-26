# SPDX-License-Identifier: AGPL-3.0-or-later
"""Transação única IFC + lateral, desfazer e refazer (ADR-002 §4.1, §4.2, §4.6 e §4.8). Sem Qt, sem `obimcore`.
Uma transação nossa = um `Transaction` do ifcopenshell + as operações do lateral; fora dela `arquivo.transaction` é uma sentinela que recusa edição.
Tudo roda em `SessaoModelo.escrever()`. Limite de memória sobre histórico mais refazer dos dois lados."""
import json
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
    def __init__(self, arquivo, historico):
        self.arquivo, self._h = arquivo, historico

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
            with self._h._livre(self.arquivo):
                self.arquivo.remove(element)
            if sys._getframe(1).f_code is ifcopenshell.file.add.__code__:  # file.add (file.py:722; Python 3.12): as dependências criadas não dá para limpar
                self._h._quebrar(self.arquivo, "file.add fora de uma transação deixou entidades soltas")
            self._recusar()


class _Lado:  # o lateral dentro da transação: aplica na hora e guarda (coleção, id, antigo, novo) para desfazer
    def __init__(self, lateral):
        self._lat, self.ops = lateral, []

    def __getattr__(self, nome):  # criar, alterar, apagar
        if nome not in ("criar", "alterar", "apagar"):
            raise AttributeError(nome)

        def aplicar(c, i, *obj):
            antigo = self._lat.obter(c, i)
            getattr(self._lat, "_" + nome)(c, i, *obj)
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

    def ent(i):
        try:
            return a.by_id(i)
        except RuntimeError:
            return None

    def objeto(i):  # GlobalId se o id é IfcObjectDefinition (existindo ou só nas operações), senão None
        e, v = ent(i), info.get(i)
        if e is not None:
            return e.GlobalId if e.is_a("IfcObjectDefinition") else None
        return v["GlobalId"] if v and _subtipo(a.schema_identifier, v["type"], "IfcObjectDefinition") else None

    def gids(ids):
        return {g for g in map(objeto, ids) if g}

    donos, visto = set(), set()

    def sobe(e):
        if e.id() in visto: return
        visto.add(e.id())
        if e.is_a("IfcObjectDefinition"):
            donos.add(e.GlobalId)
            return
        for i in a.get_inverse(e):
            if i.is_a("IfcRelationship"):  # a relação nunca é dona; só os objetos das listas dela
                donos.update(o.GlobalId for x in i if isinstance(x, tuple) for o in x if o.id() and o.is_a("IfcObjectDefinition"))
            else:
                sobe(i)

    for i in nc | nd:
        if _subtipo(a.schema_identifier, info[i]["type"], "IfcRelationship"):
            donos.update(gids(_ids([v for k, v in info[i].items() if k not in ("id", "type")], set())))  # relação criada ou apagada: todos os objetos dela
        elif (e := ent(i)) is not None:
            sobe(e)
    for i in set(edits) | inv:  # editados e atingidos pelos inversos de um apagado (a relação aí só perdeu o próprio apagado)
        e = ent(i)
        if i in nc or i in nd or e is None: continue
        if e.is_a("IfcRelationship"):  # objetos que entraram ou saíram das listas dela
            antes, depois = set(), set()
            for op in edits.get(i, ()):
                _ids(op["old"], antes), _ids(op["new"], depois)
            donos.update(gids(antes ^ depois))
        else:
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


def _custo_passo(ifc_enc, lado_ops):
    dados = {"ifc": ifc_enc, "lado": list(lado_ops)}
    raw = json.dumps(dados, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return len(raw) * 12


class Historico:
    def __init__(self, sessao, lateral, limite_bytes=256 * 1024 * 1024, codificar=None, anotar=None, avisar=None):
        if isinstance(limite_bytes, bool) or (limite_bytes is not None and (not isinstance(limite_bytes, int) or limite_bytes <= 0)):
            raise ValueError("limite_bytes deve ser inteiro > 0 ou None")
        self._lat, self._limite_bytes, self._codificar, self._anotar, self._avisar = (
            lateral, limite_bytes, codificar, anotar, avisar
        )
        self._lh, self._lf, self._ch, self._cf = [], [], [], []  # lateral e custos: histórico e refazer (o IFC guarda as dele)
        self._descartados, self._aberta, self._quebrado, self._poda_pendente = 0, False, False, False
        with sessao.escrever() as esc:  # abre escrever() próprio: dentro de outro escrever() da mesma thread dá ReentradaProibida
            a = self._arquivo = esc.arquivo
            if a.transaction is not None:
                raise TransacaoAberta("o arquivo já tem uma transação aberta")
            a.set_history_size(sys.maxsize)  # só o nosso limite descarta passos, nunca o silencioso da biblioteca
            self._sent = a.transaction = _Sentinela(a, self)

    pode_desfazer = property(lambda s: bool(s._lh))
    pode_refazer = property(lambda s: bool(s._lf))
    quebrado = property(lambda s: s._quebrado)
    descartados = property(lambda s: s._descartados)

    @property
    def limite_bytes(self):
        return self._limite_bytes

    @limite_bytes.setter
    def limite_bytes(self, novo):
        if isinstance(novo, bool) or (novo is not None and (not isinstance(novo, int) or novo <= 0)):
            raise ValueError("limite_bytes deve ser inteiro > 0 ou None")
        self._limite_bytes = novo
        if not self._aberta:
            self._podar()
        else:
            self._poda_pendente = True

    def _podar(self):
        self._poda_pendente = False
        if self._limite_bytes is None or self._arquivo is None or self._quebrado:
            return
        a = self._arquivo
        custo_total = sum(self._ch) + sum(self._cf)
        min_hist = 1 if not self._lf else 0
        while len(self._lh) > min_hist and custo_total > self._limite_bytes:
            custo_removido = self._ch.pop(0)
            self._lh.pop(0)
            a.history.pop(0)
            custo_total -= custo_removido
            self._descartados += 1

    def _pre(self, esc):
        a = esc.arquivo  # TravaNaoSegura se vencido
        if self._aberta or self._quebrado:
            raise TransacaoAberta("já há uma transação aberta") if self._aberta else HistoricoQuebrado("histórico quebrado; reabra pela recuperação")
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

    def _aplicar_lado(self, ops, avanco):  # se o lateral falhar no meio, desfaz só o que já foi aplicado
        feitas = []
        try:
            for c, i, antigo, novo in (ops if avanco else reversed(ops)):
                self._lat._repor(c, i, novo if avanco else antigo)
                feitas.append((c, i, antigo if avanco else novo))
        except BaseException:
            for c, i, volta in reversed(feitas):
                self._lat._repor(c, i, volta)
            raise

    @contextmanager
    def _aberto(self, esc):  # marca "transação aberta" (transação e fora_do_historico não se aninham)
        a = self._pre(esc)
        self._aberta = True
        try:
            yield a
        finally:
            self._aberta = False
            if self._poda_pendente and not self._quebrado:
                self._podar()

    @contextmanager
    def transacao(self, esc):
        with self._aberto(esc) as a:
            a.transaction = None
            a.begin_transaction()
            tx, t = a.transaction, SimpleNamespace(ifc=a, lado=_Lado(self._lat), resumo=None)
            try:
                yield t
                enc = self._codificar(tx.operations) if self._codificar else None
                if enc is not None:
                    custo_ifc = enc
                else:
                    from openbim_app.diario import codificar_ifc
                    custo_ifc = codificar_ifc(tx.operations)
                custo = _custo_passo(custo_ifc, t.lado.ops)
                if a.transaction is not tx:
                    raise RuntimeError("a transação do arquivo foi trocada por terceiros")
            except BaseException as e:
                self._abortar(a, tx, t, e)
                raise
            a.end_transaction()
            a.transaction = self._sent
            self._lf.clear()
            self._cf.clear()
            n0 = len(self._lh)
            try:
                t.resumo = Resumo(*_resumo_ifc(a, tx.operations, True), *_resumo_lado(t.lado.ops, True))
                self._anotar and self._anotar("transacao", enc, t.lado.ops)
                self._lh.append(t.lado.ops)
                self._ch.append(custo)
            except BaseException:  # o passo sai dos dois lados (e o refazer anterior já se perdeu no end_transaction)
                if len(self._lh) > n0:
                    self._lh.pop()
                if len(self._ch) > n0:
                    self._ch.pop()
                self._lado(t.lado.ops, False)
                self._ifc(a, True)
                a.future.pop()
                raise
            self._podar()

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
        de_c, para_c = (self._ch, self._cf) if desfazer else (self._cf, self._ch)
        if not de:
            if desfazer and not self._lh and self._descartados > 0 and self._avisar:
                self._avisar("desfazer impossível: passos foram descartados por limite de memória")
            return None
        lado_ops, tr = de[-1], (a.history if desfazer else a.future)[-1]
        self._ifc(a, desfazer)  # IFC primeiro; se falhar o lateral não é mexido
        aplicado = False
        try:
            self._aplicar_lado(lado_ops, not desfazer)
            aplicado = True
            resumo = Resumo(*_resumo_ifc(a, tr.operations, not desfazer), *_resumo_lado(lado_ops, not desfazer))
            self._anotar and self._anotar("desfazer" if desfazer else "refazer", self._codificar(tr.operations) if self._codificar else None, lado_ops)
            para.append(de.pop())
            para_c.append(de_c.pop())
        except BaseException:  # tudo volta: modelo e lateral (só o que já foi aplicado)
            if aplicado:
                self._aplicar_lado(lado_ops, desfazer)
            self._ifc(a, not desfazer)
            raise
        return resumo

    def desfazer(self, esc):
        return self._mover(esc, True)

    def refazer(self, esc):
        return self._mover(esc, False)

    @contextmanager
    def fora_do_historico(self, esc):  # só para o carimbo do pset OBIM_Projeto: edição livre, sem desfazer nem diário
        with self._aberto(esc) as a, self._livre(a):
            yield

    def encerrar(self):
        a = self._arquivo
        if a is not None:
            a.history.clear(), a.future.clear()
            a.transaction = None
            ifcopenshell.file.registry.pop(int(a.this), None)
            self._arquivo = None
        self._lh.clear(), self._lf.clear()
        self._ch.clear(), self._cf.clear()
        self._descartados = 0
        self._sent = None
