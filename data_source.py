"""Explicit API/demo data modes and immutable shared preview/export snapshots."""
import hashlib
import json
import math
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from generate_data import make

ROOT = Path(__file__).resolve().parent
API_BASE = os.environ.get('SECTORFLOW_API_BASE', 'https://lzcsnew.stocktest.hnchasing.com/ai-gateway/api').rstrip('/')
FLOW_COLORS = ['#FF567C', '#FFB547', '#40B9FF', '#20E0C5', '#BA92FF',
               '#FF7FD1', '#C8E95B', '#FF895E', '#62E0F3', '#8FAEFF',
               '#61E59A', '#F6D85B', '#D799F0', '#73C9AE', '#F5A8A8']
INDUSTRY_RANK_RULE = 'top8_positive_top7_negative_excluding_level1_v1'
INDUSTRY_FILTER_VERSION = 'exclude_level1_31_v1'
LEVEL1_INDUSTRY_NAMES = frozenset('''农林牧渔 食品饮料 医药生物 家用电器 纺织服饰 轻工制造 社会服务 商贸零售 美容护理
石油石化 煤炭 有色金属 基础化工 钢铁 电力设备 机械设备 国防军工 公用事业 环保 汽车 房地产 建筑材料 建筑装饰
交通运输 电子 计算机 通信 传媒 银行 非银金融 综合'''.split())


