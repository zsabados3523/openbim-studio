# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lateral provisório em memória (ADR-002 §4.3 e §4.8). Sem Qt, sem ifcopenshell.
Coleções (`[a-z_]{1,32}`, nunca `manifest`) de objetos JSON por id (`[A-Za-z0-9_-]{1,64}`); referência ao modelo só por GlobalId. Dentro de
uma transação, edita-se por `t.lado` do `Historico`; `_criar`, `_alterar`, `_apagar` e `_repor` são só dele."""
import copy
import json
import math
import re

_COLECAO, _ID = re.compile(r"[a-z_]{1,32}"), re.compile(r"[A-Za-z0-9_-]{1,64}")


class ObjetoInvalido(ValueError):
    """Coleção, id ou objeto fora do formato (não é JSON puro, NaN, chave que não é texto...)."""


class IdRepetido(KeyError):
    """`criar` de um id que já existe."""


class IdInexistente(KeyError):
    """`alterar` ou `apagar` de um id que não existe."""


def _validar(o):
    if isinstance(o, dict):
        if not all(isinstance(k, str) for k in o):
            raise ObjetoInvalido("chave que não é texto")
        o = list(o.values())
    if isinstance(o, list):
        for x in o:
            _validar(x)
    elif isinstance(o, float) and not math.isfinite(o):
        raise ObjetoInvalido("NaN ou infinito")
    elif o is not None and not isinstance(o, (bool, int, float, str)):
        raise ObjetoInvalido(f"tipo que não é JSON: {type(o).__name__}")


def json_canonico(obj):  # bytes UTF-8
    _validar(obj)
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def _chave(c, i):
    if not _COLECAO.fullmatch(c) or c == "manifest" or not _ID.fullmatch(i):
        raise ObjetoInvalido(f"coleção ou id inválido: {c!r}, {i!r}")


class Lateral:
    def __init__(self, objetos=None):
        self._d = {}
        for c, i, o in ((c, i, o) for c, objs in (objetos or {}).items() for i, o in objs.items()):
            self._criar(c, i, o)

    json_canonico = staticmethod(json_canonico)

    def obter(self, c, i):  # cópia, ou None
        return copy.deepcopy(self._d.get(c, {}).get(i))

    def ids(self, c):
        return sorted(self._d.get(c, {}))

    def colecoes(self):
        return sorted(self._d)

    def canonico(self):
        return json_canonico(self._d)

    def _mudar(self, c, i, obj, existe, apagar=False):  # fora de apagar, o objeto tem de ser um objeto JSON (dict)
        _chave(c, i)
        if not apagar and not isinstance(obj, dict):
            raise ObjetoInvalido("o objeto do lateral é um objeto JSON (dict)")
        apagar or json_canonico(obj)
        if (i in self._d.get(c, {})) != existe:
            raise (IdInexistente if existe else IdRepetido)((c, i))
        self._repor(c, i, obj)

    def _criar(self, c, i, obj):
        self._mudar(c, i, obj, False)

    def _alterar(self, c, i, obj):  # troca o objeto inteiro
        self._mudar(c, i, obj, True)

    def _apagar(self, c, i):
        self._mudar(c, i, None, True, True)

    def _repor(self, c, i, obj):  # sem checagem: desfazer e refazer do Historico (obj None = sem o objeto)
        if obj is None:
            self._d[c].pop(i)
            self._d[c] or self._d.pop(c)  # coleção vazia some (o canônico não depende do histórico)
        else:
            self._d.setdefault(c, {})[i] = copy.deepcopy(obj)
