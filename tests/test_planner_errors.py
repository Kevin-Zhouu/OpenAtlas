import ast
import os
import re
from pathlib import Path


def test_planner_error_redacts_and_bounds_provider_message(monkeypatch):
    class APIError(Exception):
        def __init__(self, message):
            self.message = message

    tree = ast.parse(Path('generation/planner.py').read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == 'error_message']
    env = dict(APIError=APIError, os=os, re=re)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'planner', 'exec'), env)
    format_error = env['error_message']
    monkeypatch.setenv('CODEX_API_KEY', 'relay-secret')
    monkeypatch.setenv('OPENAI_API_KEY', 'provider-secret')
    message = format_error(APIError(
        'No credits. relay-secret provider-secret sk-abcdefghijk Bearer abcdefghi'))
    assert message.startswith('Planning failed: APIError: No credits.')
    for secret in ('relay-secret', 'provider-secret', 'sk-abcdefghijk', 'abcdefghi'):
        assert secret not in message
    assert len(format_error(APIError('x' * 10000))) < 1100
    assert 'Missing build prompt' in format_error(ValueError('Missing build prompt'))