def valid_date(date):
    if not isinstance(date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError('日期必须为 YYYY-MM-DD')
    datetime.strptime(date, '%Y-%m-%d')
    return date


def validate_category(category):
    if category not in ('industry', 'concept'):
        raise ValueError('数据类型必须为 industry 或 concept')
    return category


def validate_source(source):
    if source not in ('top', 'legacy'):
        raise ValueError('数据源必须为 top 或 legacy')
    return source


def _latest_path(date, category, source='top'):
    validate_category(category)
    validate_source(source)
    folder = ROOT / 'data' / 'top' / category if source == 'top' else (ROOT / 'data' if category == 'industry' else ROOT / 'data' / 'concept')
    return folder / (date + '.json')


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def _version(snapshot):
    content = {k: v for k, v in snapshot.items() if k != 'dataset_version'}
    content['meta'] = {k: v for k, v in snapshot.get('meta', {}).items() if k != 'dataset_version'}
    return hashlib.sha256(_encoded(content)).hexdigest()


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temp.write_bytes(_encoded(value))
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def snapshot_path(version):
    if not isinstance(version, str) or not re.fullmatch(r'[0-9a-f]{64}', version):
        raise ValueError('数据快照版本无效，请重新获取数据')
    return ROOT / 'data' / 'snapshots' / (version + '.json')


def save_snapshot(snapshot):
    snapshot['dataset_version'] = _version(snapshot)
    snapshot.setdefault('meta', {})['dataset_version'] = snapshot['dataset_version']
    path = snapshot_path(snapshot['dataset_version'])
    if not path.exists():
        _atomic(path, snapshot)
    if not snapshot.get('mock'):
        _atomic(_latest_path(snapshot['date'], validate_category(snapshot.get('meta', {}).get('category', 'industry')), validate_source(snapshot.get('meta', {}).get('source_key', 'legacy'))), snapshot)
    return snapshot


def _records(response, date, label):
    if not isinstance(response, dict) or response.get('retCode') != 0:
        raise ValueError(f'{label}接口返回失败：{response.get("message", "响应格式无效") if isinstance(response, dict) else "响应格式无效"}')
    data = response.get('data')
    if not isinstance(data, dict) or str(data.get('date')) != date.replace('-', ''):
        raise ValueError(f'{label}接口返回日期与请求日期不一致')
    records = data.get('list')
    if not isinstance(records, list) or not records:
        raise ValueError(f'{label}接口暂无该日期数据；请确认上游缓存或采集状态')
    return records


def _time(value, date):
    value = str(value)
    if not re.fullmatch(r'\d{12}', value) or value[:8] != date.replace('-', ''):
        raise ValueError('接口记录时间或日期无效')
    parsed = datetime.strptime(value, '%Y%m%d%H%M').strftime('%H:%M')
    return parsed if '09:30' <= parsed <= '11:30' or '13:00' <= parsed <= '15:00' else None


def _amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError('接口金额缺失或类型无效')
    result = float(value) / 100000000
    if not math.isfinite(result):
        raise ValueError('接口金额不是有效数值')
    return result


def build_snapshot(date, market, industry, fetched_at=None, category='industry', source='legacy'):
    valid_date(date)
    validate_category(category)
    validate_source(source)
    noun = '行业' if category == 'industry' else '概念'
    market_records = _records(market, date, '大盘')
    industry_records = _records(industry, date, noun)
    markets, industries = {}, {}
    for record in market_records:
        time = _time(record.get('time'), date)
        if time is None:
            continue
        if time in markets:
            raise ValueError(f'大盘接口存在重复分钟：{time}')
        markets[time] = {key: _amount(record.get(field)) for key, field in [('sh', 'shInflow'), ('sz', 'szInflow'), ('total', 'totalInflow')]}
    for time, values in markets.items():
        if not math.isclose(values['total'], values['sh'] + values['sz'], rel_tol=0, abs_tol=1e-8):
            raise ValueError(f'大盘合计与沪深之和不一致：{time}')
    for record in industry_records:
        time = _time(record.get('time'), date)
        if time is None:
            continue
        code, name = str(record.get('prodCode', '')), record.get('prodName')
        if not code or not isinstance(name, str) or not name:
            raise ValueError(f'{noun}代码或名称缺失')
        group = industries.setdefault(time, {})
        if code in group:
            raise ValueError(f'{noun}接口存在重复记录：{time} / {code}')
        group[code] = {'name': name, 'value': _amount(record.get('netValueTotal'))}
    if not markets or not industries:
        raise ValueError('接口没有有效交易时段数据')
    times = sorted(set(markets) | set(industries))
    last = max(industries)
    raw_ranking = industries[last]
    filter_meta = {}
    if category == 'industry':
        # Classify using complete raw names, never the shortened display labels.
        excluded_codes = {code for group in industries.values() for code, item in group.items()
                          if item['name'].strip() in LEVEL1_INDUSTRY_NAMES}
        industries = {time: {code: item for code, item in group.items() if code not in excluded_codes}
                      for time, group in industries.items()}
        removed = {code: item for code, item in raw_ranking.items() if code in excluded_codes}
        filter_meta = {'industry_filter_version': INDUSTRY_FILTER_VERSION,
                       'industry_filter_policy': 'exclude exact raw names from user-provided 31 first-level industries before ranking; retain actual available counts',
                       'raw_rank_universe_count': len(raw_ranking), 'excluded_level1_count': len(removed),
                       'excluded_level1_names': sorted({item['name'] for item in removed.values()}),
                       'rank_positive_target': 8, 'rank_negative_target': 7}
    ranking = industries[last]
    positive = sorted((c for c in ranking if ranking[c]['value'] > 0), key=lambda c: (-ranking[c]['value'], c))
    if category == 'concept':
        if len(positive) < 10:
            raise ValueError(f'概念{last}快照不足10个净流入为正的概念，无法生成净流入前10回放')
        selected = positive[:10]
        rank_rule = 'top10_positive_returned_universe'
        rank_description = '最后快照已返回概念中的净流入前10'
    else:
        negative = sorted((c for c in ranking if ranking[c]['value'] < 0), key=lambda c: (ranking[c]['value'], c))
        selected = positive[:8] + negative[:7]
        if not selected:
            raise ValueError(f'行业{last}剔除一级行业后没有金额非零的可展示行业，请重新获取完整二级行业数据')
        rank_rule = INDUSTRY_RANK_RULE
        rank_description = f'剔除一级行业后，最后快照已返回二级行业中的净流入前{min(8, len(positive))}、净流出前{min(7, len(negative))}，共{len(selected)}个行业（最多8＋7）'
    series = [{'code': code, 'name': ranking[code]['name'], 'color': FLOW_COLORS[i], 'values': [industries.get(t, {}).get(code, {}).get('value') for t in times]} for i, code in enumerate(selected)]
    asof, latest = [], None
    for time in times:
        if time in markets:
            latest = time
        asof.append(latest)
    missing = sum(v is None for s in series for v in s['values'])
    warnings = [f'{noun}排名仅限最后快照已返回{noun}；当前接口可能仅返回排序前50条，不代表全{noun}排名。']
    if category == 'industry' and (len(positive) < 8 or len(negative) < 7):
        warnings.append(f'剔除一级行业后，{last}快照实际可选正值{len(positive)}个、负值{len(negative)}个；最多展示净流入8个、净流出7个，不足按实际数量，不补零、不使用一级行业凑数。')
    if max(markets) < '15:00':
        warnings.append(f'大盘仅返回至{max(markets)}，后续不补值，曲线停留在实际末端。')
    if last < '15:00':
        warnings.append(f'{noun}仅返回至{last}，排名为该时点排名。')
    if missing:
        warnings.append(f'入选{noun}缺失{missing}个分钟点；缺失处不展示、不填零、不插值。')
    return {'date': date, 'mock': False, 'unit': '亿元', 'times': times, 'market': {key: [markets.get(t, {}).get(key) for t in times] for key in ('sh', 'sz', 'total')}, 'industries': series, 'meta': {
        'source': '财信证券APP', 'api_base': API_BASE, 'classification': '二级行业' if category == 'industry' else '热门概念', 'category': category, 'source_key': source,
        'endpoints': {'market': 'fund_flow_min', 'sector': 'fund_flow_block' if category == 'industry' else 'fund_flow_plat'}, 'timezone': 'Asia/Shanghai',
        'rank_mode': ('close' if last == '15:00' else 'asof') + '_' + rank_rule, 'rank_description': rank_description,
        'rank_positive_count': len(selected) if category == 'concept' else min(8, len(positive)), 'rank_negative_count': 0 if category == 'concept' else min(7, len(negative)),
        **filter_meta,
        'rank_as_of': last, 'rank_universe_count': len(ranking), 'market_asof': asof,
        'market_range': [min(markets), max(markets)], 'industry_range': [min(industries), last], 'sector_range': [min(industries), last],
        'range_start': times[0], 'range_end': times[-1], 'market_source_latest': max(markets), 'industry_source_latest': last, 'sector_source_latest': last,
        'compatibility': True, 'missing_selected_points': missing, 'warnings': warnings,
        'quality_status': 'compatible_partial_source', 'status': 'partial',
        'missing_policy': 'null; no zero fill, interpolation or repeated market values',
        'metric_definition': f'主力净流入=（超大单流入+大单流入）−（超大单流出+大单流出）；{noun}快照值直接展示，不再次累加',
        'fetched_at': fetched_at or datetime.now(timezone.utc).isoformat(),
        'raw_record_counts': {'market': len(market_records), category: len(industry_records)},
        'raw_sha256': {'market': hashlib.sha256(_encoded(market)).hexdigest(), category: hashlib.sha256(_encoded(industry)).hexdigest()}}}


def build_top_snapshot(date, market, response, fetched_at=None, category='industry'):
    """Merge signed records from both lists; the outFlow field does not imply a sign."""
    valid_date(date)
    validate_category(category)
    noun = '行业' if category == 'industry' else '概念'
    label = '新数据源' + noun
    if not isinstance(response, dict) or response.get('retCode') != 0:
        raise ValueError(f'{label}接口返回失败：{response.get("message", "响应格式无效") if isinstance(response, dict) else "响应格式无效"}')
    data = response.get('data')
    if not isinstance(data, dict) or str(data.get('date')) != date.replace('-', ''):
        raise ValueError(f'{label}接口返回日期与请求日期不一致')
    groups, counts, duplicate_count = {}, {}, 0
    for side in ('inFlow', 'outFlow'):
        frames = data.get(side)
        if frames is None:
            frames = []
        if not isinstance(frames, list):
            raise ValueError(f'{label}接口{side}必须为数组')
        counts[side] = 0
        for frame in frames:
            if not isinstance(frame, dict):
                raise ValueError(f'{label}接口分钟记录格式无效')
            time = _time(frame.get('time'), date)
            records = frame.get('list')
            if not isinstance(records, list):
                raise ValueError(f'{label}接口分钟list必须为数组')
            if time is None:
                continue
            for row in records:
                counts[side] += 1
                if not isinstance(row, str) or row.count(',') < 2:
                    raise ValueError(f'{label}记录必须为“代码,名称,金额”字符串')
                code, remainder = row.split(',', 1)
                name, raw_amount = remainder.rsplit(',', 1)
                code, name, raw_amount = code.strip(), name.strip(), raw_amount.strip()
                if not code or not name or not raw_amount:
                    raise ValueError(f'{label}代码、名称或金额缺失')
                try:
                    amount = Decimal(raw_amount)
                except InvalidOperation as exc:
                    raise ValueError(f'{label}金额无效：{time} / {code}') from exc
                if not amount.is_finite():
                    raise ValueError(f'{label}金额不是有效数值：{time} / {code}')
                group = groups.setdefault(time, {})
                if code in group:
                    if group[code]['amount'] != amount:
                        raise ValueError(f'{label}同分钟同代码金额冲突：{time} / {code}')
                    duplicate_count += 1
                    continue
                group[code] = {'name': name, 'amount': amount}
    if not groups:
        raise ValueError(f'{label}接口暂无{date}数据；该源未返回有效记录，请确认采集状态，不会回退旧源或模拟数据')
    records = [{'time': date.replace('-', '') + time.replace(':', ''), 'prodCode': code,
                'prodName': item['name'], 'netValueTotal': str(item['amount'])}
               for time in sorted(groups) for code, item in groups[time].items()]
    adapted = {'retCode': 0, 'data': {'date': date.replace('-', ''), 'list': records}}
    try:
        snapshot = build_snapshot(date, market, adapted, fetched_at=fetched_at, category=category, source='top')
    except ValueError as exc:
        raise ValueError(f'{label}：{exc}；按接口金额实际正负号排名，不会将outFlow金额强制转负') from exc
    meta = snapshot['meta']
    meta['classification'] = '二级行业（已剔除一级行业，恒生返回范围）' if category == 'industry' else '热门概念（恒生返回范围）'
    meta['per_minute_counts'] = [{'time': time, 'total': len(groups[time]), 'positive': sum(item['amount'] > 0 for item in groups[time].values()), 'negative': sum(item['amount'] < 0 for item in groups[time].values())} for time in sorted(groups)]
    meta['endpoints']['sector'] = 'fund_flow_block_top' if category == 'industry' else 'fund_flow_plat_top'
    meta['raw_sha256'][category] = hashlib.sha256(_encoded(response)).hexdigest()
    meta['raw_record_counts'][category] = sum(counts.values())
    meta['top_record_counts'] = counts
    meta['deduplicated_records'] = duplicate_count
    meta['merged_record_count'] = len(records)
    meta['sign_policy'] = 'preserve signed net amount; never infer sign from inFlow/outFlow'
    meta['warnings'][0] = f'{noun}排名仅限新数据源最后快照两侧合并返回的{noun}，不代表全{noun}排名。'
    return snapshot


def fetch_data(date, category='industry', source='top'):
    valid_date(date)
    validate_category(category)
    validate_source(source)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '_' + uuid.uuid4().hex[:8]
    folder = ROOT / 'data' / 'raw' / date / stamp
    folder.mkdir(parents=True)
    def fetch(endpoint):
        request = Request(API_BASE + '/' + endpoint, data=_encoded({'date': date.replace('-', '')}), headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read()
            (folder / (endpoint + '.json')).write_bytes(raw)
            return json.loads(raw)
        except HTTPError as exc:
            (folder / (endpoint + '_error.txt')).write_bytes(exc.read())
            raise RuntimeError(f'{endpoint}接口HTTP {exc.code}；请检查接口服务状态') from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f'{endpoint}接口连接失败：{exc}；请检查网络、VPN及接口可达性') from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f'{endpoint}接口未返回有效JSON；原始响应已保存') from exc
    with ThreadPoolExecutor(max_workers=2) as pool:
        market_future = pool.submit(fetch, 'fund_flow_min')
        endpoint = ('fund_flow_block' if category == 'industry' else 'fund_flow_plat') + ('_top' if source == 'top' else '')
        industry_future = pool.submit(fetch, endpoint)
        market, industry = market_future.result(), industry_future.result()
    snapshot = build_top_snapshot(date, market, industry, category=category) if source == 'top' else build_snapshot(date, market, industry, category=category, source=source)
    snapshot['meta']['raw_directory'] = str(folder.relative_to(ROOT))
    return save_snapshot(snapshot)


