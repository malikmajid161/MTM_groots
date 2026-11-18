"""Bounded JSON HTTP provider access and honest cumulative attempt tracing.

Wire protocol: configurable chat-completions-compatible endpoint. No SDK retries.
Transport credentials travel over subprocess stdin, never command-line arguments.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from dataclasses import dataclass, field

TAGS = frozenset(('reading', 'venue', 'schedule', 'food', 'judging', 'budget'))

class BudgetExceeded(RuntimeError):
    pass

@dataclass
class RunBudget:
    seconds: float = 60
    max_calls: int = 5
    reserve_seconds: float = 3
    clock: object = time.monotonic
    attempts: int = 0
    deadline: float = field(init=False)

    def __post_init__(self):
        if self.seconds <= self.reserve_seconds or self.reserve_seconds < 0 or self.max_calls < 1:
            raise ValueError('invalid run budget')
        self.deadline = self.clock() + self.seconds

    def acquire(self):
        remaining = self.deadline - self.clock() - self.reserve_seconds
        if self.attempts >= self.max_calls or remaining <= 0:
            raise BudgetExceeded('model call/time budget exhausted')
        self.attempts += 1
        return remaining

class TraceRecorder:
    """Load prior session trace; append each real attempt once, including failures."""
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.records = []
        if self.path and self.path.exists():
            self.records = [json.loads(line) for line in self.path.read_text().splitlines() if line]
            if any(row['number'] != n for n, row in enumerate(self.records, 1)):
                raise ValueError('nonsequential prior trace')

    def append(self, row):
        row = dict(row, number=len(self.records) + 1)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as out:
                out.write(json.dumps(row, ensure_ascii=False) + '\n')
                out.flush()
                os.fsync(out.fileno())
        self.records.append(row)
        return row

    def totals(self):
        fields = ('prompt_tokens', 'completion_tokens', 'total_tokens')
        return {k: (sum(r['usage'][k] for r in self.records)
                    if all(r['usage'][k] is not None for r in self.records) else None)
                for k in fields}

    def print_trace(self, stream=None):
        stream = stream or sys.stdout
        for row in self.records:
            print(json.dumps(row, ensure_ascii=False), file=stream)
        print('Total tokens: ' + json.dumps(self.totals()), file=stream)

_HTTP_WORKER = '''import json, sys, urllib.request
x=json.load(sys.stdin)
r=urllib.request.Request(x['endpoint'], data=json.dumps(x['payload']).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer '+x['key']}, method='POST')
with urllib.request.urlopen(r, timeout=x['timeout']) as response:
    sys.stdout.write(response.read().decode('utf-8'))
'''

def http_transport(endpoint, key, payload, timeout):
    # Parent timeout is an absolute wall bound even if the server trickles bytes.
    result = subprocess.run([sys.executable, '-c', _HTTP_WORKER],
        input=json.dumps(dict(endpoint=endpoint, key=key, payload=payload, timeout=timeout)),
        text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        # Worker stderr may contain provider data; never print it or credentials.
        raise RuntimeError('provider HTTP worker failed')
    return json.loads(result.stdout)

class ModelClient:
    def __init__(self, endpoint, model, api_key, transport=http_transport, approved_models=None):
        if not endpoint or not model or not api_key:
            raise ValueError('MODEL_ENDPOINT, MODEL_NAME and MODEL_API_KEY are required')
        if not endpoint.startswith('https://'):
            if not endpoint.startswith(('http://localhost:', 'http://127.0.0.1:')):
                raise ValueError('remote provider endpoint must use HTTPS')
        if approved_models is not None and model not in approved_models:
            raise ValueError('configured model is outside supplied approved list')
        self.endpoint, self.model, self.api_key = endpoint, model, api_key
        self.transport = transport

    @classmethod
    def from_env(cls):
        approved = os.environ.get('MODEL_APPROVED_MODELS')
        return cls(os.environ.get('MODEL_ENDPOINT'), os.environ.get('MODEL_NAME'),
                   os.environ.get('MODEL_API_KEY'),
                   approved_models=approved.split(',') if approved else None)

    def call(self, messages, budget, recorder, tag='reading'):
        if tag not in TAGS:
            raise ValueError('invalid call tag')
        timeout = budget.acquire()
        payload = {'model': self.model, 'messages': messages}
        start = time.monotonic()
        usage = dict(prompt_tokens=None, completion_tokens=None, total_tokens=None)
        raw, error, reported_model = None, None, None
        try:
            raw = self.transport(self.endpoint, self.api_key, payload, timeout)
            if isinstance(raw, dict):
                reported_model = raw.get('model')
                supplied = raw.get('usage') or {}
                for k in usage:
                    v = supplied.get(k)
                    usage[k] = v if type(v) is int and v >= 0 else None
            if time.monotonic() - start > timeout:
                raise BudgetExceeded('provider exceeded reserved call deadline')
            content = raw['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise ValueError('provider content is not text')
            return content
        except Exception as exc:
            error = type(exc).__name__  # no potentially secret-bearing exception text
            raise
        finally:
            recorder.append(dict(model=self.model, reported_model=reported_model, tag=tag,
                input=payload, output=raw, usage=usage,
                elapsed_seconds=time.monotonic()-start, error=error))
