"""Run the numerical Agent exactly once, then explain the frozen result."""
import argparse
from contextlib import redirect_stdout
import io
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import Agent
from local_eval import evaluate_agent
from explanations import build_facts, explain, render_markdown


def json_safe(value):
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, 'item'):
        return json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class RecordingAgent:
    def __init__(self):
        self.agent = Agent()
        self.plan = None

    def act(self, env):
        self.plan = self.agent.act(env)
        return self.plan


def run(out, *, seed=42, llm=False):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    wrapped = RecordingAgent()
    with redirect_stdout(io.StringIO()):
        result = evaluate_agent(wrapped, seed=seed, verbose=False)
    def save(name, value):
        (out / name).write_text(json.dumps(json_safe(value), ensure_ascii=False,
                                         indent=2, allow_nan=False) + '\n', encoding='utf-8')
    save('plan.json', wrapped.plan)
    save('trace.json', wrapped.agent.trace)
    save('local_evaluator.json', result)
    if wrapped.plan is None or result is None:
        raise RuntimeError('Evaluation failed; available artifacts saved')
    facts = build_facts(wrapped.plan, wrapped.agent.trace, result)
    facts['seed'] = seed
    save('facts.json', facts)
    doc, mode = explain(facts, llm=llm)
    save('explanation.json', {'mode': mode, **doc})
    (out / 'explanation.md').write_text(render_markdown(facts, doc, mode), encoding='utf-8')
    return mode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='reports/explanation')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--llm', action='store_true')
    args = parser.parse_args()
    out = Path(args.out).resolve()
    os.chdir(ROOT)
    mode = run(out, seed=args.seed, llm=args.llm)
    print('Explanation saved; mode=' + mode)


if __name__ == '__main__':
    main()
