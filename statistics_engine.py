"""Compile and decode read-only Stata descriptive and Pearson statistics."""
import math
import re
from numeric_types import is_numeric_type


def validate_statistics(spec, dataset):
    variables = spec.get('variables')
    kinds = spec.get('kinds')
    if not isinstance(variables, list) or not 1 <= len(variables) <= 100 or any(not isinstance(v, str) for v in variables):
        raise ValueError('请选择 1 至 100 个数值变量。')
    if not isinstance(kinds, list) or not kinds or any(not isinstance(k, str) or k not in ('descriptive', 'correlation') for k in kinds) or len(kinds) != len(set(kinds)):
        raise ValueError('请选择描述性统计或 Pearson 相关性。')
    available = dataset.get('variables', [])
    chosen = []
    for name in variables:
        if not name.isidentifier() or len(name.encode('utf-8')) > 32:
            raise ValueError(f'变量 {name!r} 名称无效。')
        matches = [v for v in available if v['name'] == name]
        if not matches:
            matches = [v for v in available if v['name'].casefold() == name.casefold()]
        if len(matches) != 1:
            raise ValueError(f'变量 {name!r} 不存在或大小写存在歧义。')
        entry = matches[0]
        if not is_numeric_type(entry.get('type', '')):
            raise ValueError(f"{entry['name']} 不是数值变量。")
        chosen.append(entry['name'])
    if len(set(chosen)) != len(chosen):
        raise ValueError('请选择不重复的变量。')
    if 'correlation' in kinds and len(chosen) < 2:
        raise ValueError('相关性检验至少需要两个变量。')
    return {'variables': chosen, 'kinds': kinds}


def compile_statistics(spec, output):
    # The result file is a local machine-readable companion to the real Stata log.
    path = str(output).replace('\\', '/')
    if '"' in path or '\n' in path or '\r' in path:
        raise ValueError('结果路径无效。')
    detailed = 'descriptive' in spec['kinds']
    lines = ['* 只读统计：基于当前 Stata 主分析集，不修改数据。',
             '* 描述性统计使用各变量非缺失样本；Pearson 相关性使用逐对非缺失样本。',
             'tempname statfile', f'file open `statfile\' using "{path}", write text replace']
    lines += [f"local variables {' '.join(spec['variables'])}", 'local i = 0', "foreach variable of local variables {", '    local ++i',
              "    quietly summarize `variable'" + (', detail' if detailed else '')]
    values = ['r(N)', 'r(mean)', 'r(sd)', 'r(p50)' if detailed else '.', 'r(min)', 'r(max)']
    lines += ['    file write `statfile\' "D|`i\'|" ' + ' "|" '.join(f'%24.16g ({v})' for v in values) + ' _n', '}']
    if 'correlation' in spec['kinds']:
        lines += ['* 逐对计算 Pearson 相关系数、样本量和双侧 p 值。',
                  "local total : word count `variables'", 'local i = 0',
                  'foreach left of local variables {', '    local ++i', "    local j = `i'",
                  "    while `j' < `total' {", '        local ++j', "        local right : word `j' of `variables'",
                  "        capture quietly correlate `left' `right'", '        if _rc {',
                  "            quietly count if !missing(`left', `right')", '            local n = r(N)',
                  '            local rho = .', '        }', '        else {', '            local n = r(N)',
                  '            local rho = r(rho)', '        }', '        local p = .',
                  "        if `n' > 2 & !missing(`rho') {", "            if abs(`rho') >= 1 local p = 0",
                  "            else local p = 2 * ttail(`n'-2, abs(`rho') * sqrt((`n'-2)/(1-`rho'^2)))",
                  '        }',
                  '        file write `statfile\' "C|`i\'|`j\'|" %24.16g (`n\') "|" %24.16g (`rho\') "|" %24.16g (`p\') _n',
                  '    }', '}']
    lines += ["file close `statfile'", 'display "STATISTICS_COMPLETED"']
    return '\n'.join(lines) + '\n'


def parse_statistics(text, spec, dataset):
    desc = {}; pairs = {}
    def number(value):
        value = value.strip()
        if re.fullmatch(r'\.[a-z]?', value, re.I): return None
        result = float(value)
        return result if math.isfinite(result) else None
    for line in text.splitlines():
        parts = line.split('|')
        if parts[0] == 'D' and len(parts) == 8:
            desc[int(parts[1])] = [number(v) for v in parts[2:]]
        elif parts[0] == 'C' and len(parts) == 6:
            pairs[(int(parts[1]), int(parts[2]))] = [number(v) for v in parts[3:]]
        elif line.strip():
            raise ValueError('Stata 统计结果格式无效。')
    n = len(spec['variables'])
    if len(desc) != n or ('correlation' in spec['kinds'] and len(pairs) != n*(n-1)//2):
        raise ValueError('Stata 统计结果不完整。')
    labels = {v['name']:v.get('label', '') for v in dataset.get('variables', [])}
    report = {'variables':spec['variables'], 'kinds':spec['kinds'], 'method':'Pearson',
              'missing_policy':'pairwise', 'dataset':dataset.get('filename', '')}
    if 'descriptive' in spec['kinds']:
        report['descriptive'] = [{'variable':name, 'label':labels.get(name, ''), **dict(zip(['n','mean','sd','median','min','max'], desc[i]))}
                                 for i,name in enumerate(spec['variables'], 1)]
    if 'correlation' in spec['kinds']:
        matrix = []
        for i in range(1, n+1):
            row = []
            for j in range(1, n+1):
                if i == j:
                    values = desc[i]
                    row.append({'r':1.0 if values[0] and values[0] >= 2 and values[2] is not None and values[2] > 0 else None,
                                'p':None, 'n':values[0]})
                else:
                    count, rho, p = pairs[tuple(sorted((i, j)))]
                    row.append({'r':rho, 'p':p, 'n':count})
            matrix.append(row)
        report['correlation'] = matrix
    return report
