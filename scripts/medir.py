"""Executa a série do guia, preservando evidências antes de excluir cada Job."""
import csv
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'resultados'
EVIDENCE = ROOT / 'evidencias'
BASE = ['kubectl', '--context=ops-lab', '-n', 'ops-lab']


def kub(*args):
    return subprocess.check_output(BASE + list(args), text=True, cwd=ROOT)


def save(label, suffix, data):
    (EVIDENCE / f'{label}-{suffix}').write_text(data)


def counts(raw):
    return {m[0]: (int(m[1]), int(m[2])) for m in re.findall(
        r'\[pod/([^/]+)/rotas\].*total_aceitos=(\d+) total_recusados=(\d+)', raw)}


def main():
    OUT.mkdir(exist_ok=True)
    EVIDENCE.mkdir(exist_ok=True)
    for label, replicas in [('3pods-a', 3), ('1pod-a', 1), ('2pods-a', 2),
                            ('2pods-b', 2), ('3pods-b', 3), ('1pod-b', 1),
                            ('1pod-c', 1), ('2pods-c', 2), ('3pods-c', 3)]:
        logpath = OUT / f'{label}.txt'
        if logpath.exists():
            raise RuntimeError(f'Evidência já existe: {logpath}; não sobrescrever')
        if kub('get', 'job', 'carga', '--ignore-not-found').strip():
            raise RuntimeError('Já existe um Job carga; preservar e inspecionar')
        print(f'INICIO {label}: {replicas} réplicas', flush=True)
        kub('scale', 'deployment/rotas', f'--replicas={replicas}')
        kub('rollout', 'status', 'deployment/rotas', '--timeout=180s')
        deadline = time.monotonic() + 120
        while True:
            pods = json.loads(kub('get', 'pods', '-l', 'app=rotas', '-o', 'json'))['items']
            eps = json.loads(kub('get', 'endpointslices', '-l', 'kubernetes.io/service-name=rotas', '-o', 'json'))
            ready = [e for s in eps['items'] for e in s['endpoints'] if e['conditions'].get('ready')]
            if len(pods) == replicas and len(ready) == replicas and not any(p['metadata'].get('deletionTimestamp') for p in pods):
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Cluster não convergiu')
            time.sleep(3)
        save(label, 'endpoints.json', json.dumps(eps, indent=2))
        before = kub('logs', '-l', 'app=rotas', '--prefix', '--tail=1')
        save(label, 'contadores-antes.txt', before)
        kub('apply', '-f', 'k8s/job-carga.yaml')
        start = time.monotonic()
        samples = []
        while True:
            job = json.loads(kub('get', 'job', 'carga', '-o', 'json'))
            if any(c['type'] in ('Complete', 'Failed') and c['status'] == 'True' for c in job.get('status', {}).get('conditions', [])):
                break
            try:
                raw = kub('get', '--raw', '/apis/metrics.k8s.io/v1beta1/namespaces/ops-lab/pods')
                samples.append({'observed_at': datetime.now(timezone.utc).isoformat(), 'metrics': json.loads(raw)})
            except subprocess.CalledProcessError:
                samples.append({'observed_at': datetime.now(timezone.utc).isoformat(), 'error': 'metrics unavailable'})
            if time.monotonic() - start > 300:
                raise RuntimeError('Job excedeu espera; preservar para diagnóstico')
            time.sleep(15)
        log = kub('logs', 'job/carga')
        logpath.write_text(log)
        save(label, 'job.json', json.dumps(job, indent=2))
        podstate = json.loads(kub('get', 'pods', '-l', 'job-name=carga', '-o', 'json'))
        save(label, 'pod.json', json.dumps(podstate, indent=2))
        save(label, 'recursos.json', json.dumps(samples, indent=2))
        after = kub('logs', '-l', 'app=rotas', '--prefix', '--tail=1')
        save(label, 'contadores-depois.txt', after)
        exitcode = podstate['items'][0]['status']['containerStatuses'][0]['state']['terminated']['exitCode']
        if exitcode not in (0, 99) or 'TOTAL RESULTS' not in log:
            raise RuntimeError(f'{label}: sem resultado válido, saída {exitcode}')
        ok = int(re.search(r'rotas_ok\.+:\s+(\d+)', log)[1])
        failures = re.search(r'falhas\.+:\s+([\d.]+)%\s+(\d+) out of (\d+)', log)
        p95 = re.search(r'latencia_ok\.+:.*?p\(95\)=([\d.]+)(ms|s)', log)
        latency = float(p95[1]) * (1000 if p95[2] == 's' else 1)
        dropped = int(re.search(r"'count==0' count=(\d+)", log)[1])
        b, a = counts(before), counts(after)
        distribution = ', '.join(f'{p}: {v[0]-b.get(p,(0,0))[0]}' for p,v in a.items())
        cpus = {}
        seen = set()
        for sample in samples:
            for item in sample.get('metrics', {}).get('items', []):
                name = item['metadata']['name']
                key = (name, item['timestamp'])
                if not name.startswith('rotas-') or key in seen:
                    continue
                seen.add(key)
                value = item['containers'][0]['usage']['cpu']
                unit = re.search(r'[a-z]+$', value)
                unit = unit[0] if unit else ''
                millicores = float(value[:-len(unit)] if unit else value) * {'n': 1e-6, 'u': .001, 'm': 1, '': 1000}[unit]
                cpus.setdefault(name, []).append(millicores)
        cpu_text = ', '.join(f'{p}: pico {max(v):.1f}m' for p,v in cpus.items())
        table = ROOT / 'resultados_modelo.csv'
        with table.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f, delimiter=';'); fields = reader.fieldnames; rows = list(reader)
        row = next(r for r in rows if r['rotulo'] == label)
        row.update(taxa='6', rotas_ok=str(ok), sucessos_por_s=f'{ok/60:.4f}', falhas_pct=failures[1],
                   p95_latencia_ok_ms=f'{latency:.2f}', dropped_iterations_medicao=str(dropped),
                   status_job=f'{"Failed" if exitcode else "Complete"} (exit {exitcode})',
                   cpu_observada_por_pod=cpu_text, distribuicao_aceitos_por_pod=distribution,
                   observacoes=f'{failures[2]}/{failures[3]} falhas. Contadores incluem aquecimento; CPU é amostrada e pode incluir início/fim.')
        with table.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter=';'); writer.writeheader(); writer.writerows(rows)
        print(f'FIM {label}: {ok/60:.2f} sucessos/s, falhas {failures[1]}%, p95 {latency:.2f} ms, descartes {dropped}', flush=True)
        kub('delete', 'job', 'carga', '--wait=true')


if __name__ == '__main__':
    main()
