# cartographer — inputs

| Lê | Para quê |
|---|---|
| `harness/state/code-inventory.json` | arquivos, símbolos e arestas de import do alvo |
| `harness/state/harvest.json` | o que o alvo já documenta, com proveniência (fase ING-02) |
| `workspace/target/**` | o alvo materializado no SHA do lock — **somente leitura** |
| `project.yaml:target` | raízes de código e de teste declaradas |
| `target.lock` | o SHA que toda proveniência tem de citar |
| `architecture/components.yaml` | o que já foi cartografado, para propor o delta e não o todo |
| `harness/schemas/*.json` | a forma exata do que ele pode escrever |

- `harness/prompts/cartographer-task.md` — o template da tarefa.

Não lê: credenciais, rede, nem nada fora de `workspace/target/` e deste repositório.
