# SPDX-License-Identifier: AGPL-3.0-or-later
"""Arquivo `.obim` real: ZIP deflate com `manifest.json` e uma entrada JSON por objeto do `Lateral` (ADR-003 §4 a §7).
Sem Qt, sem ifcopenshell: só stdlib e `lateral`. A chave mora no campo do JSON; o nome do arquivo é o id do `Lateral`. Caminho perigoso no ZIP
é recusado (zip-slip). Versão 0.1.0 (provisório da S05) migra em memória; versão fora de 0.1/0.2 abre só para leitura."""
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace

from .lateral import Lateral

VERSAO_FORMATO = "0.2.0"
FORMATO = "obim-lateral"
_ENTRADA = re.compile(r"([a-z_]{1,32})/([A-Za-z0-9_-]{1,64})\.json")
_FAMILIAS = {(0, 1), (0, 2)}


class ObimInvalido(ValueError):
    """`.obim` fora do formato: ZIP inválido, manifesto ausente/estranho, caminho perigoso, coleção reservada inconsistente."""


def _familia(versao):
    if not isinstance(versao, str):
        return None
    try:
        numeros = [int(p) for p in versao.split(".")]
    except ValueError:
        return None
    return tuple(numeros[:2]) if len(numeros) >= 2 else None


def _perigosa(nome):
    nome = nome[:-1] if nome.endswith("/") else nome
    if not nome or nome.startswith(("/", "\\")) or "\\" in nome or re.match(r"^[A-Za-z]:", nome):
        return True
    return any(parte in ("", "..") for parte in nome.split("/"))


def _bytes(obj):
    try:
        return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as e:
        raise ObimInvalido(f"objeto fora do JSON puro: {e}") from e


def _numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validar(lateral):
    """Confere as coleções reservadas; `ObimInvalido` antes de qualquer escrita. Chave no campo, unicidade exata."""
    vistas, pranchas, viewports = {}, {}, {}
    for ident in lateral.ids("vistas"):
        guid = lateral.obter("vistas", ident).get("vista_guid")
        if not isinstance(guid, str) or not guid:
            raise ObimInvalido(f"vista {ident!r} sem vista_guid texto não vazio")
        if guid in vistas:
            raise ObimInvalido(f"vista_guid repetido: {guid!r}")
        vistas[guid] = ident
    for ident in lateral.ids("pranchas"):
        identificacao = lateral.obter("pranchas", ident).get("identification")
        if not isinstance(identificacao, str) or not identificacao or identificacao != identificacao.strip():
            raise ObimInvalido(f"prancha {ident!r} com identification vazia ou com espaço nas pontas")
        if identificacao in pranchas:
            raise ObimInvalido(f"identification repetida: {identificacao!r}")
        pranchas[identificacao] = ident
    for ident in lateral.ids("viewports"):
        o = lateral.obter("viewports", ident)
        if not isinstance(o.get("prancha"), str) or not o["prancha"]:
            raise ObimInvalido(f"viewport {ident!r} sem prancha texto não vazio")
        if not isinstance(o.get("vista_guid"), str) or not o["vista_guid"]:
            raise ObimInvalido(f"viewport {ident!r} sem vista_guid texto não vazio")
        if not _numero(o.get("x")) or not _numero(o.get("y")):
            raise ObimInvalido(f"viewport {ident!r} com x ou y que não é número")
        if not _numero(o.get("escala")) or o["escala"] <= 0:
            raise ObimInvalido(f"viewport {ident!r} com escala que não é número > 0")
        par = (o["prancha"], o["vista_guid"])
        if par in viewports:
            raise ObimInvalido(f"par prancha/vista repetido: {par!r}")
        viewports[par] = ident


def _reservado(nome):
    return nome == "manifest.json" or _ENTRADA.fullmatch(nome) is not None


