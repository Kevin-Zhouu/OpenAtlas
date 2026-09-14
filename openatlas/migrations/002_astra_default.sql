UPDATE settings SET value = json_set(value, '$.model', 'gpt-6-astra')
WHERE json_extract(value, '$.model') = 'gpt-5.3-codex';
