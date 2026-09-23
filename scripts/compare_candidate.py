"""Paired b70e366 comparison. Synthetic models exist only in this evaluator."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import Agent
from environment import make_environment
from scoring_core import CHANNELS, score_campaigns, sanitize_campaigns
from local_eval import evaluate_agent
from scripts.evaluate import RecordingAgent, violations


def baseline_agent():
    # Isolated names prevent the baseline importing the modified policy/planner.
    for name in ('contracts', 'planning', 'policy', 'agent'):
        source = subprocess.check_output(['git', 'show', f'b70e366:{name}.py'], cwd=ROOT, text=True)
        for dependency in ('contracts', 'planning', 'policy'):
            source = source.replace(f'from {dependency} import', f'from baseline_{dependency} import')
        module = types.ModuleType('baseline_' + name)
        module.__file__ = str(ROOT / (name + '.py'))
        sys.modules[module.__name__] = module
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return sys.modules['baseline_agent'].Agent


def synthetic_model(profile, tariffs, scenario, model_seed):
    rng = np.random.default_rng(model_seed)
    rows = []
    for current, segment in sorted(set(map(tuple, profile[["current_tariff", "arpu_segment"]].dropna().values))):
        for target in sorted(tariffs.tariff_plan_code):
            if scenario == 'null': effect, conversion = 0., .5
            elif scenario == 'negative': effect, conversion = -.20, .5
            elif scenario == 'weak': effect, conversion = rng.normal(.04, .08), .5
            elif scenario == 'sparse': effect, conversion = (.9 if rng.random() < .12 else -.12), .5
            elif scenario == 'dense': effect, conversion = rng.normal(.2, .20), rng.uniform(.15, .8)
            elif scenario == 'saturated': effect, conversion = rng.normal(.2, .20), rng.uniform(.85, 1.)
            else: raise ValueError(scenario)
            rows.append((current, segment, target, effect, conversion))
    return pd.DataFrame(rows, columns=['tariff_plan_code_from','arpu_segment','tariff_plan_code_to','arpu_change_pct','conversion_rate'])


def run(cls, scenario, seed, model_seed, profile, tariffs):
    agent = cls()
    wrapped = RecordingAgent(agent)
    start = time.monotonic()
    if scenario == 'mock':
        result = evaluate_agent(wrapped, seed=seed, verbose=False)
    else:
        model = synthetic_model(profile, tariffs, scenario, model_seed)
        fallback = lambda *args: (0., .5)
        env, internals = make_environment(profile, model, tariffs, CHANNELS, 100000, 15000, fallback, seed=seed)
        campaigns = wrapped.act(env)
        assert len(sanitize_campaigns(campaigns, tariffs)) == len(campaigns)
        pilots = internals.executed_pilot_campaigns()
        frame = pd.DataFrame(pilots + campaigns)
        result = score_campaigns(frame, profile, model, tariffs, profile.predicted_arpu.sum(), fallback)
        result['n_pilots'] = len(pilots)
    errors = violations(result, wrapped.campaigns, '')
    events = agent.trace
    requested = [e for e in events if e['event'] == 'pilot_requested']
    return dict(net=result['net_arpu_gain'], cost=result['total_cost'], contacts=result['total_contacts'],
                pilots=result['n_pilots'], final=len(wrapped.campaigns), violations=errors,
                unique_pilots=len({e['candidate_key'] for e in requested}),
                cells=len({tuple(sorted(e['filters'].items())) for e in requested}),
                seconds=time.monotonic()-start)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=10)
    parser.add_argument('--start', type=int, default=0)
    parser.add_argument('--model-seed', type=int, default=20260923)
    parser.add_argument('--scenarios', nargs='+', default=['mock','null','negative','weak','sparse','dense','saturated'])
    parser.add_argument('--out', default='reports/candidate-comparison.json')
    args = parser.parse_args()
    import os
    os.chdir(ROOT)
    baseline = baseline_agent()
    profile, tariffs = pd.read_csv('customer_profile.csv'), pd.read_csv('data/dict_tariff.csv')
    rows = []
    for scenario in args.scenarios:
        for seed in range(args.start, args.start + args.seeds):
            row = dict(scenario=scenario, seed=seed, model_seed=args.model_seed)
            for label, cls in [('baseline', baseline), ('candidate', Agent)]:
                row[label] = run(cls, scenario, seed, args.model_seed, profile, tariffs)
            row['difference'] = row['candidate']['net'] - row['baseline']['net']
            rows.append(row)
            print(f"{scenario} seed={seed}: {row['baseline']['net']:.0f} -> {row['candidate']['net']:.0f} ({row['difference']:+.0f})", flush=True)
    report = dict(baseline='b70e366', model_seed=args.model_seed,
                  source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ['agent.py','policy.py','planning.py']}, rows=rows)
    Path(args.out).write_text(json.dumps(report, indent=2)+'\n')
    return int(any(r[k]['violations'] for r in rows for k in ('baseline','candidate')))

if __name__ == '__main__':
    sys.exit(main())
