# Política: alinhamento entre departamentos e cobertura reversa de risco

Todos os fiscais anteriores respondem a mesma forma de pergunta: **o que foi declarado existe?**
Nenhum responde a inversa: **o que existe foi declarado?** — e a segunda é a que descobre lacuna.

A prova está neste repositório. Os treze primeiros riscos eram todos sobre a própria harness. O
enum de `area` traz `availability`, e nenhum risco o usava. O CI ficou verde o tempo todo, porque
nada perguntava o que tinha ficado de fora.

## As quatro regras

| | Reprova quando | O silêncio que ela quebra |
|---|---|---|
| **R1** | capacidade `high`/`critical` sem `RISK-*` que a referencie | risco reconhecido em campo e invisível na governança |
| **R2** | risco `open` sem `treatment`, `owner` e `due` | aberto sem prazo é aceito sem ninguém ter aceitado |
| **R3** | superfície de UI sem `satisfies` | ou o requisito sumiu, ou a tela não deveria existir |
| **R4** | componente concreto sem requisito nem regra verificada | código maduro sem razão registrada |

R2 merece atenção. `open` **soa** como trabalho em andamento, e é exatamente por isso que dura:
ninguém trata como pendência um estado que se anuncia como temporário. O prazo é o que torna a
temporariedade verificável.

## Uma escala só

`risk_level` é a única escala de criticidade de capacidade. Não existe `criticality`, e a ausência
é deliberada: duas escalas para a mesma pergunta começam espelhadas, cada fiscal passa a ler a sua,
e elas divergem sem que nada reprove. Criar essa deriva dentro do fiscal que combate deriva seria
particularmente ruim.

## Isenção honesta

`risk_exemptions[]` exige `ref` e `justification`, e **isenção que não casa ativo algum é achado**
— a mesma propriedade de `stages.yaml:ungoverned` e de `components.yaml:exemptions`. Sem ela a
lista vira o lugar onde a cobertura é fingida com uma linha, e uma isenção morta é pior que
nenhuma: ela consome a atenção de quem revisa sem proteger nada.

## O artefato derivado

`docs/alignment.md` é gerado, com `--check` no CI e escrita manual negada no hook e em
`.claude/settings.json` — como `docs/metadata-graph.md`. A razão é mais forte aqui: a matriz de
alinhamento é exatamente onde alguém teria a tentação de corrigir o **número** em vez do fato.

Regerar: `python ci/alignment_report.py`.

## Onde ele roda

Quinto passo de `ci/validate_all.py`, entre conformidade e LGPD. A ordem não é arbitrária: o
alinhamento pressupõe metadado coerente (senão reportaria ruído derivado do primeiro erro) e
precede o julgamento de privacidade.

## Limite honesto

R4 é a mais opinativa das quatro. Um repositório que usa componentes como agrupamento puramente
técnico — e não como unidade de propósito — vai colidir com ela. A saída declarada é
`risk_exemptions`, com justificativa e sob revisão, **não** afrouxar a regra: um fiscal editado
para o CI passar deixa de ser fiscal.

E nenhuma das quatro julga *qualidade*. R1 verifica que existe risco associado, nunca que o risco
é o certo; R2 verifica que há prazo, nunca que ele é razoável. Essa camada é o agente de
conformidade (ADR-012), e ela produz proposta — jamais correção direta.

---

Fiscalizado por: `ci/alignment_report.py::r1_capacidade_de_alto_risco_sem_risco`,
`::r2_risco_aberto_sem_prazo`, `::r3_superficie_orfa`, `::r4_componente_sem_justificativa`,
`::isencao_morta`; `harness/schemas/risk-register.schema.json` (`open` ⇒ `due`; `risk_exemptions`
com `justification`); `ci/hooks/post_edit_guard.py` (o derivado não se edita à mão);
`.github/workflows/governance.yml`.
Declarado em: `governance/risk-register.yaml`, `architecture/adr/index.yaml`, `harness/stages.yaml`.
Falha como: ativo descoberto, risco aberto sem prazo, órfão ou isenção morta ⇒ achado e exit 1;
`docs/alignment.md` desatualizado ⇒ exit 1; metadado ilegível ⇒ exit 2.
