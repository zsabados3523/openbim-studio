# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resumo de um arquivo IFC: nome, esquema, total de elementos e contagem por classe."""
import logging
import os
from collections import Counter
from dataclasses import dataclass, field

import ifcopenshell


log = logging.getLogger("openbim.ifc")


class IfcSummaryError(Exception):
    """Falha ao abrir o IFC; a mensagem já está em pt-BR e pronta para o usuário."""


@dataclass(frozen=True)
class IfcSummary:
    file_name: str
    schema: str  # IFC2X3, IFC4, IFC4X3
    total: int  # instâncias de IfcProduct
    by_class: dict = field(default_factory=dict)  # classe -> contagem


def _erro_do_sistema(exc, name):
    """Mensagem em pt-BR para um erro de leitura do sistema (arquivo em uso, nuvem, permissão, disco)."""
    codigo = getattr(exc, "winerror", None)
    if isinstance(exc, FileNotFoundError):
        return f"Arquivo não encontrado: {name}"
    if isinstance(exc, IsADirectoryError):
        return f"\"{name}\" é uma pasta, não um arquivo IFC."
    if codigo in (32, 33):  # violação de compartilhamento / trava de região: outro programa está usando
        return f"Não foi possível abrir \"{name}\": o arquivo está aberto em outro programa. Feche-o e tente de novo."
    if codigo is not None and 358 <= codigo <= 395:  # erros de arquivo só na nuvem (OneDrive e parecidos)
        return (f"Não foi possível abrir \"{name}\": o arquivo parece estar só na nuvem (OneDrive) e ainda não foi baixado. "
                "Marque \"Sempre manter neste dispositivo\" e tente de novo.")
    if isinstance(exc, PermissionError):
        return f"Não foi possível abrir \"{name}\": sem permissão para ler o arquivo (ou ele está em uso por outro programa)."
    return f"Não foi possível ler \"{name}\": o sistema recusou o acesso ({exc.strerror or type(exc).__name__}). Veja o registro em Ajuda."


def count_by_class(path):
    """Abre o IFC em `path` e devolve um IfcSummary; levanta IfcSummaryError se não der."""
    name = os.path.basename(str(path))
    # Primeiro lê um byte com o Python: separa "não consegui ler o arquivo" (travado, nuvem, permissão) de "não é IFC".
    try:
        with open(str(path), "rb") as f:
            f.read(1)
    except OSError as exc:
        log.warning("Leitura recusada: %s (%s: %s)", path, type(exc).__name__, exc)
        raise IfcSummaryError(_erro_do_sistema(exc, name)) from None
    # TEMPORÁRIO: leitura na thread da interface; threads: ver ADR-004
    try:
        model = ifcopenshell.open(str(path))
    except FileNotFoundError:
        raise IfcSummaryError(f"Arquivo não encontrado: {name}") from None
    except MemoryError:
        log.exception("Sem memória ao abrir %s", path)
        raise IfcSummaryError(
            f"Não foi possível abrir \"{name}\": faltou memória. Feche outros programas e tente de novo."
        ) from None
    except Exception:
        log.exception("Falha ao abrir como IFC: %s", path)
        raise IfcSummaryError(
            f"Não foi possível abrir \"{name}\": o arquivo não é um IFC válido."
        ) from None
    try:
        counts = Counter(e.is_a() for e in model.by_type("IfcProduct"))
    except MemoryError:
        log.exception("Sem memória ao ler %s", path)
        raise IfcSummaryError(
            f"Não foi possível ler \"{name}\": faltou memória. Feche outros programas e tente de novo."
        ) from None
    except Exception:
        log.exception("Falha ao ler o conteúdo de %s", path)
        raise IfcSummaryError(
            f"O arquivo \"{name}\" abriu, mas não foi possível ler os elementos dele. O erro ficou no registro (menu Ajuda)."
        ) from None
    return IfcSummary(
        file_name=name,
        schema=model.schema,
        total=sum(counts.values()),
        by_class=dict(sorted(counts.items())),
    )


def format_summary(summary):
    """Texto simples do resumo, uma classe por linha."""
    lines = [
        f"Arquivo: {summary.file_name}",
        f"Esquema: {summary.schema}",
        f"Total de elementos: {summary.total}",
    ]
    lines += [f"  {cls}: {n}" for cls, n in summary.by_class.items()]
    return "\n".join(lines)
