<!-- DERIVADO de ci/alignment_report.py. NÃO EDITE À MÃO: regere com
     python ci/alignment_report.py — o --check do CI contradiz qualquer edição manual. -->
# Alinhamento entre departamentos

Matriz derivada do metadado declarado. Ela responde a pergunta que os demais fiscais não
fazem: **o que ficou de fora?**

## Cobertura de risco por capacidade

| Capacidade | risk_level | Riscos que a cobrem |
|---|---|---|
| `CAP-CATALOG` | low | — |
| `CAP-PRICING` | medium | — |

## Componentes

| Componente | Status | Capacidade | Implementa | Coberto por risco |
|---|---|---|---|---|
| `CMP-CATALOG` | verified | `CAP-CATALOG` | — | não |
| `CMP-PRICING` | verified | `CAP-PRICING` | REQ-001 | não |

## Riscos por área

| Área | Total | Abertos |
|---|---|---|
| access | 1 | 0 |
| data | 2 | 0 |
| dependencies | 1 | 0 |
| governance | 9 | 0 |
| webqa | 1 | 0 |

## Pendências de alinhamento

Nenhuma. Todo ativo relevante está coberto ou tem isenção declarada.
