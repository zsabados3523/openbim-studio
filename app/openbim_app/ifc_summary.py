# SPDX-License-Identifier: AGPL-3.0-or-later
"""Resumo de um arquivo IFC: nome, esquema, total de elementos e contagem por classe (F0-S02-T05)."""
import os
from collections import Counter
from dataclasses import dataclass, field

import ifcopenshell


class IfcSummaryError(Exception):
    """Falha ao abrir o IFC; a mensagem já está em pt-BR e pronta para o usuário."""


@dataclass(frozen=True)
class IfcSummary:
    file_name: str
    schema: str  # IFC2X3, IFC4, IFC4X3
    total: int  # instâncias de IfcProduct
    by_class: dict = field(default_factory=dict)  # classe -> contagem


def count_by_class(path):
    """Abre o IFC em `path` e devolve um IfcSummary; levanta IfcSummaryError se não der."""
    name = os.path.basename(str(path))
    # TEMPORÁRIO: leitura na thread da interface; threads são T3 (ADR-004)
    try:
        model = ifcopenshell.open(str(path))
    except FileNotFoundError:
        raise IfcSummaryError(f"Arquivo não encontrado: {name}") from None
    except Exception:
        raise IfcSummaryError(
            f"Não foi possível abrir \"{name}\": o arquivo não é um IFC válido."
        ) from None
    counts = Counter(e.is_a() for e in model.by_type("IfcProduct"))
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
