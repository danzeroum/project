# Política: orientação derivada

Existe uma pergunta que este repositório sabia responder mal:

> *vou mexer nestes arquivos: que etapas isso aciona, que fiscais vão rodar, o que muda junto, e o
> que já está vermelho?*

A resposta existia — espalhada por `CLAUDE.md`, `harness/stages.yaml` e sete políticas. Reuni-la
num guia teria sido a solução óbvia e errada.

## Por que um guia seria a solução errada

Um guia que **enumera** etapas, fiscais e caminhos é uma segunda descrição do repositório. Segunda
descrição deriva da primeira — em silêncio, sem erro, e com a aparência de documentação cuidadosa.
Alguém acrescenta uma etapa em `stages.yaml`, ninguém lembra do guia, e o guia passa a ensinar um
repositório que não existe mais.

Seria o ADR-002 violado exatamente pela ferramenta criada para ensiná-lo.

## A regra

**A orientação deriva; ela não descreve.**

`ci/orient.py` lê o estado vivo e não carrega lista nenhuma:

| O que ele responde | De onde ele tira |
|---|---|
| papel, alvo, âncora | `project.yaml`, `target.lock` |
| etapa dona de um caminho | `harness/stages.yaml:artifacts` |
| fiscais que vão rodar | `harness/stages.yaml:enforced_by` |
| se exige change-proposal | `harness/harness.yaml:protected_paths` |
| pergunta de privacidade | `privacy_lens` da própria etapa |
| o que está vermelho | `validate_all._steps()`, reusado |
| quanto do código tem dono | `ci/inventory_code.py` |

E a skill (`.claude/skills/desenvolver/SKILL.md`) é magra de propósito: ela não contém a
informação, ela manda perguntar. É o que a mantém correta sem manutenção.

`ADR-014-A3` **reprova** id de etapa escrito à mão no `SKILL.md` — a mesma regra que
`stages.schema.json` já aplica a artefato que seja um ID. Vale para o índice, vale para quem
ensina o índice.

## Orientar não é fiscalizar

`orient.py` **sai sempre 0**. Não reprova, não escreve, não julga.

A separação é deliberada. Um orientador que também reprovasse viraria o oitavo fiscal — com regras
próprias, sem política e sem teste de mordida — e seria o primeiro lugar onde alguém tentaria
afrouxar algo, justamente por não parecer um fiscal. Quem reprova é `ci/validate_all.py`.

Pela mesma razão ele reporta **códigos, não laudos**: repetir a saída dos fiscais criaria duas
versões da mesma resposta, e a resumida é a que as pessoas acabariam citando.

## Limite honesto

A skill não ensina julgamento. Ela diz o que roda em cima da mudança; não diz se a mudança é boa.
Se a fronteira de um componente faz sentido, se um risco está bem avaliado, se uma decisão ainda
vale — isso é revisão humana e o agente `conformance` (ADR-012). Prometer que uma página de
markdown responderia é a promessa vazia que o ADR-002 proíbe.

---

Fiscalizado por: `ci/audit_governance.py` (executa as asserções do ADR-014: os artefatos
existem, a skill não restata id de etapa, `ci/orient.py` segue reusando a lista de fiscais de
`ci/validate_all.py` em vez de manter uma cópia, e não reprova nada);
`.github/workflows/governance.yml`.
Declarado em: `architecture/adr/index.yaml`, `.claude/skills/desenvolver/SKILL.md`.
Falha como: orientação que enumera em vez de derivar ⇒ achado `FIND-ADR-014-A3` e exit 1.
Nenhum fiscal novo entra no conjunto: a orientação lê e ordena, quem reprova é a validação total.
