"""Post-run explanations. No agent, environment, CSV or SDK imports on the offline path."""
import json
import math
import os
import signal
import threading
from contextlib import contextmanager

SUMMARY = 'План сформирован числовым агентом; объяснение не изменяет решения.'
EXPLANATION = 'Кампания проверена пилотом и включена агентом в финальный план.'
LIMITATIONS = [
    'Данные и эффекты синтетические; выводы о реальном бизнесе неизвестны.',
    'Пилотные наблюдения содержат шум; оценка агента не является доверительным интервалом.',
    'Локальный evaluator учитывает пилоты и финальные кампании; скрытый балл неизвестен и не гарантирован.',
    'История задаёт порядок исследования; её причинный эффект и вклад в отдельное решение неизвестны.',
]
MAX_PAYLOAD_BYTES = 48000


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def build_facts(plan, trace, result):
    """Allowlist aggregate facts; bind final events to their actual pilot requests."""
    if len(plan) > 10 or len(trace) > 100:
        raise ValueError('run exceeds explanation bounds')
    facts = {'schema_version': 1, 'campaigns': {}, 'events': {}, 'metrics': {},
             'history': 'unavailable' if any(e.get('event') == 'history_unavailable' for e in trace) else 'unknown',
             'limitations': LIMITATIONS.copy()}
    metrics = facts['metrics']
    for field in ('net_arpu_gain', 'total_cost', 'total_contacts', 'n_pilots', 'gross_arpu_lift'):
        metrics['local_evaluator.' + field] = {'value': number((result or {}).get(field)), 'source': 'local_evaluator'}
    selected = []
    requests = {}
    observations = {}
    for index, event in enumerate(trace):
        if event.get('step') != index or event.get('schema_version') != 1:
            raise ValueError('invalid trace sequence')
        eid = f'e{index}'
        kind, key = event.get('event'), event.get('candidate_key')
        if kind == 'pilot_requested':
            requests[key] = event
        if kind in ('pilot_observed', 'final_selected'):
            if key not in requests:
                raise ValueError('missing pilot request')
            fields = ('actual_n', 'cost', 'ratio') if kind == 'pilot_observed' else ('estimated_score', 'audience_count')
            refs = []
            for field in fields:
                ref = eid + '.' + field
                metrics[ref] = {'value': number(event.get(field)),
                                'source': ('pilot_observation' if kind == 'pilot_observed' else
                                           'public_profile' if field == 'audience_count' else 'agent_estimate')}
                refs.append(ref)
            facts['events'][eid] = {'kind': kind, 'metric_refs': refs}
            if kind == 'pilot_observed':
                observations.setdefault(key, []).append(eid)
            else:
                selected.append((key, eid))
    if len(selected) != len(plan):
        raise ValueError('plan and trace disagree')
    for index, (campaign, (key, eid)) in enumerate(zip(plan, selected), 1):
        request = requests[key]
        if (campaign.get('target_tariff') != request.get('target') or
                campaign.get('channel') != request.get('channel') or
                any(campaign.get(k) != v for k, v in request['filters'].items()) or
                not observations.get(key)):
            raise ValueError('campaign evidence mismatch')
        evidence = observations[key] + [eid]
        facts['campaigns'][f'c{index:02d}'] = {
            'plan_index': index - 1, 'evidence_event_ids': evidence,
            'metric_refs': [r for e in evidence for r in facts['events'][e]['metric_refs']]}
    return facts


def template(facts):
    return {'summary': SUMMARY, 'explanations': [
        {'campaign_id': cid, 'text': EXPLANATION,
         'evidence_event_ids': c['evidence_event_ids'].copy(), 'metric_refs': c['metric_refs'].copy()}
        for cid, c in facts['campaigns'].items()], 'limitations': LIMITATIONS.copy()}


def validate_response(doc, facts):
    """Closed Russian vocabulary prevents uncheckable prose, numbers and references."""
    if not isinstance(doc, dict) or set(doc) != {'summary', 'explanations', 'limitations'}:
        raise ValueError('invalid document')
    if doc['summary'] != SUMMARY or doc['limitations'] != LIMITATIONS:
        raise ValueError('unverified narrative')
    rows = doc['explanations']
    if not isinstance(rows, list) or len(rows) != len(facts['campaigns']):
        raise ValueError('invalid campaigns')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'campaign_id', 'text', 'evidence_event_ids', 'metric_refs'}:
            raise ValueError('invalid explanation')
        cid = row['campaign_id']
        if not isinstance(cid, str) or cid not in facts['campaigns'] or cid in seen or row['text'] != EXPLANATION:
            raise ValueError('unverified campaign')
        seen.add(cid)
        for field in ('evidence_event_ids', 'metric_refs'):
            refs = row[field]
            expected = facts['campaigns'][cid][field]
            if (not isinstance(refs, list) or not all(isinstance(r, str) for r in refs)
                    or len(refs) != len(set(refs)) or set(refs) != set(expected)):
                raise ValueError('unverified evidence')
    return doc


