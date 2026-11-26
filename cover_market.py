"""Read same-date market cache for cover colors, independently of sector choice."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from data_source import _latest_path, _version, valid_date, validate_source


def _decimal(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def market_summary(snapshot, date, source):
    """Last jointly available Shanghai/Shenzhen minute, never a minute sum."""
    if not isinstance(snapshot, dict) or snapshot.get('date') != date or snapshot.get('mock') is not False:
        return None
    meta = snapshot.get('meta', {})
    if not isinstance(meta, dict) or meta.get('source_key', 'legacy') != source or snapshot.get('unit', '亿元') != '亿元':
        return None
    times, market = snapshot.get('times', []), snapshot.get('market', {})
    if not isinstance(market, dict):
        return None
    sh, sz = market.get('sh', []), market.get('sz', [])
    if not isinstance(times, list) or not isinstance(sh, list) or not isinstance(sz, list):
        return None
    candidates = []
    for i, time in enumerate(times):
        if not isinstance(time, str) or not re.fullmatch(r'(?:09|10|11|13|14|15):[0-5][0-9]', time):
            continue
        if not ('09:30' <= time <= '11:30' or '13:00' <= time <= '15:00'):
            continue
        if i >= len(sh) or i >= len(sz):
            continue
        left, right = _decimal(sh[i]), _decimal(sz[i])
        if left is not None and right is not None:
            candidates.append((time, left + right))
    if not candidates:
        return None
    time, total = max(candidates, key=lambda item: item[0])
    return {'date': date, 'source': source, 'available': True, 'unit': '亿元',
            'total': float(total), 'total_exact': str(total), 'as_of': time,
            'color': 'red' if total >= 0 else 'blue',
            'fetched_at': meta.get('fetched_at'), 'dataset_version': snapshot.get('dataset_version')}


def _fetched_at(snapshot):
    try:
        value = datetime.fromisoformat(snapshot.get('meta', {}).get('fetched_at', '').replace('Z', '+00:00'))
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    except (TypeError, ValueError, AttributeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def cover_market(date, source='top'):
    """Read only: no upstream fetch, cache migration, or sector dependency."""
    valid_date(date)
    validate_source(source)
    candidates = []
    for category in ('industry', 'concept'):
        try:
            text = _latest_path(date, category, source).read_text(encoding='utf8')
            checked = json.loads(text)
            if checked.get('dataset_version') != _version(checked):
                continue
            precise = json.loads(text, parse_float=Decimal)
            summary = market_summary(precise, date, source)
            if summary:
                candidates.append((_fetched_at(checked), summary))
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            continue
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return {'date': date, 'source': source, 'available': False,
            'reason': '尚未获取该日有效大盘数据，未自动判定；可先手动选色，或在行情视频中获取该日期数据。'}
