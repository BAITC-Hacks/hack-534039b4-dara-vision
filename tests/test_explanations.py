import copy
import hashlib
import json
import socket
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import explanations as ex
from scripts import explain_run


@pytest.fixture
def facts():
    plan = [{'target_tariff': 't', 'channel': 'sms', 'filter_arpu_segment': 'HIGH'}]
    trace = [
        {'schema_version': 1, 'step': 0, 'event': 'pilot_requested', 'candidate_key': 'key',
         'target': 't', 'channel': 'sms', 'filters': {'filter_arpu_segment': 'HIGH'}, 'ID_NUMBER': 'private-person'},
        {'schema_version': 1, 'step': 1, 'event': 'pilot_observed', 'candidate_key': 'key', 'actual_n': 100, 'cost': 400, 'ratio': .2},
        {'schema_version': 1, 'step': 2, 'event': 'final_selected', 'candidate_key': 'key', 'estimated_score': 150, 'audience_count': 900},
    ]
    return ex.build_facts(plan, trace, {'net_arpu_gain': 80, 'total_cost': 400, 'total_contacts': 1000, 'n_pilots': 1})


def sdk(monkeypatch, facts, *, response=None, error=None):
    monkeypatch.setenv('OPENAI_API_KEY', 'secret-sentinel')
    monkeypatch.setenv('OPENAI_EXPLANATION_MODEL', 'configured-model')
    monkeypatch.delenv('OPENAI_EXPLANATION_TIMEOUT_SECONDS', raising=False)
    monkeypatch.delenv('OPENAI_EXPLANATION_MAX_OUTPUT_TOKENS', raising=False)
    create = Mock(return_value=response or SimpleNamespace(status='completed', output_text=json.dumps(ex.template(facts))), side_effect=error)
    client = Mock()
    client.responses.create = create
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    factory = Mock(return_value=client)
    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=factory))
    return factory, create


def test_offline_never_imports_sdk_or_uses_network(monkeypatch, facts):
    factory, create = sdk(monkeypatch, facts)
    monkeypatch.setattr(socket, 'socket', Mock(side_effect=AssertionError('network')))
    assert ex.explain(facts) == (ex.template(facts), 'offline')
    factory.assert_not_called()
    create.assert_not_called()


def test_valid_one_request_and_safe_payload(monkeypatch, facts, capsys):
    factory, create = sdk(monkeypatch, facts)
    before = copy.deepcopy(facts)
    doc, mode = ex.explain(facts, llm=True)
    assert mode == 'llm_validated'
    assert facts == before
    factory.assert_called_once_with(api_key='secret-sentinel', base_url='https://api.openai.com/v1', max_retries=0, timeout=20)
    create.assert_called_once()
    args = create.call_args.kwargs
    assert args['store'] is False and args['max_output_tokens'] == 2000
    assert 'tools' not in args and 'web_search' not in json.dumps(args)
    assert len(args['input'].encode()) <= ex.MAX_PAYLOAD_BYTES
    for secret in ('secret-sentinel', 'ID_NUMBER', 'private-person', '.csv'):
        assert secret not in json.dumps(args)
        assert secret not in str(capsys.readouterr())
    assert ex.render_markdown(facts, doc, mode).count('150 (agent_estimate)') == 1


@pytest.mark.parametrize('error', [TimeoutError('secret-sentinel'), RuntimeError('401 secret-sentinel'),
                                  RuntimeError('429'), RuntimeError('500'), RuntimeError('503')])
def test_request_errors_fallback_once(monkeypatch, facts, error, capsys):
    _, create = sdk(monkeypatch, facts, error=error)
    doc, mode = ex.explain(facts, llm=True)
    assert doc == ex.template(facts) and mode.startswith('fallback')
    create.assert_called_once()
    assert 'secret-sentinel' not in str(capsys.readouterr())


@pytest.mark.parametrize('case', ['json', 'incomplete', 'campaign', 'event', 'metric', 'number', 'missing', 'cross_campaign'])
def test_invalid_responses_rejected(monkeypatch, facts, case):
    doc = ex.template(facts)
    if case == 'campaign':
        doc['explanations'][0]['campaign_id'] = 'c99'
    elif case == 'event':
        doc['explanations'][0]['evidence_event_ids'] = ['e99']
    elif case == 'metric':
        doc['explanations'][0]['metric_refs'] = ['invented']
    elif case == 'number':
        doc['summary'] = 'Гарантированная прибыль миллион.'
    elif case == 'missing':
        del doc['limitations']
    elif case == 'cross_campaign':
        facts['events']['e88'] = {'kind': 'pilot_observed', 'metric_refs': []}
        doc['explanations'][0]['evidence_event_ids'].append('e88')
    response = SimpleNamespace(status='incomplete' if case == 'incomplete' else 'completed',
                               output_text='{' if case == 'json' else json.dumps(doc))
    _, create = sdk(monkeypatch, facts, response=response)
    result, mode = ex.explain(facts, llm=True)
    assert result == ex.template(facts) and mode.startswith('fallback')
    create.assert_called_once()