def response_schema(facts):
    def strings(values):
        return {'type': 'array', 'items': {'type': 'string', 'enum': list(values)}}
    row = {'type': 'object', 'additionalProperties': False,
           'properties': {'campaign_id': {'type': 'string', 'enum': list(facts['campaigns'])},
                          'text': {'type': 'string', 'enum': [EXPLANATION]},
                          'evidence_event_ids': strings(facts['events']),
                          'metric_refs': strings(facts['metrics'])}}
    row['required'] = list(row['properties'])
    return {'type': 'object', 'additionalProperties': False,
            'properties': {'summary': {'type': 'string', 'enum': [SUMMARY]},
                           'explanations': {'type': 'array', 'items': row},
                           'limitations': strings(LIMITATIONS)},
            'required': ['summary', 'explanations', 'limitations']}


@contextmanager
def deadline(seconds):
    if (not hasattr(signal, 'setitimer') or threading.current_thread() is not threading.main_thread()
            or signal.getitimer(signal.ITIMER_REAL)[0]):
        raise RuntimeError('deadline unavailable')
    def expired(*args):
        raise TimeoutError('explanation deadline')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def explain(facts, *, llm=False):
    fallback = template(facts)
    if not llm:
        return fallback, 'offline'
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    model = os.environ.get('OPENAI_EXPLANATION_MODEL', '').strip()
    if not key or not model:
        return fallback, 'fallback_configuration'
    try:
        seconds = float(os.environ.get('OPENAI_EXPLANATION_TIMEOUT_SECONDS') or '20')
        tokens = int(os.environ.get('OPENAI_EXPLANATION_MAX_OUTPUT_TOKENS') or '2000')
        if not math.isfinite(seconds) or not 0 < seconds <= 120 or not 1 <= tokens <= 8000:
            raise ValueError('invalid bounds')
        payload = json.dumps(facts, ensure_ascii=False, allow_nan=False)
        if len(payload.encode()) > MAX_PAYLOAD_BYTES or not facts['campaigns']:
            raise ValueError('payload bounds')
        with deadline(seconds):
            from openai import OpenAI  # Optional dependency, explicit path only.
            with OpenAI(api_key=key, base_url='https://api.openai.com/v1',
                        max_retries=0, timeout=seconds) as client:
                response = client.responses.create(
                    model=model, store=False, max_output_tokens=tokens,
                    instructions='Верни структурированное русское объяснение. Используй только разрешённые формулировки и все ссылки соответствующей кампании. Не добавляй факты.',
                    input=payload,
                    text={'format': {'type': 'json_schema', 'name': 'run_explanation',
                                     'strict': True, 'schema': response_schema(facts)}})
                if response.status != 'completed' or not isinstance(response.output_text, str) or len(response.output_text) > 40000:
                    raise ValueError('incomplete response')
                doc = validate_response(json.loads(response.output_text), facts)
        return doc, 'llm_validated'
    except Exception:
        return fallback, 'fallback_unavailable_or_invalid'


def render_markdown(facts, doc, mode):
    validate_response(doc, facts)
    lines = ['# Объяснение запуска', '', f'Режим: `{mode}`.', '', doc['summary'], '',
             '## История', '', 'История используется для ранжирования. Вклад истории в конкретный выбор неизвестен.',
             'Статус истории в trace: ' + ('недоступна' if facts['history'] == 'unavailable' else 'неизвестно') + '.', '',
             '## Локальный evaluator', '', 'Общий результат включает пилоты и финальный план.', '']
    def display(ref):
        metric = facts['metrics'][ref]
        value = metric['value']
        return f"- `{ref}`: {'неизвестно' if value is None else format(value, '.12g')} ({metric['source']})."
    lines.extend(display(r) for r in facts['metrics'] if r.startswith('local_evaluator.'))
    for row in doc['explanations']:
        lines += ['', f"## Кампания {row['campaign_id']}", '', row['text'],
                  'Позиция в сохранённом plan.json: ' + str(facts['campaigns'][row['campaign_id']]['plan_index'] + 1) + '.',
                  'События: ' + ', '.join(row['evidence_event_ids']) + '.', '',
                  'Наблюдения пилотов и отдельная оценка агента:', '']
        lines.extend(display(r) for r in row['metric_refs'])
    lines += ['', '## Ограничения', ''] + ['- ' + x for x in LIMITATIONS]
    return '\n'.join(lines) + '\n'