def _upgrade_industry_snapshot(snapshot, source):
    """Rebuild latest only from the original hash-matched raw responses."""
    date = snapshot['date']
    meta = snapshot.get('meta', {})
    expected = meta.get('raw_sha256', {})
    if not expected.get('market') or not expected.get('industry'):
        raise ValueError('旧行业缓存缺少可校验的原始响应，无法按剔除一级行业的新规则重新排名，请重新获取接口数据')
    endpoint = 'fund_flow_block_top' if source == 'top' else 'fund_flow_block'
    roots = []
    if meta.get('raw_directory'):
        candidate = (ROOT / meta['raw_directory']).resolve()
        if candidate.is_relative_to((ROOT / 'data' / 'raw').resolve()):
            roots.append(candidate)
    roots.extend(sorted((ROOT / 'data' / 'raw' / date).glob('*')))
    for folder in dict.fromkeys(roots):
        try:
            market = json.loads((folder / 'fund_flow_min.json').read_text(encoding='utf8'))
            sector = json.loads((folder / (endpoint + '.json')).read_text(encoding='utf8'))
        except (OSError, ValueError):
            continue
        if hashlib.sha256(_encoded(market)).hexdigest() != expected['market'] or hashlib.sha256(_encoded(sector)).hexdigest() != expected['industry']:
            continue
        if source == 'top':
            rebuilt = build_top_snapshot(date, market, sector, fetched_at=meta.get('fetched_at'))
        else:
            rebuilt = build_snapshot(date, market, sector, fetched_at=meta.get('fetched_at'), source=source)
        rebuilt['meta']['raw_directory'] = str(folder.relative_to(ROOT))
        rebuilt['meta']['upgraded_from_dataset_version'] = snapshot['dataset_version']
        # Existing immutable snapshots stay byte-for-byte intact.
        return save_snapshot(rebuilt)
    raise ValueError('旧行业缓存未找到与原快照校验一致的原始响应，无法按剔除一级行业的新规则重新排名，请重新获取接口数据')


