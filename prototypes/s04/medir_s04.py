# SPDX-License-Identifier: AGPL-3.0-or-later
"""S04-T12: ferramenta que lê `medicao.json` do fluxo A (e do B), aplica as metas M2 a M5, compara os IFCs do passo 7, calcula M6 e conta linhas (M7).
ESQUELETO: o implementador completa. O contrato (linha de comando, JSON e regras) está no cabeçalho de `tests/test_s04_metas.py`; o implementador não edita o oráculo.
Só biblioteca padrão, numpy e ifcopenshell. Os tempos vêm dos tempos brutos (não confiar no campo `metas` gravado pelos fluxos)."""
import argparse
import sys


def primeiro_quadro(relogio, sequencia):
    """Tempo (ms) do primeiro quadro de `relogio` ([[t_ms, seq], ...] em ordem de tempo) com seq >= `sequencia`, ou None.
    A sequência CAI a 0 durante o reenvio da cena: não supor que seja crescente."""
    raise NotImplementedError("S04-T12: medir_s04.primeiro_quadro")


def contar_linhas(raiz):
    """{"obimcore": n, "fluxo_a": n, "fluxo_b": n}: linhas de código depois de formatar (regra no cabeçalho do oráculo)."""
    raise NotImplementedError("S04-T12: medir_s04.contar_linhas")


def avaliar(pasta_a, pasta_b=None, estrito=False):
    """Dicionário do JSON de saída (`metas`, `erros`, `m6`, `saida_igual`, `aprovado`); levanta ValueError em entrada inválida."""
    raise NotImplementedError("S04-T12: medir_s04.avaliar")


def main(argv=None):
    p = argparse.ArgumentParser(description="S04-T12: metas, saída igual, M6 e linhas")
    p.add_argument("--a")
    p.add_argument("--b")
    p.add_argument("--estrito", action="store_true")
    p.add_argument("--json")
    p.add_argument("--linhas", action="store_true")
    p.add_argument("--raiz")
    p.parse_args(argv)
    raise NotImplementedError("S04-T12: medir_s04.main")


if __name__ == "__main__":
    sys.exit(main())
