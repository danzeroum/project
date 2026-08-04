# Comece aqui

Você acabou de clonar este repositório. Uma pergunta decide tudo o que vem depois:

**Este repositório é um molde ou um derivado?** A resposta está em `project.yaml:project.kind` —
não presuma, leia.

```bash
python ci/adoption_status.py     # responde, e diz qual é o próximo passo
python ci/orient.py              # o painel completo: fiscais, cobertura, próximo passo
```

Para saber o que uma mudança aciona antes de fazê-la — etapa dona, fiscais que vão rodar, se
exige change-proposal — use `python ci/orient.py --tocar <caminho>…`. A skill `desenvolver`
embala os dois.

## `kind: mold` — a casca genérica

É o que este repositório é. Ele **não governa alvo algum**, e é isso que o torna reaproveitável
para qualquer um. Se você chegou com o link de um repositório de negócio:

```
/adotar https://github.com/<owner>/<repo>
```

O comando traz o alvo para o escopo da sessão, reconhece o que ele é (branch padrão real,
linguagens, raízes de código), cria o gêmeo de governança `project-<repo>`, ancora-o no SHA
exato do alvo e encadeia o bootstrap. Contrato completo em `.claude/commands/adotar.md`.

## `kind: derived` — o gêmeo de governança de um alvo

```
/bootstrap
```

Materializa o código do alvo em `workspace/target/` no SHA de `target.lock`, instala o que os
fiscais precisam e valida. É idempotente: rodar de novo custa um fetch.

## O que este arquivo deliberadamente não faz

Não descreve as etapas do pipeline. Por ADR-002, **enforcement não mora em markdown**: uma regra
escrita aqui e implementada ali vira duas fontes que derivam em silêncio. As etapas, seus
fiscais e sua ordem moram em `harness/stages.yaml` e nos scripts de `ci/`; esta página só aponta
para a porta certa.

## Antes de encerrar qualquer tarefa

```bash
python ci/validate_all.py
```

`0` conforme · `1` divergência entre o declarado e o real · `2` algum fiscal não conseguiu
fiscalizar. É exatamente o que `.github/workflows/governance.yml` roda.

## Onde ler mais

`README.md` (arquitetura) · `CLAUDE.md` (doutrina operacional) ·
`docs/PLANO-MOLDE-VIVO.md` (para onde isto está indo) ·
`docs/COMO-ADOTAR.md` (playbook de adoção) · `harness/policies/` (as regras e seus fiscais).
