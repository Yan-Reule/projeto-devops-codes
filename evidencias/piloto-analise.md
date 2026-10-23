# Piloto de calibração

Executado em 22/10/2026 com 1 Pod, imagem rotas:1.0, CPU solicitada/limitada em 500m, memória solicitada de 64Mi e limite de 128Mi.

Parâmetros fixados para a série: TAXA=6 pedidos/s, PARADAS=9, DURACAO=60 segundos. O teste usa 10 segundos de aquecimento e inicia a medição aos 20 segundos, pelo Service http://rotas:8000.

## Resultado

| Indicador | Valor |
|---|---|
| Tentativas na medição | 361 |
| Rotas válidas | 92 |
| Sucessos por segundo | 92 / 60 = 1,5333 |
| Falhas | 269 / 361 = 74,51% |
| p95 das respostas válidas | 759,29 ms |
| Iterações descartadas na medição | 0 |
| Job | Failed, saída 99 |

O teste terminou e produziu resumo completo. A saída 99 corresponde à meta de falhas não atingida; não é uma falha de execução do teste. O p95 ficou abaixo de 800 ms e o gerador iniciou toda a demanda programada.

Mantemos 6 pedidos/s: o piloto produziu sucessos suficientes para medir latência e mostrou saturação com uma réplica, sem descartes do gerador. A série comparará a mesma demanda com 1, 2 e 3 Pods; não há garantia de que três Pods atinjam as metas.

Os contadores da aplicação passaram de 4 para 110 aceitos e de 0 para 315 recusados: diferenças de 106 e 315, incluindo aquecimento. Não devem ser comparados diretamente às métricas exclusivas dos 60 segundos medidos.

## Limitação das métricas de recursos

As três consultas a kubectl top retornaram 7m de CPU e 14Mi de memória para a aplicação e não mostraram o Pod do k6. São leituras possivelmente desatualizadas, insuficientes para concluir sobre CPU durante a carga. Verificar atualização do metrics-server antes da série comparativa. Os horários das amostras em piloto-recursos.txt estão em UTC.

O Docker limita o nó a 3 CPUs e 3 GiB, mas o Kubernetes anuncia recursos do host. Considerar essa diferença na interpretação do agendamento e dos percentuais de uso.

## Evidências

- ../resultados/piloto.txt: saída completa do k6.
- piloto-job.json e piloto-pod.json: estado final e código de saída.
- piloto-contadores-antes.txt e piloto-contadores-depois.txt: contadores da aplicação.
- piloto-recursos.txt: amostras de CPU e memória.
- ../resultados_modelo.csv: linha do piloto preenchida; série de nove execuções ainda pendente.
