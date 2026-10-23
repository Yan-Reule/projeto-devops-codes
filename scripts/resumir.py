"""Calcula medianas da série completa e verifica consistência das evidências."""
import csv
import json
import re
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
with (ROOT / 'resultados_modelo.csv').open(encoding='utf-8-sig', newline='') as f:
    rows = [r for r in csv.DictReader(f, delimiter=';') if r['rodada'] in ('A', 'B', 'C')]
assert len(rows) == 9, 'Esperadas nove medições'
summary = []
for replicas in (1, 2, 3):
    group = [r for r in rows if int(r['replicas']) == replicas]
    assert {r['rodada'] for r in group} == {'A', 'B', 'C'}
    for r in group:
        assert r['taxa'] == '6'
        log = (ROOT / 'resultados' / f"{r['rotulo']}.txt").read_text()
        ok = int(re.search(r'rotas_ok\.+:\s+(\d+)', log)[1])
        assert ok == int(r['rotas_ok'])
        assert abs(float(r['sucessos_por_s']) - ok / 60) < .0001
        raw = json.loads((ROOT / 'evidencias' / f"{r['rotulo']}-pod.json").read_text())
        assert raw['items'][0]['status']['containerStatuses'][0]['state']['terminated']['exitCode'] in (0, 99)
    result = {'replicas': replicas, 'cpu_solicitada': replicas * .5,
              'memoria_solicitada_MiB': replicas * 64, 'limite_memoria_MiB': replicas * 128}
    for field in ('sucessos_por_s', 'falhas_pct', 'p95_latencia_ok_ms', 'dropped_iterations_medicao'):
        result[field] = median(float(r[field]) for r in group)
    result['execucoes_com_todas_metas'] = sum(
        float(r['falhas_pct']) < 1 and float(r['p95_latencia_ok_ms']) < 800
        and int(r['dropped_iterations_medicao']) == 0 for r in group)
    summary.append(result)
with (ROOT / 'evidencias' / 'medianas.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(summary[0]), delimiter=';')
    writer.writeheader(); writer.writerows(summary)
print(json.dumps(summary, ensure_ascii=False, indent=2))
print('Verificação concluída: nove medições completas e contagens coerentes com os logs.')