def escrever(caminho, lateral, manifesto, extras=None):
    """Grava o ZIP; monta tudo antes de abrir o arquivo, então falha não deixa nada no destino."""
    validar(lateral)
    extras = extras or {}
    for nome, conteudo in extras.items():
        if _perigosa(nome):
            raise ObimInvalido(f"entrada com caminho perigoso: {nome!r}")
        if _reservado(nome):
            raise ObimInvalido(f"entrada extra com nome reservado: {nome!r}")
        if not isinstance(conteudo, bytes):
            raise ObimInvalido(f"extra {nome!r} não é bytes")
    entradas = [("manifest.json", _bytes(manifesto))]
    for colecao in lateral.colecoes():
        for ident in lateral.ids(colecao):
            entradas.append((f"{colecao}/{ident}.json", lateral.json_canonico(lateral.obter(colecao, ident))))
    entradas.extend((nome, extras[nome]) for nome in sorted(extras))
    caminho = Path(caminho)
    with zipfile.ZipFile(caminho, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in entradas:
            z.writestr(nome, conteudo)


def ler(caminho):
    """Devolve manifesto, lateral, extras, versão original e somente_leitura. Migra 0.1.0 em memória, sem regravar."""
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
            for nome in nomes:
                if _perigosa(nome):
                    raise ObimInvalido(f"entrada com caminho perigoso: {nome!r}")
            if "manifest.json" not in nomes:
                raise ObimInvalido("ZIP do lateral sem manifest.json")
            try:
                manifesto = json.loads(z.read("manifest.json").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise ObimInvalido(f"manifest.json ilegível: {e}") from e
            if not isinstance(manifesto, dict) or manifesto.get("formato") != FORMATO:
                raise ObimInvalido("manifesto do lateral fora do formato")
            versao = manifesto.get("versao_formato")
            familia = _familia(versao)
            somente_leitura = familia not in _FAMILIAS
            if familia == (0, 1):
                manifesto = dict(manifesto)
                manifesto["versao_formato"] = VERSAO_FORMATO
                manifesto.pop("provisorio", None)
            objetos, extras = {}, {}
            for nome in nomes:
                if nome == "manifest.json" or nome.endswith("/"):
                    continue
                achado = _ENTRADA.fullmatch(nome)
                if achado is not None:
                    try:
                        objeto = json.loads(z.read(nome).decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as e:
                        raise ObimInvalido(f"entrada {nome!r} ilegível: {e}") from e
                    objetos.setdefault(achado.group(1), {})[achado.group(2)] = objeto
                else:
                    extras[nome] = z.read(nome)
    except zipfile.BadZipFile as e:
        raise ObimInvalido(f"{Path(caminho).name} não é um ZIP válido") from e
    try:
        lateral = Lateral(objetos)
    except ValueError as e:
        raise ObimInvalido(f"objetos do lateral inválidos: {e}") from e
    if familia == (0, 2):
        validar(lateral)
    return SimpleNamespace(manifesto=manifesto, lateral=lateral, extras=extras,
                           versao_original=versao, somente_leitura=somente_leitura)


def orfaos(lateral, vista_guids, identifications):
    """Ids do lateral que o `.obim` cita e os conjuntos dados (IFC) não têm; só calcula, nunca apaga."""
    vistas, pranchas, viewports = [], [], []
    for ident in lateral.ids("vistas"):
        if lateral.obter("vistas", ident).get("vista_guid") not in vista_guids:
            vistas.append(ident)
    for ident in lateral.ids("pranchas"):
        if lateral.obter("pranchas", ident).get("identification") not in identifications:
            pranchas.append(ident)
    for ident in lateral.ids("viewports"):
        o = lateral.obter("viewports", ident)
        if o.get("vista_guid") not in vista_guids or o.get("prancha") not in identifications:
            viewports.append(ident)
    return {"vistas": vistas, "pranchas": pranchas, "viewports": viewports}


def apagar_vista(lado, vista_guid):
    """Apaga a vista dessa chave e todos os viewports dela na mesma transação (`lado` = `t.lado`)."""
    lateral = getattr(lado, "_lat", lado)
    for ident in list(lateral.ids("vistas")):
        if lateral.obter("vistas", ident).get("vista_guid") == vista_guid:
            lado.apagar("vistas", ident)
    for ident in list(lateral.ids("viewports")):
        if lateral.obter("viewports", ident).get("vista_guid") == vista_guid:
            lado.apagar("viewports", ident)
