# RotaExpress — análise do experimento

Atividade executada em 22/10/2026. A aplicação foi empacotada, publicada no Kubernetes, acessada por Service, submetida a uma implantação com erro e recuperada por rollback. Foram realizados um piloto e nove testes comparativos.

## 1. Cenário e método

- Computador: Ubuntu 26.04 LTS, Intel Core i5-13420H, 12 CPUs lógicas e aproximadamente 14,8 GiB de RAM. Detalhes em [ambiente.json](evidencias/ambiente.json).
- Docker 29.1.3, Minikube 1.39.0 e Kubernetes 1.37.0, com um único nó no perfil `ops-lab`.
- Limites do contêiner do nó: 3 CPUs e 3 GiB. O limite de CPU precisou ser aplicado com `docker update --cpus=3 ops-lab`; o Minikube não o havia efetivado. O Kubernetes continuou anunciando 12 CPUs e a memória do host, o que afeta o exercício de agendamento e os percentuais de recursos.
- Aplicação `rotas:1.0`: cada Pod solicita 500m de CPU e 64Mi de memória, com limites de 500m e 128Mi. Um cálculo por vez, sem fila nem cache.
- k6 1.0.0 em um Job: solicita 250m de CPU e 128Mi, com limites de 500m e 256Mi. O script foi fornecido por ConfigMap e acessou `http://rotas:8000`.
- Carga fixa: 6 pedidos/s, nove entregas por rota e 60 segundos medidos. Há 10 segundos de aquecimento; a janela medida começa aos 20 segundos.
- Três repetições por configuração, na ordem A: 3/1/2, B: 2/3/1 e C: 1/2/3. Antes de cada teste, foi verificada a convergência dos Pods e dos endpoints prontos. Apenas a quantidade de réplicas mudou durante a série.
- Metas: falhas < 1%, p95 das respostas válidas < 800 ms e zero iterações descartadas na medição.

O piloto justificou manter a taxa de 6/s: houve 92 rotas válidas, 74,51% de falhas e nenhum descarte pelo gerador. Essa carga permitiu observar diferenças entre as configurações. O piloto não entrou nas medianas.

No piloto, o metrics-server coletava a cada 60 segundos, produzindo amostras repetidas e pouco úteis. Antes da série, seu intervalo foi alterado para 15 segundos; as evidências da série contêm horários de coleta distintos. Nenhum parâmetro da aplicação ou do k6 foi alterado por esse ajuste.

## 2. Evidências

### Nove execuções

| Teste | Pods | Rotas válidas | Sucessos/s | Falhas | p95 válido (ms) | Descartes |
|---|---:|---:|---:|---:|---:|---:|
| 3pods-a | 3 | 202 | 3,3667 | 43,88% | 573,58 | 0 |
| 1pod-a | 1 | 87 | 1,4500 | 75,83% | 785,25 | 0 |
| 2pods-a | 2 | 176 | 2,9333 | 51,11% | 590,89 | 0 |
| 2pods-b | 2 | 175 | 2,9167 | 51,52% | 620,07 | 0 |
| 3pods-b | 3 | 204 | 3,4000 | 43,49% | 559,45 | 0 |
| 1pod-b | 1 | 84 | 1,4000 | 76,73% | 810,78 | 0 |
| 1pod-c | 1 | 87 | 1,4500 | 75,90% | 757,18 | 0 |
| 2pods-c | 2 | 164 | 2,7333 | 54,57% | 622,24 | 0 |
| 3pods-c | 3 | 215 | 3,5833 | 40,27% | 571,66 | 0 |

Todas as nove execuções produziram resumo completo e terminaram com código 99: metas não atingidas, e não falha de execução do k6. Todas falharam no critério de falhas; `1pod-b` também falhou no critério de latência.

### Medianas e custo por configuração

| Pods | Sucessos/s | Falhas | p95 válido (ms) | Descartes | CPU solicitada/limitada | Memória solicitada / limite |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 1,45 | 75,90% | 785,25 | 0 | 0,5 CPU | 64 / 128 MiB |
| 2 | 2,9167 | 51,52% | 620,07 | 0 | 1 CPU | 128 / 256 MiB |
| 3 | 3,40 | 43,49% | 571,66 | 0 | 1,5 CPU | 192 / 384 MiB |

Custos da tabela referem-se somente à aplicação. O gerador e os componentes do cluster consomem recursos adicionais. Os valores são medianas calculadas separadamente por coluna; o p95 é a mediana dos três p95, não um percentil recalculado sobre todas as requisições juntas. Sucessos/s = rotas válidas / 60; não foi usado o `/s` que o k6 imprime sobre o tempo total.

### CPU e distribuição

Os picos amostrados com um Pod foram 478,2m, 482,8m e 479,6m nas rodadas A, B e C: próximos do limite de 500m. Nos testes com dois Pods, os picos por Pod variaram de 363,4m a 479,0m; com três, de 263,1m a 387,3m. Essas são amostras, não máximos instantâneos nem prova de saturação contínua. As coletas podem abranger início/fim e aquecimento; a série bruta inclui timestamps e janelas para auditoria.

Exemplos de rotas aceitas por Pod, obtidas subtraindo contadores antes/depois:

| Teste | Aceitos por Pod, incluindo aquecimento |
|---|---|
| 2pods-a | 97 e 106 |
| 3pods-a | 93, 68 e 75 |
| 3pods-b | 78, 76 e 85 |
| 3pods-c | 83, 83 e 85 |

Todos os Pods receberam trabalho, sem obrigação de divisão idêntica. Esses contadores incluem aquecimento, por isso não somam o mesmo total de `rotas_ok` da janela medida. Nomes completos e diferenças de contadores estão no CSV e nos arquivos de cada execução.

## 3. Explicação dos resultados

Observado: de um para dois Pods, a mediana de sucessos/s praticamente dobrou. De dois para três, o ganho foi de aproximadamente 16,6%, com aumento de 50% na CPU solicitada. Três Pods atingiram cerca de 2,34 vezes o atendimento de um Pod, consumindo três vezes a CPU solicitada. As falhas diminuíram, mas permaneceram muito acima de 1%.

O código fornece uma explicação para as recusas: cada Pod aceita somente um cálculo por vez e devolve 503 quando ocupado. O Service distribui conexões sem consultar essa ocupação; uma solicitação pode chegar a um Pod ocupado mesmo quando outro estiver livre. Adicionar réplicas aumenta o paralelismo, mas não cria uma fila nem coordena a distribuição por disponibilidade do calculador.

As amostras próximas de 500m em uma réplica são compatíveis com a limitação de CPU por Pod. Com três réplicas, a menor utilização média por Pod não significa ausência de recusas: a distribuição temporal dos pedidos e os intervalos ociosos também importam. Não foi instrumentado cada instante de ocupação, portanto não é possível atribuir numericamente todas as falhas a um único fator. Disputa por recursos do computador é uma hipótese adicional, não demonstrada isoladamente.

O p95 considera apenas respostas válidas. Uma configuração com p95 baixo e muitas recusas continua oferecendo atendimento insuficiente. Nenhum descarte do k6 foi observado: as falhas não decorreram de o gerador deixar de iniciar a demanda programada.

### Limite do nó

O pedido de seis réplicas previsto no guia resultou em seis Pods prontos. O scheduler considera os recursos anunciados pelo Kubernetes, que neste ambiente são 12 CPUs, embora o consumo do contêiner esteja limitado a 3 CPUs pelo Docker.

Para demonstrar a restrição de agendamento, após a série foi solicitado temporariamente um total de 25 réplicas, sem teste de carga. Só a aplicação solicitava 12,5 CPUs. Foram observados 22 Pods em execução e três `Pending`, com eventos `FailedScheduling` e `Insufficient cpu`. Os componentes do cluster também possuem requests. Depois, o Deployment foi restaurado para uma réplica.

Evidências: [seis Pods](evidencias/limite-6pods.txt), [25 Pods](evidencias/limite-25pods.txt), [eventos](evidencias/limite-eventos.txt) e [recursos do nó](evidencias/limite-no-25pods.txt). A adaptação não alterou a série de medições, que já estava concluída.

## 4. Decisão operacional

Entre as opções medidas, adotaria **três Pods como mitigação temporária**, pois apresentaram o maior atendimento e o menor percentual de falhas, com custo de 1,5 CPU solicitada, 192 MiB de memória solicitada e limite agregado de 384 MiB. O ganho sobre dois Pods é modesto para os 0,5 CPU adicionais, mas melhora o atendimento sob esta demanda.

**Nenhuma configuração está aprovada para atender 6 pedidos/s dentro das metas.** Não seria correto declarar sucesso apenas porque o p95 mediano ficou abaixo de 800 ms. Mesmo a melhor configuração recusou aproximadamente 43% das tentativas na mediana.

Próximas investigações propostas, ainda não executadas: otimizar o cálculo; avaliar fila limitada com controle de espera, medindo o efeito no p95; testar distribuição que considere ocupação; e medir a taxa sustentável abaixo de 1% de falhas. Também é necessário alinhar a capacidade anunciada pelo nó aos limites reais antes de extrapolar dimensionamento ou introduzir autoscaling. Aumentar réplicas indiscriminadamente não cria capacidade física.

Três Pods no mesmo nó não protegem contra a perda desse nó. Este trabalho avalia atendimento sob carga, não recuperação de desastre nem disponibilidade entre zonas.

## Arquivos e verificação

- [Manifestos](k8s/): Namespace, Deployment, Service e Job.
- [Tabela completa](resultados_modelo.csv) e [medianas](evidencias/medianas.csv).
- `resultados/<teste>.txt`: saída integral do k6.
- `evidencias/<teste>-job.json` e `-pod.json`: estado final e código de saída.
- `evidencias/<teste>-recursos.json`: métricas com horários de coleta.
- `evidencias/<teste>-contadores-antes.txt` e `-contadores-depois.txt`: distribuição.
- `scripts/medir.py`: execução sequencial; recusa sobrescrever evidências existentes.
- `python3 scripts/resumir.py`: verifica as nove execuções contra os logs e recalcula medianas, sem precisar do cluster.

O encerramento é registrado em `evidencias/encerramento.txt`. Os arquivos locais permanecem disponíveis após a remoção do namespace e a parada do cluster.
