"""Paired baseline/candidate evaluation using only public factories and scorer.

Models here are synthetic test inputs, never inspected by Agent. Baseline Python
modules are loaded from the requested git revision without modifying the checkout.
"""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import types
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import Agent
from environment import make_environment
from mock_environment import CHANNELS, make_mock_env, _mock_fallback, _mock_impact_model
from scoring_core import score_campaigns, sanitize_campaigns
from scripts.evaluate import violations


def baseline_agent(revision):
    saved = {name: sys.modules.get(name) for name in ('contracts', 'planning', 'policy', 'agent')}
    try:
        for name in saved:
            module = types.ModuleType(name)
            module.__file__ = str(ROOT / (name + '.py'))
            sys.modules[name] = module
            source = subprocess.check_output(['git', 'show', f'{revision}:{name}.py'], cwd=ROOT, text=True)
            exec(compile(source, module.__file__, 'exec'), module.__dict__)
        return sys.modules['agent'].Agent
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def synthetic_model(name, profile, tariffs, model_seed=20260923):
    rng = np.random.default_rng(model_seed)
    prices = tariffs.set_index('tariff_plan_code').price_tariff.to_dict()
    rows = []
    for current, segment in sorted(set(profile[['current_tariff', 'arpu_segment']].dropna().itertuples(index=False, name=None))):
        for target in sorted(prices):
            if name == 'negative':
                effect, conversion = -0.12, 0.7
            elif name == 'null':
                effect, conversion = 0., 0.7
            elif name == 'dense_saturated':
                effect, conversion = 0.25, 0.95
            elif name == 'reversed_price':
                effect = 0.5 if prices[target] < prices[current] else -0.2
                conversion = 0.6
            elif name == 'sparse_independent':
                effect = 0.8 if rng.random() < 0.12 else -0.08
                conversion = 0.6
            else:
                raise ValueError(name)
            rows.append((current, target, segment, effect, conversion))
    return pd.DataFrame(rows, columns=['tariff_plan_code_from', 'tariff_plan_code_to',
                                     'arpu_segment', 'arpu_change_pct', 'conversion_rate'])


def evaluate(cls, scenario, seed, profile, tariffs, model):
    if scenario == 'mock':
        env, internals = make_mock_env(seed=seed)
    else:
        env, internals = make_environment(profile, model, tariffs, CHANNELS, 100000, 15000,
                                         _mock_fallback, seed=seed)
    agent = cls()
    with redirect_stdout(io.StringIO()) as captured:
        final = agent.act(env)
        clean = sanitize_campaigns(final, tariffs)
        pilots = internals.executed_pilot_campaigns()
        campaigns = pd.DataFrame(pilots + clean)
        for col in ('filter_arpu_segment', 'filter_data_segment', 'filter_call_segment',
                    'filter_current_tariff', 'explicit_ids'):
            if col not in campaigns:
                campaigns[col] = None
        result = score_campaigns(campaigns, profile, model, tariffs,
                                 profile.predicted_arpu.sum(), _mock_fallback)
    result['n_pilots'] = len(pilots)
    errors = violations(result, final, captured.getvalue())
    return {'net': result['net_arpu_gain'], 'cost': result['total_cost'],
            'contacts': result['total_contacts'], 'pilots': len(pilots),
            'final_campaigns': len(final), 'violations': errors}


def main():
    import os
    os.chdir(ROOT)
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', default='b70e366')
    parser.add_argument('--seeds', default='0,1,2,3,4,5,6,7,8,9,42')
    parser.add_argument('--scenarios', default='mock,negative,null,dense_saturated,reversed_price,sparse_independent')
    parser.add_argument('--model-seed', type=int, default=20260923)
    parser.add_argument('--out', default='reports/redteam/paired.json')
    args = parser.parse_args()
    baseline = baseline_agent(args.baseline)
    profile, tariffs = pd.read_csv('customer_profile.csv'), pd.read_csv('data/dict_tariff.csv')
    rows = []
    for scenario in args.scenarios.split(','):
        model = (_mock_impact_model(pd.read_csv('data/change_tariff.csv')) if scenario == 'mock'
                 else synthetic_model(scenario, profile, tariffs, args.model_seed))
        for seed in map(int, args.seeds.split(',')):
            before = evaluate(baseline, scenario, seed, profile, tariffs, model)
            after = evaluate(Agent, scenario, seed, profile, tariffs, model)
            row = dict(scenario=scenario, seed=seed, baseline=before, candidate=after,
                       delta=after['net']-before['net'])
            rows.append(row)
            print(f'{scenario} {seed}: {before["net"]:.0f} -> {after["net"]:.0f} ({row["delta"]:+.0f})', flush=True)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(baseline=args.baseline, model_seed=args.model_seed, rows=rows), indent=2)+'\n')
    return int(any(r[side]['violations'] for r in rows for side in ('baseline', 'candidate')))

if __name__ == '__main__':
    sys.exit(main())