@pytest.mark.parametrize('missing', ['OPENAI_API_KEY', 'OPENAI_EXPLANATION_MODEL', 'sdk'])
def test_missing_configuration(monkeypatch, facts, missing):
    factory, create = sdk(monkeypatch, facts)
    if missing == 'sdk':
        monkeypatch.setitem(sys.modules, 'openai', None)
    else:
        monkeypatch.delenv(missing)
    assert ex.explain(facts, llm=True)[1].startswith('fallback')
    factory.assert_not_called()
    create.assert_not_called()


@pytest.mark.parametrize('name,value', [('OPENAI_EXPLANATION_TIMEOUT_SECONDS', 'nan'),
                                        ('OPENAI_EXPLANATION_TIMEOUT_SECONDS', '-1'),
                                        ('OPENAI_EXPLANATION_MAX_OUTPUT_TOKENS', '9000')])
def test_invalid_config_no_request(monkeypatch, facts, name, value):
    _, create = sdk(monkeypatch, facts)
    monkeypatch.setenv(name, value)
    assert ex.explain(facts, llm=True)[1].startswith('fallback')
    create.assert_not_called()


def test_real_wall_deadline(monkeypatch, facts):
    _, create = sdk(monkeypatch, facts)
    monkeypatch.setenv('OPENAI_EXPLANATION_TIMEOUT_SECONDS', '.02')
    create.side_effect = lambda **kwargs: time.sleep(1)
    started = time.monotonic()
    assert ex.explain(facts, llm=True)[1].startswith('fallback')
    assert time.monotonic() - started < .5
    create.assert_called_once()


def test_unknowns_are_not_zero(facts):
    assert facts['metrics']['local_evaluator.gross_arpu_lift']['value'] is None
    assert 'неизвестно' in ex.render_markdown(facts, ex.template(facts), 'offline')


def test_payload_bound(monkeypatch, facts):
    _, create = sdk(monkeypatch, facts)
    monkeypatch.setattr(ex, 'MAX_PAYLOAD_BYTES', 10)
    assert ex.explain(facts, llm=True)[1].startswith('fallback')
    create.assert_not_called()


def test_real_runs_once_unchanged_offline_with_api_env(monkeypatch, tmp_path, facts):
    from agent import Agent
    from local_eval import evaluate_agent
    from make_submission import build_submission
    factory, create = sdk(monkeypatch, facts)
    monkeypatch.setattr(socket, 'socket', Mock(side_effect=AssertionError('network')))
    root = explain_run.ROOT
    monkeypatch.chdir(root)
    paths = list(root.rglob('*.csv'))
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    original = Agent.act
    calls = []
    def recorded(self, env):
        calls.append(1)
        return original(self, env)
    monkeypatch.setattr(Agent, 'act', recorded)
    assert explain_run.run(tmp_path / 'first') == 'offline'
    assert len(calls) == 1
    assert explain_run.run(tmp_path / 'second') == 'offline'
    assert len(calls) == 2
    for name in ('plan.json', 'trace.json', 'local_evaluator.json', 'facts.json', 'explanation.md'):
        assert (tmp_path / 'first' / name).read_bytes() == (tmp_path / 'second' / name).read_bytes()
    baseline = evaluate_agent(Agent(), seed=42, verbose=False)
    assert json.loads((tmp_path / 'first/local_evaluator.json').read_text()) == explain_run.json_safe(baseline)
    first = build_submission(Agent()).to_csv(index=False)
    second = build_submission(Agent()).to_csv(index=False)
    assert first == second
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == before
    factory.assert_not_called()
    create.assert_not_called()


def test_llm_cannot_change_artifacts(monkeypatch, tmp_path, facts):
    _, create = sdk(monkeypatch, facts, response=SimpleNamespace(status='completed', output_text='{}'))
    explain_run.run(tmp_path / 'offline')
    assert explain_run.run(tmp_path / 'llm', llm=True).startswith('fallback')
    for name in ('plan.json', 'trace.json', 'local_evaluator.json', 'facts.json'):
        assert (tmp_path / 'offline' / name).read_bytes() == (tmp_path / 'llm' / name).read_bytes()
    create.assert_called_once()


def test_successful_llm_preserves_real_plan(monkeypatch, tmp_path, facts):
    _, create = sdk(monkeypatch, facts)
    create.side_effect = lambda **kw: SimpleNamespace(
        status='completed', output_text=json.dumps(ex.template(json.loads(kw['input']))))
    explain_run.run(tmp_path / 'offline')
    assert explain_run.run(tmp_path / 'llm', llm=True) == 'llm_validated'
    for name in ('plan.json', 'trace.json', 'local_evaluator.json', 'facts.json'):
        assert (tmp_path / 'offline' / name).read_bytes() == (tmp_path / 'llm' / name).read_bytes()
    create.assert_called_once()


def test_unmatched_plan_rejected():
    with pytest.raises(ValueError, match='disagree'):
        ex.build_facts([{'target_tariff': 'fake'}], [], {})


def test_env_example_not_ignored():
    import subprocess
    result = subprocess.run(['git', 'check-ignore', '.env', '.env.production', '.env.example'],
                            cwd=explain_run.ROOT, text=True, capture_output=True)
    assert result.stdout.splitlines() == ['.env', '.env.production']
