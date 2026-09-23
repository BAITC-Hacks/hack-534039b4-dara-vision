"""Paired baseline/current evaluation using only public environment factories.

Synthetic models belong to this evaluator; neither agent receives model or internals.
Baseline modules are loaded from git without changing the checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import types

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import Agent
from environment import make_environment
from mock_environment import make_mock_env, _mock_fallback, _mock_impact_model
from scoring_core import CHANNELS, score_campaigns, sanitize_campaigns, validate_strategy


def baseline_agent(ref):
    names = ('contracts', 'planning', 'policy', 'agent')
    previous = {name: sys.modules.get(name) for name in names}
    try:
        for name in names:
            source = subprocess.check_output(['git', 'show', f'{ref}:{name}.py'], cwd=ROOT, text=True)
            module = types.ModuleType(name)
            module.__file__ = str(ROOT / f'{name}.py')
            sys.modules[name] = module
            exec(compile(source, module.__file__, 'exec'), module.__dict__)
        return sys.modules['agent'].Agent
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def synthetic_model(profile, tariffs, scenario, model_seed):
    rng = np.random.default_rng(model_seed)
    rows = []
    for current, segment in profile[['current_tariff', 'arpu_segment']].drop_duplicates().sort_values(
            ['current_tariff', 'arpu_segment']).itertuples(index=False, name=None):
        for target in sorted(tariffs.tariff_plan_code):
            if scenario == 'positive':
                effect = 0.15
            elif scenario == 'negative':
                effect = -0.15
            elif scenario == 'null':
                effect = 0.0
            elif scenario == 'mixed':
                effect = rng.uniform(-0.4, 0.6)
            elif scenario == 'sparse':
                effect = 0.8 if rng.random() < 0.1 else -0.08
            else:
                raise ValueError(scenario)
            rows.append((current, segment, target, effect, 0.6))
    return pd.DataFrame(rows, columns=['tariff_plan_code_from', 'arpu_segment',
                                      'tariff_plan_code_to', 'arpu_change_pct', 'conversion_rate'])


def run(agent_class, scenario, seed, model, profile, tariffs):
    if scenario == 'mock':
        env, internals = make_mock_env(seed=seed)
    else:
        env, internals = make_environment(profile, model, tariffs, CHANNELS, 100000, 15000,
                                          _mock_fallback, seed=seed)
    agent = agent_class()
    started = time.monotonic()
    final = agent.act(env)
    duration = time.monotonic() - started
    validate_strategy(pd.DataFrame(final), tariffs)
    assert 1 <= len(final) <= 10
    assert len(sanitize_campaigns(final, tariffs)) == len(final)
    pilots = internals.executed_pilot_campaigns()
    assert 1 <= len(pilots) <= 20
    frame = pd.DataFrame(pilots + final)
    result = score_campaigns(frame, profile, model, tariffs, profile.predicted_arpu.sum(), _mock_fallback)
    assert result['total_contacts'] <= 15000 and result['total_cost'] <= 100000
    assert not any(detail.get(flag) for detail in result['campaigns_detail'] for flag in
                   ('capped_at_campaign_limit', 'capped_at_reach_budget', 'capped_at_money_budget'))
    requested = [event for event in agent.trace if event['event'] == 'pilot_requested']
    return {'net': result['net_arpu_gain'], 'cost': result['total_cost'],
            'contacts': result['total_contacts'], 'unique': result['unique_customers_targeted'],
            'pilots': len(pilots), 'distinct_pilots': len({e['candidate_key'] for e in requested}),
            'final_campaigns': len(final), 'seconds': duration}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='b70e366')
    parser.add_argument('--seeds', default='0,1,2,3,4,5,6,7,8,9,42,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119')
    parser.add_argument('--scenarios', default='mock,positive,negative,null,mixed,sparse')
    parser.add_argument('--model-seeds', default='701,1907,8803')
    parser.add_argument('--out', default='reports/candidate-comparison.json')
    args = parser.parse_args()
    import os
    os.chdir(ROOT)
    baseline = baseline_agent(args.baseline)
    profile = pd.read_csv('customer_profile.csv')
    tariffs = pd.read_csv('data/dict_tariff.csv')
    rows = []
    for scenario in args.scenarios.split(','):
        for model_seed in ([0] if scenario in ('mock', 'positive', 'negative', 'null') else map(int, args.model_seeds.split(','))):
            model = (_mock_impact_model(pd.read_csv('data/change_tariff.csv')) if scenario == 'mock'
                     else synthetic_model(profile, tariffs, scenario, model_seed))
            for seed in map(int, args.seeds.split(',')):
                old = run(baseline, scenario, seed, model, profile, tariffs)
                new = run(Agent, scenario, seed, model, profile, tariffs)
                row = {'scenario': scenario, 'model_seed': model_seed, 'seed': seed,
                       'baseline': old, 'candidate': new, 'difference': new['net'] - old['net']}
                rows.append(row)
                print(f"{scenario}/{model_seed}/{seed}: {old['net']:.0f} -> {new['net']:.0f} ({row['difference']:+.0f})", flush=True)
    summary = {}
    for scenario in args.scenarios.split(','):
        selected = [r for r in rows if r['scenario'] == scenario]
        summary[scenario] = {'runs': len(selected), 'wins': sum(r['difference'] > 1e-6 for r in selected),
                             'losses': sum(r['difference'] < -1e-6 for r in selected),
                             'mean_delta': float(np.mean([r['difference'] for r in selected]))}
        for variant in ('baseline', 'candidate'):
            values = [r[variant]['net'] for r in selected]
            summary[scenario][variant] = {'mean': float(np.mean(values)), 'median': float(np.median(values)),
                                          'min': float(min(values)), 'negative': sum(v < 0 for v in values)}
    report = {'baseline': args.baseline, 'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
               for name in ('agent.py', 'policy.py', 'planning.py', 'scripts/compare_candidate.py')},
              'summary': summary, 'rows': rows}
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