def load_data(date, mode='api', version=None, category='industry', source='top'):
    valid_date(date)
    validate_category(category)
    validate_source(source)
    if mode not in ('api', 'demo'):
        raise ValueError('数据模式必须为 api 或 demo')
    if version is not None:
        path = snapshot_path(version)
    elif mode == 'demo':
        snapshot = make(date)
        if category == 'concept':
            names = ['人工智能', '机器人', '算力', '低空经济', '商业航天', '新能源汽车', '数字经济', '数据要素', '量子科技', '智能驾驶']
            for series, name in zip(snapshot['industries'], names):
                series['name'] = name
                if series['values'][-1] < 0:
                    series['values'] = [-value for value in series['values']]
            snapshot['industries'].sort(key=lambda series: (-series['values'][-1], series['code']))
            snapshot['meta']['rank_mode'] = 'close_top10_positive_returned_universe'
            snapshot['meta']['rank_description'] = '模拟概念净流入前10'
            snapshot['meta']['category'] = category
            snapshot['meta']['classification'] = '热门概念（演示概念名，模拟数据）'
        else:
            # Extend only explicit demonstration mode; no API values are synthesized.
            for index, (name, base_index, scale) in enumerate([
                    ('软件开发', 0, .8), ('计算机设备', 1, .8), ('通信设备', 2, .8),
                    ('化学制药', 5, .8), ('房地产开发', 6, .8)], start=11):
                original = snapshot['industries'][base_index]
                snapshot['industries'].append({'code': f'MOCK{index:03d}', 'name': name,
                                              'values': [round(value * scale, 3) for value in original['values']]})
            positive = sorted((series for series in snapshot['industries'] if series['values'][-1] > 0), key=lambda series: (-series['values'][-1], series['code']))
            negative = sorted((series for series in snapshot['industries'] if series['values'][-1] < 0), key=lambda series: (series['values'][-1], series['code']))
            snapshot['industries'] = positive[:8] + negative[:7]
            snapshot['meta'].update({'rank_mode': 'close_' + INDUSTRY_RANK_RULE,
                                     'rank_description': '模拟行业净流入前8、净流出前7，共15个行业',
                                     'industry_filter_version': INDUSTRY_FILTER_VERSION,
                                     'category': 'industry', 'classification': '二级行业（演示行业名，模拟数据）'})
        for index, series in enumerate(snapshot['industries']):
            series['color'] = FLOW_COLORS[index]
        snapshot['meta']['rank_positive_count'] = 10 if category == 'concept' else 8
        snapshot['meta']['rank_negative_count'] = 0 if category == 'concept' else 7
        snapshot['meta']['source_key'] = source
        return save_snapshot(snapshot)
    else:
        path = _latest_path(date, category, source)
    if not path.exists():
        raise FileNotFoundError(f'{"新" if source == "top" else "旧"}数据源尚无{date}的{"行业" if category == "industry" else "概念"}缓存，请点击“获取接口数据”；不会回退其他数据源或模拟数据')
    snapshot = json.loads(path.read_text(encoding='utf8'))
    if snapshot.get('meta', {}).get('source_key', 'legacy') != source:
        raise ValueError('快照数据源与请求不一致，请重新加载对应数据源')
    if snapshot.get('meta', {}).get('category', 'industry') != category:
        raise ValueError('快照数据类型与请求不一致，请重新加载对应数据')
    if snapshot.get('date') != date or bool(snapshot.get('mock')) != (mode == 'demo'):
        raise ValueError('快照日期或数据模式与请求不一致')
    actual_version = snapshot.get('dataset_version')
    if actual_version != _version(snapshot) or version is not None and actual_version != version:
        raise ValueError('数据快照校验失败，请重新获取接口数据')
    snapshot_path(actual_version)
    n = len(snapshot['times'])
    if n < 2 or snapshot['times'] != sorted(set(snapshot['times'])):
        raise ValueError('时间轴无效')
    for values in list(snapshot['market'].values()) + [s['values'] for s in snapshot['industries']]:
        if len(values) != n or any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in values):
            raise ValueError('数据长度或金额无效')
    if version is None and mode == 'api' and category == 'industry' and (not snapshot.get('meta', {}).get('rank_mode', '').endswith(INDUSTRY_RANK_RULE) or snapshot.get('meta', {}).get('industry_filter_version') != INDUSTRY_FILTER_VERSION):
        return _upgrade_industry_snapshot(snapshot, source)
    return snapshot


def default_date(category='industry', source='top'):
    validate_category(category)
    validate_source(source)
    dates = []
    for path in _latest_path('', category, source).parent.glob('????-??-??.json'):
        try:
            load_data(path.stem, category=category, source=source)
            dates.append(path.stem)
        except (ValueError, KeyError, TypeError, OSError):
            continue
    return max(dates, default='2026-10-23')
