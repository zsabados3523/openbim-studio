# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gravação do par `Casa.ifc` + `Casa.obim` com diário de gravação (ADR-002 §4.3, §4.5 e §4.8).
O IFC é carimbado com `Revisao` + 1 e `LadoId` por `Historico.fora_do_historico`; o resto roda em `ler()`. IFC e lateral são preparados,
o `gravacao.json` entra por troca atômica e só então os dois são confirmados (IFC primeiro). Falha antes do diário volta o carimbo; depois
dele o resolvedor roda na hora. Sem Qt, sem `obimcore` e sem importar `diario.py`."""
import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import ifcopenshell.api

from . import gravacao_atomica as GA
from . import obim_zip

VERSAO_FORMATO = obim_zip.VERSAO_FORMATO
VERSAO_PROGRAMA = "0.1.0"
FORMATO = "obim-lateral"
_PSET = "OBIM_Projeto"


def _sha(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _resumo(caminho):
    h, tamanho = hashlib.sha256(), 0
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
            tamanho += len(bloco)
    return h.hexdigest(), tamanho


def _resumo_ou_nada(caminho):
    return _resumo(caminho) if Path(caminho).exists() else (None, None)


def _mesmo(a, b):
    return os.path.normcase(os.path.abspath(os.fspath(a))) == os.path.normcase(os.path.abspath(os.fspath(b)))


def _tmp(destino):
    return Path(destino).with_name(Path(destino).name + ".tmp")


def _bak(destino):
    return Path(destino).with_name(Path(destino).name + ".bak")


def _obim(destino):
    return Path(destino).with_suffix(".obim")


def _pset(arquivo):
    projetos = arquivo.by_type("IfcProject")
    if not projetos:
        raise RuntimeError("o IFC não tem IfcProject")
    proj = projetos[0]
    for rel in proj.IsDefinedBy or ():
        if rel.is_a("IfcRelDefinesByProperties"):
            pd = rel.RelatingPropertyDefinition
            if pd.is_a("IfcPropertySet") and pd.Name == _PSET:
                return proj, pd
    return proj, None


def _valores(ps):
    v = {}
    if ps is not None:
        for prop in ps.HasProperties or ():
            if prop.is_a("IfcPropertySingleValue") and prop.NominalValue is not None:
                v[prop.Name] = prop.NominalValue.wrappedValue
    return v


def _ler_carimbo(sessao):
    with sessao.ler() as arquivo:
        _, ps = _pset(arquivo)
        v = _valores(ps)
        return ps is not None, v.get("LadoId"), v.get("Revisao")


def _editar_carimbo(sessao, historico, lado, revisao, remover=False):
    with sessao.escrever() as esc:
        with historico.fora_do_historico(esc):
            arquivo = esc.arquivo
            proj, ps = _pset(arquivo)
            if remover:
                if ps is not None:
                    ifcopenshell.api.run("pset.remove_pset", arquivo, product=proj, pset=ps)
                return
            if ps is None:
                ps = ifcopenshell.api.run("pset.add_pset", arquivo, product=proj, name=_PSET)
            props = {k: v for k, v in (("LadoId", lado), ("Revisao", revisao)) if v is not None}
            ifcopenshell.api.run("pset.edit_pset", arquivo, pset=ps, properties=props)


def _manifesto(destino, prep, projeto, lado_id, revisao, autosave=False, origem_ifc_sha256=None, base=None):
    man = dict(base or {})
    man.update({"formato": FORMATO, "versao_formato": VERSAO_FORMATO, "LadoId": lado_id,
                "Revisao": revisao, "ifc_nome": Path(destino).name, "ifc_sha256": prep.sha256, "ifc_tamanho": prep.tamanho,
                "ifc_projeto_globalid": projeto.GlobalId, "programa_versao": VERSAO_PROGRAMA,
                "data": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    man.pop("provisorio", None)
    if autosave:
        man["autosave"] = True
        man["origem_ifc_sha256"] = origem_ifc_sha256
    else:
        man.pop("autosave", None)
        man.pop("origem_ifc_sha256", None)
    return man


def _escrever_obim(caminho, lateral, manifesto, extras=None):
    obim_zip.escrever(caminho, lateral, manifesto, extras)


def _manifesto_bruto(obim):
    try:
        with zipfile.ZipFile(obim) as z:
            man = json.loads(z.read("manifest.json").decode("utf-8"))
    except Exception:  # noqa: BLE001  (sem ZIP ou sem manifesto legível não há versão confiável)
        return {}
    return man if isinstance(man, dict) else {}


def _ler_existente(obim):
    if not Path(obim).exists():
        return {}, {}
    try:
        lido = obim_zip.ler(obim)
    except obim_zip.ObimInvalido:
        man = _manifesto_bruto(obim)
        familia = obim_zip._familia(man.get("versao_formato")) if man.get("formato") == FORMATO else None
        if familia is not None and familia not in obim_zip._FAMILIAS:
            raise ValueError(f"Não foi possível gravar {Path(obim).name}: o arquivo é de uma versão mais nova do que esta.") from None
        return {}, {}
    if lido.somente_leitura:
        raise ValueError(f"Não foi possível gravar {Path(obim).name}: o arquivo é da versão {lido.versao_original}, mais nova do que esta.")
    return lido.manifesto, lido.extras


def _conferir_obim(caminho):
    try:
        with zipfile.ZipFile(caminho) as z:
            nomes = z.namelist()
            for nome in nomes:
                if obim_zip._perigosa(nome):
                    raise ValueError(f"entrada com caminho perigoso no ZIP do lateral: {nome!r}")
            if "manifest.json" not in nomes:
                raise ValueError("ZIP do lateral sem manifest.json")
            man = json.loads(z.read("manifest.json").decode("utf-8"))
            if not isinstance(man, dict) or man.get("formato") != FORMATO or man.get("versao_formato") != VERSAO_FORMATO:
                raise ValueError("manifesto do lateral fora do formato")
    except zipfile.BadZipFile as e:
        raise ValueError(f"{Path(caminho).name} não é um ZIP válido") from e


def _conferir_temporario(prep):
    if not prep.temporario.exists():
        raise GA.FalhaGravacao("conferir", "conferencia", prep.destino, False,
                              f"Não foi possível gravar {prep.destino.name}: o temporário {prep.temporario} desapareceu.")
    sha, tamanho = _resumo(prep.temporario)
    if sha != prep.sha256 or tamanho != prep.tamanho:
        raise GA.FalhaGravacao("conferir", "conferencia", prep.destino, False,
                              f"Não foi possível gravar {prep.destino.name}: o temporário {prep.temporario} mudou antes da confirmação.")


def _dados_gravacao(destino, obim, ifc_prep, obim_prep, ifc_antigo, obim_antigo, lado_id, revisao, seq):
    return {"versao": 1, "lado_id": lado_id, "Revisao": revisao, "seq": seq,
            "ifc": {"caminho": str(Path(destino).absolute()), "temporario": str(_tmp(destino).absolute()),
                    "antigo_sha256": ifc_antigo[0], "antigo_tamanho": ifc_antigo[1],
                    "novo_sha256": ifc_prep.sha256, "novo_tamanho": ifc_prep.tamanho},
            "obim": {"caminho": str(Path(obim).absolute()), "temporario": str(_tmp(obim).absolute()),
                     "antigo_sha256": obim_antigo[0], "antigo_tamanho": obim_antigo[1],
                     "novo_sha256": obim_prep.sha256, "novo_tamanho": obim_prep.tamanho}}


def _gravar_gravacao(pasta, dados):
    pasta, alvo, tmp = Path(pasta), Path(pasta) / "gravacao.json", Path(pasta) / "gravacao.json.tmp"
    texto = json.dumps(dados, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    with open(tmp, "wb") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(alvo))


def _apagar(path, faltando_ok=False):
    try:
        os.unlink(str(path))
    except FileNotFoundError:
        if not faltando_ok:
            raise


def _limpar_gravacao(pasta, manter_json=False):
    pasta = Path(pasta)
    for p in sorted(pasta.glob("gravacao*")):
        if manter_json and p.name == "gravacao.json":
            continue
        _apagar(p, faltando_ok=True)


def _limpar_antes(pasta, destino, obim):
    GA.limpar_temporarios(destino)
    GA.limpar_temporarios(obim)
    _limpar_gravacao(pasta)


def _reverter_carimbo(sessao, historico, existia, lado, revisao):
    _editar_carimbo(sessao, historico, lado, revisao, remover=not existia)


def _resolver_antes_de_gravar(destino, pasta, ao_concluir):
    try:
        resultado = resolver_gravacao_pendente(pasta, destino, ao_concluir)
    except Exception as e:
        raise RuntimeError(f"Não foi possível gravar {destino.name}: a gravação pendente em {pasta / 'gravacao.json'} não pôde ser resolvida.") from e
    if resultado not in ("concluido", "desfeito", "sem_pendencia"):
        raise RuntimeError(f"Não foi possível gravar {destino.name}: a gravação pendente em {pasta / 'gravacao.json'} não pôde ser resolvida ({resultado}).")
    return resultado


def gravar_par(sessao, historico, lateral, destino, pasta_projeto, lado_id, seq, carimbo=True, ao_concluir=None,
               autosave=False, origem_ifc_sha256=None):
    """Grava o par; carimba `Revisao` + 1 e `LadoId` (o definitivo = o provisório). Devolve os dois `Gravado`."""
    destino, obim, pasta = Path(destino), _obim(destino), Path(pasta_projeto)
    _resolver_antes_de_gravar(destino, pasta, None if autosave else ao_concluir)
    obim_zip.validar(lateral)
    base_man, extras = _ler_existente(obim)
    existia, lado_antes, revisao_antes = _ler_carimbo(sessao)
    if carimbo:
        novo_lado = lado_antes if lado_antes is not None else lado_id
        nova_revisao = revisao_antes + 1 if isinstance(revisao_antes, int) else 1
        _editar_carimbo(sessao, historico, novo_lado, nova_revisao)
    else:
        novo_lado = lado_antes if lado_antes is not None else lado_id
        nova_revisao = revisao_antes if isinstance(revisao_antes, int) else 0
    ifc_antigo, obim_antigo = _resumo_ou_nada(destino), _resumo_ou_nada(obim)
    etapa, com_gravacao = "antes", False
    try:
        with sessao.ler() as arquivo:
            proj = arquivo.by_type("IfcProject")[0]
            seq_val = seq() if callable(seq) else seq
            ifc_prep = GA.preparar(destino, lambda tmp: arquivo.write(str(tmp)), conferir=GA.conferir_ifc)
            manifesto = _manifesto(destino, ifc_prep, proj, novo_lado, nova_revisao,
                                   autosave=autosave, origem_ifc_sha256=origem_ifc_sha256, base=base_man)
            obim_prep = GA.preparar(obim, lambda tmp: _escrever_obim(tmp, lateral, manifesto, extras), conferir=_conferir_obim)
            _gravar_gravacao(pasta, _dados_gravacao(destino, obim, ifc_prep, obim_prep, ifc_antigo, obim_antigo,
                                                    novo_lado, nova_revisao, seq_val))
            com_gravacao, etapa = True, "gravacao"
            _conferir_temporario(ifc_prep)
            gravado_ifc = GA.confirmar(ifc_prep)
            _conferir_temporario(obim_prep)
            gravado_obim = GA.confirmar(obim_prep)
            etapa = "ao_concluir"
            if ao_concluir is not None:
                ao_concluir(seq_val)
            etapa = "trocado"
            os.unlink(str(pasta / "gravacao.json"))
    except BaseException:
        if not com_gravacao:
            _limpar_antes(pasta, destino, obim)
            if carimbo:
                _reverter_carimbo(sessao, historico, existia, lado_antes, revisao_antes)
            raise
        if etapa == "ao_concluir":
            raise
        try:
            resultado = resolver_gravacao_pendente(pasta, destino, ao_concluir)
        except Exception:  # noqa: BLE001  (o diário fica para a próxima abertura)
            resultado = None
        if resultado == "desfeito" and carimbo:
            _reverter_carimbo(sessao, historico, existia, lado_antes, revisao_antes)
        raise
    return gravado_ifc, gravado_obim


def _conferir_temp_de(destino, dados):
    tmp = _tmp(destino)
    if not tmp.exists():
        return False
    sha, tamanho = _resumo(tmp)
    return sha == dados["novo_sha256"] and tamanho == dados["novo_tamanho"]


def _confirmar_um(destino, dados):
    prep = GA.Preparado(Path(destino), _tmp(destino), dados["novo_sha256"], dados["novo_tamanho"])
    _conferir_temporario(prep)
    return GA.confirmar(prep)


def _voltar(destino, dados):
    """Volta o destino ao par antigo só com o `.bak` desta gravação (sha = antigo) ou, na primeira, apaga o novo; False se não dá."""
    destino, bak, antigo = Path(destino), _bak(destino), dados["antigo_sha256"]
    if antigo is None:
        if destino.exists() and _sha(destino) == dados["novo_sha256"]:
            os.unlink(str(destino))
            return True
        return False
    if not bak.exists() or _sha(bak) != antigo:
        return False
    tmp = _tmp(destino)
    shutil.copyfile(bak, tmp)
    with open(tmp, "rb+") as f:
        os.fsync(f.fileno())
    os.replace(str(tmp), str(destino))
    return True


def _terminar(pasta, destino, obim, seq, ao_concluir, desfazer=False):
    GA.limpar_temporarios(destino)
    GA.limpar_temporarios(obim)
    if not desfazer and ao_concluir is not None:
        ao_concluir(seq)
    os.unlink(str(Path(pasta) / "gravacao.json"))


def resolver_gravacao_pendente(pasta_projeto, destino, ao_concluir=None):
    """Resolve o `gravacao.json` (E1 a E10, ADR-002 §4.5): conclui, desfaz ou não mexe (E9/E10). É idempotente."""
    destino, obim, pasta = Path(destino), _obim(destino), Path(pasta_projeto)
    gravacao = pasta / "gravacao.json"
    if not gravacao.exists():
        _limpar_antes(pasta, destino, obim)
        return "sem_pendencia"
    try:
        dados = json.loads(gravacao.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  (diário ilegível fica para inspeção)
        return "gravacao_ilegivel"
    if not (_mesmo(dados["ifc"]["caminho"], destino) and _mesmo(dados["obim"]["caminho"], obim)):
        return "outro_caminho"
    atual = {}
    for chave, caminho in (("ifc", destino), ("obim", obim)):
        e = dados[chave]
        if caminho.exists():
            sha = _sha(caminho)
            if sha not in (e["antigo_sha256"], e["novo_sha256"]):
                return "destino_alterado"
            atual[chave] = sha
        elif e["antigo_sha256"] is not None:
            return "destino_alterado"
        else:
            atual[chave] = None
    ifc_novo = atual["ifc"] == dados["ifc"]["novo_sha256"]
    obim_novo = atual["obim"] == dados["obim"]["novo_sha256"]
    if ifc_novo and obim_novo:
        _terminar(pasta, destino, obim, dados["seq"], ao_concluir)
        return "concluido"
    if ifc_novo:
        if _conferir_temp_de(obim, dados["obim"]):
            _confirmar_um(obim, dados["obim"])
            _terminar(pasta, destino, obim, dados["seq"], ao_concluir)
            return "concluido"
        if not _voltar(destino, dados["ifc"]):
            return "destino_alterado"
        _terminar(pasta, destino, obim, dados["seq"], ao_concluir, desfazer=True)
        return "desfeito"
    if obim_novo:
        if _conferir_temp_de(destino, dados["ifc"]):
            _confirmar_um(destino, dados["ifc"])
            _terminar(pasta, destino, obim, dados["seq"], ao_concluir)
            return "concluido"
        if not _voltar(obim, dados["obim"]):
            return "destino_alterado"
        _terminar(pasta, destino, obim, dados["seq"], ao_concluir, desfazer=True)
        return "desfeito"
    if _conferir_temp_de(destino, dados["ifc"]) and _conferir_temp_de(obim, dados["obim"]):
        _confirmar_um(destino, dados["ifc"])
        _confirmar_um(obim, dados["obim"])
        _terminar(pasta, destino, obim, dados["seq"], ao_concluir)
        return "concluido"
    _terminar(pasta, destino, obim, dados["seq"], ao_concluir, desfazer=True)
    return "desfeito"
