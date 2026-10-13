#!/usr/bin/env python3
"""Present measured results; does not run models or change grading."""
import argparse
import html
import json
from pathlib import Path
from statistics import median

NAMES={'website':'Сайт мастер-классов','game':'Игра «Найди пару»','app':'Прототип доски задач'}
ARMS={'baseline':'Без скилов','lite':'Lite-конвенции','workflow':'С estafeta'}
ABOUT={'baseline':'ноль включённых скилов, только общий промпт.',
       'lite':'ноль включённых скилов, как без скилов; на месте активации в промпт вставлен '
              'текст prompts/lite.md — конвенции файлов проекта без скилов и runtime.',
       'workflow':'ровно четыре проектные копии скилов и их явный вызов{skills}.'}
COLORS={'baseline':'#87909d','lite':'#c58b2a','workflow':'#4e78d8'}
def fmt(n): return f'{n:,.0f}'.replace(',',' ') if n is not None else 'unknown'
def minutes(seconds): return f'{seconds/60:.2f}'
def count(n): return f'{n:g}'
def percent(after,before): return (after/before-1)*100 if before and after is not None else None
def delta(after,before):
    p=percent(after,before)
    return f'{p:+.1f}%' if p is not None else 'unknown'
def middle(values):
    """Median only when every planned repetition has a value; a gap stays unknown."""
    return median(values) if values and None not in values else None
def spread(values,show):
    known=[v for v in values if v is not None]
    if not known: return 'unknown'
    span=f'{show(min(known))}–{show(max(known))}'
    if len(known)<len(values): return f'unknown (известно {len(known)}/{len(values)}: {span})'
    return show(known[0]) if len(known)==1 else f'{show(median(known))} ({span})'

def main(out):
    adjudicated=(out/'adjudicated-results.json').exists()
    results=json.loads((out/('adjudicated-results.json' if adjudicated else 'results.json')).read_text())['rows']
    sub='adjudicated/' if adjudicated else ''
    review=json.loads((out/'review.json').read_text()) if (out/'review.json').exists() else {'cases':{}}
    reviewed=review.get('cases',{})
    protocol=json.loads((out/'protocol.json').read_text())
    extra=json.loads((out/'extra-checks.json').read_text()) if (out/'extra-checks.json').exists() else None
    audit=json.loads((out/'audit.json').read_text()) if (out/'audit.json').exists() else None
    correction_note=(
        'Сырые результаты первого grader сохранены. В нём исправлены две ошибки: '
        'немедленное чтение кэша URL в Playwright и требование наличия полей формы '
        'в игре, которая управляется кнопками. Исправленный grader одинаково '
        'применён ко всем сохранённым версиям после выполнения модели. Продукты, '
        'промпты, модельные прогоны и их время/токены при этом не изменялись. '
        'Итоговая таблица использует результаты этой независимой переоценки; '
        'исходные ошибки стенда не считаются багами продукта. См. '
        '[evaluator-correction.json](evaluator-correction.json) и '
        '[лабораторные заметки](LAB-NOTES.md).'
        if (out/'evaluator-correction.json').exists() else
        'Использован зафиксированный evaluator. Проверьте журналы и хэши '
        'перед интерпретацией его результатов; ошибки стенда исключаются из '
        'подтверждённых дефектов только после воспроизведения.')
    # Historical two-arm outputs have [scenario, arm] entries and rows without rep.
    repeated='repetitions' in protocol
    planned={}
    for entry in protocol['order']:
        planned.setdefault((entry[0],entry[1]),[]).append(entry[2] if len(entry)>2 else 1)
    scenarios=[s for s in (protocol.get('scenarios') or list(NAMES)) if any(k[0]==s for k in planned)]
    arms=[a for a in list(ARMS)+sorted({k[1] for k in planned}-set(ARMS)) if any(k[1]==a for k in planned)]
    reps=protocol.get('repetitions',1);cases=len(protocol['order'])
    by={(r['scenario'],r['arm'],r.get('rep',1)):r for r in results}
    def key(r): return r.get('case') or r['scenario']+'-'+r['arm']
    def cell(s,a,field): return [by[(s,a,rep)][field] if (s,a,rep) in by else None for rep in sorted(planned.get((s,a),[]))]
    def totals(s,a): return '/'.join(str(t) for t in sorted({x for x in cell(s,a,'final_total') if x is not None})) or '?'
    def short(r): return f"{NAMES.get(r['scenario'],r['scenario'])} / {ARMS.get(r['arm'],r['arm'])}"+(f" / r{r['rep']}" if 'rep' in r else '')
    def title(r): return f"{NAMES.get(r['scenario'],r['scenario'])} — {ARMS.get(r['arm'],r['arm'])}"+(f", повтор {r['rep']}" if 'rep' in r else '')
    rank=lambda r:(scenarios.index(r['scenario']) if r['scenario'] in scenarios else len(scenarios),
                   arms.index(r['arm']) if r['arm'] in arms else len(arms),r.get('rep',1))
    rows=sorted(results,key=rank)
    missing=[f'{s}-{a}-r{rep}' if repeated else f'{s}-{a}' for s in scenarios for a in arms
             for rep in sorted(planned.get((s,a),[])) if (s,a,rep) not in by]
    skills=protocol.get('workflow_skills')
    order_text=(f"Порядок случайный и сбалансированный, seed `{protocol['seed']}`: в каждом повторе "
                'перемешаны сценарии, внутри сценария — группы.' if 'seed' in protocol else
                'Порядок фиксирован и записан в протоколе.')
    lines=['# estafeta: сравнение групп','',
           'Общий промпт одинаков во всех группах; они различаются только блоком на месте '
           'активации скилов. Каждый случай — две свежие сессии: первая версия, затем '
           'изменение требования без истории предыдущего чата.','']
    lines+=[f'- {ARMS.get(a,a)}: '+ABOUT.get(a,'').format(skills=': '+', '.join(skills) if skills else '') for a in arms]
    lines+=['',f"Модель: `{protocol['model']}`, reasoning `{protocol['effort']}`. Плагин: "
           f"`{protocol['plugin_version']}` @ `{protocol['plugin_commit'][:7]}`. CLI: `{protocol['codex_version']}`. "
           f"Сценариев: {len(scenarios)}, групп: {len(arms)}, повторов на ячейку: {reps}, случаев: {cases}, "
           f"свежих сессий: {2*cases}. {order_text} Один компьютер, последовательные прогоны, "
           f"лимит {protocol['max_seconds_per_stage']/60:g} мин на сессию. [Протокол](protocol.json).",'',
           '## Итоги по группам','',
           '| Сценарий | Группа | Завершено повторов | Финальные требования: медиана (мин–макс) | Время, мин: медиана (мин–макс) | Токены всего: медиана (мин–макс) |',
           '|---|---|---:|---:|---:|---:|']
    for s in scenarios:
        for a in arms:
            if (s,a) not in planned:continue
            done=sum(x is not None for x in cell(s,a,'final_passed'))
            lines.append(f"| {NAMES.get(s,s)} | {ARMS.get(a,a)} | {done}/{len(planned[(s,a)])} | {spread(cell(s,a,'final_passed'),count)} из {totals(s,a)} | {spread(cell(s,a,'elapsed_seconds'),minutes)} | {spread(cell(s,a,'total_tokens'),fmt)} |")
    lines+=['','Медиана, минимум и максимум считаются по запланированным повторам ячейки. Если хотя бы '
            'у одного повтора значения нет (случай не завершён или нет нативной usage), медиана не '
            'вычисляется: указано unknown и диапазон известных значений; пропуск не заменяется нулём. '
            'Время и токены суммируют обе сессии случая, включая чтение скилов, собственные тесты '
            'и передачу проекта. Токены всего = input + output; cached input уже входит в input. '
            'Независимая оценка выполнялась после сессии и учитывается отдельно. '
            'Работа координатора по созданию стенда и отчёта сюда не включена.','',
            '## Сравнение с группой «Без скилов»','']
    others=[a for a in arms if a!='baseline']
    if 'baseline' in arms and others:
        lines+=['| Сценарий | Группа | Изменение времени | Изменение токенов | Токены на пройденную проверку: без скилов → группа |',
                '|---|---|---:|---:|---:|']
        fields=['elapsed_seconds','total_tokens','tokens_per_passed_requirement']
        for s in scenarios:
            if (s,'baseline') not in planned:continue
            base={f:middle(cell(s,'baseline',f)) for f in fields}
            for a in others:
                if (s,a) not in planned:continue
                cur={f:middle(cell(s,a,f)) for f in fields}
                lines.append(f"| {NAMES.get(s,s)} | {ARMS.get(a,a)} | {delta(cur['elapsed_seconds'],base['elapsed_seconds'])} | {delta(cur['total_tokens'],base['total_tokens'])} | {fmt(base['tokens_per_passed_requirement'])} → {fmt(cur['tokens_per_passed_requirement'])} |")
        lines+=['','Сравниваются медианы по повторам: каждая группа против «Без скилов» в том же сценарии. '
                'Положительное изменение означает больше затрат. Это описательное сравнение, '
                'а не статистически подтверждённый эффект.','']
    else:lines+=['Нет группы «Без скилов» или групп для сравнения с ней.','']
    if 'lite' in arms and 'workflow' in arms:
        lines+=['## estafeta против Lite-конвенций','',
                '| Сценарий | Изменение времени | Изменение токенов | Финальные требования: lite → workflow |',
                '|---|---:|---:|---:|']
        for s in scenarios:
            if (s,'lite') not in planned or (s,'workflow') not in planned:continue
            lite={f:middle(cell(s,'lite',f)) for f in ['elapsed_seconds','total_tokens','final_passed']}
            flow={f:middle(cell(s,'workflow',f)) for f in ['elapsed_seconds','total_tokens','final_passed']}
            passed=lambda v:count(v) if v is not None else 'unknown'
            lines.append(f"| {NAMES.get(s,s)} | {delta(flow['elapsed_seconds'],lite['elapsed_seconds'])} | {delta(flow['total_tokens'],lite['total_tokens'])} | {passed(lite['final_passed'])} → {passed(flow['final_passed'])} |")
        lines+=['','Решающее сравнение: окупает ли runtime свою стоимость поверх одних конвенций. '
                'Медианы по повторам; положительное изменение означает, что workflow дороже lite.','']
    lines+=['## Сценарии и изменение требования','',
            '- Сайт: фильтры, сортировка и запись → избранное, сохранение и URL фильтров.',
            '- Игра: пары, блокировка несовпадения и перезапуск → пауза и лучший результат.',
            '- Прототип: CRUD, фильтры и сохранение → одноуровневый undo и атомарный JSON import/export.','',
            '## Отдельные повторы','',
            '| Сценарий / группа / повтор | Финальные проверки | Подтверждённые дефекты | Время, мин | Токены всего | Некэшированный ввод |',
            '|---|---:|---:|---:|---:|---:|']
    for r in rows:
        details=reviewed.get(key(r),{})
        bugcount=str(len(details.get('confirmed_defects',[]))) if details.get('reviewed') else 'не проверено'
        lines.append(f"| {short(r)} | {r['final_passed']}/{r['final_total']} | {bugcount} | {minutes(r['elapsed_seconds'])} | {fmt(r['total_tokens'])} | {fmt(r['uncached_input_tokens'])} |")
    if missing:lines+=['','Не завершены (нет метрик и оценок обоих этапов): '+', '.join(missing)+'.']
    lines+=['','| Сценарий / группа / повтор | Первая версия | Input | Cached input | Output | Команды | Неуспешные команды | Команды с runtime |',
            '|---|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        u=r['usage'] or {}
        lines.append(f"| {short(r)} | {r['phase1_passed']}/{r['phase1_total']} | {fmt(u.get('input_tokens'))} | {fmt(u.get('cached_input_tokens'))} | {fmt(u.get('output_tokens'))} | {r['commands']} | {r['failed_commands']} | {r['runtime_commands']} |")
    lines+=['','Неуспешная команда не обязательно означает баг продукта: это также поиск '
            'отсутствующего файла, неверный аргумент инструмента или ошибка среды. '
            'Команды с runtime — внешние команды, содержащие session.py, а не число внутренних вызовов. '
            'Количество дефектов основано на воспроизводимых отклонениях поведения, '
            'объединённых по причине; оно не равно числу упавших assertion.','',
            '## Проверка стенда','',
            correction_note,'',
            '## Ошибки и передача сессии','']
    for r in rows:
        k=key(r);d=reviewed.get(k,{})
        lines.append(f'### {title(r)}')
        lines.append('')
        for defect in d.get('confirmed_defects',[]):
            lines.append('- '+defect['description']+' Воспроизведение: '+defect['reproduction'])
        if d.get('reviewed') and not d.get('confirmed_defects'):lines.append('Подтверждённых дефектов в проверенном наборе не обнаружено.')
        if d.get('evaluator_notes'):lines.append(d['evaluator_notes'])
        if d.get('handover'):lines.append('Передача: '+d['handover'])
        lines+=['',f"Источники: [grade-1](cases/{k}/{sub}grade-1.json), [grade-2](cases/{k}/{sub}grade-2.json), "
                    f"[metrics-1](cases/{k}/metrics-1.json), [metrics-2](cases/{k}/metrics-2.json), "
                    f"[первая сессия](cases/{k}/events-1.jsonl), [продолжение](cases/{k}/events-2.jsonl).",'']
    if extra:
        lines+=['## Дополнительные проверки','',
                f"Пройдено {extra['passed']}/{extra['total']}: стабильность идентификатора при edit, "
                '100 уникальных добавлений после восстановления со старым счётчиком, '
                'победа в игре только клавиатурой, сохранение рекорда после reload '
                'и повреждённое хранилище рекорда. Проверки одинаковы для всех групп '
                'и не входят в основной балл. [Результаты](extra-checks.json).','']
        if (out/'extra-checks-v1.json').exists():
            lines+=['В первой версии дополнительной проверки слишком узкий regex отверг '
                    'корректный текст победы контрольной игры; matcher исправлен и весь '
                    'дополнительный набор повторён для обеих групп. '
                    '[Первоначальный результат](extra-checks-v1.json).','']
    if audit:
        scope='соответствие промптов группам, записанный порядок, ' if 'repetitions' in audit else ''
        lines+=['## Аудит наблюдений','',
                f"{audit['passed']}/{audit['total']} проверок целостности: различных чатов — {audit.get('chat_count','?')}, "
                'нативная телеметрия, одинаковые стартовые файлы, изоляция скилов, '+scope+
                'неизменность замороженных исходников и копий плагина, завершение '
                'сессий и освобождение фаз в группе estafeta. [Детали](audit.json).','']
    if review.get('conclusion'):lines+=['## Вывод','',review['conclusion'],'']
    order_note=('Случайный сбалансированный порядок распределяет влияние времени запуска между '
                'группами, но не устраняет его. ' if 'seed' in protocol else
                'Порядок прогонов фиксирован, а не случайный. ')
    lite_note=('Lite-группа получает только текст конвенций, без скилов и runtime; соблюдение '
               'конвенций баллами не оценивается. ' if 'lite' in arms else '')
    links=(['[Итоговая переоценка](adjudicated-results.json)'] if adjudicated else [])+[
           '[Сырые результаты](results.json)','[Протокол](protocol.json)','[Хэши исходников](source-hashes.json)']+(
           ['[Ручной аудит](review.json)'] if (out/'review.json').exists() else [])
    lines+=['## Границы вывода','',
            f'Повторов на сочетание сценария и группы: {reps}; статистическая значимость не '
            'проверялась. Серверная нагрузка и состояние кэша полностью не контролируются. '
            +order_note+'Все задания небольшие и используют одну модель/провайдера; параллельные '
            'рабочие сессии и другие устройства здесь не сравнивались. Оценивался явно вызванный '
            'набор скилов, включая scripts; самостоятельное обнаружение скилов по обычному запросу '
            'не проверялось. '+lite_note+'Проверки покрывают перечисленные группы поведения, а не '
            'все возможные баги, качество визуального дизайна или готовность к production. '
            'Денежная стоимость и серверный TTFT не измерялись. Оптимизация общего промпта сама '
            'по себе не оценивалась A/B: она применена во всех группах. Скилы установлены локально '
            'в проект и остаются untracked относительно стартового Git-коммита; их файлы попадают '
            'в общий инвентарь checkpoint. Такая установка может добавлять расходы относительно '
            'готовой установки на уровне пользователя. Проверялся режим Default с явным вызовом '
            'всех четырёх скилов; режим Eco отдельно не оценён.','',
            'Ценность на длинных проектах этот стенд не устанавливает: для неё нужны более длинные '
            'проекты, принудительный обрыв и параллельная работа над одним проектом '
            '(docs/BENCHMARK-ROADMAP.md).','',
            ' · '.join(links)]
    (out/'REPORT.ru.md').write_text('\n'.join(lines)+'\n')
    medians={cell_key:(middle(cell(*cell_key,'elapsed_seconds')),middle(cell(*cell_key,'total_tokens'))) for cell_key in planned}
    maxtime=max([t for t,_ in medians.values() if t is not None] or [1]) or 1
    maximum=max([n for _,n in medians.values() if n is not None] or [1]) or 1
    def bar(value,top,color):
        if value is None:return '<div class="track unknown"></div>'
        return f'<div class="track"><i style="width:{100*value/top:.1f}%;background:{color}"></i></div>'
    cards=[]
    for s in scenarios:
        content=[]
        for a in arms:
            if (s,a) not in planned:continue
            color=COLORS.get(a,'#5d6b7e');time_median,token_median=medians[(s,a)]
            samples=' · '.join(f'r{rep}: <a href="cases/{key(by[(s,a,rep)])}/{sub}mobile-2.png">интерфейс</a>, '
                               f'<a href="cases/{key(by[(s,a,rep)])}/{sub}grade-2.json">проверки</a>'
                               for rep in sorted(planned[(s,a)]) if (s,a,rep) in by)
            content.append(f'<div class="sample"><b>{html.escape(ARMS.get(a,a))}</b>'
                           f'<span>Финальные проверки: {html.escape(spread(cell(s,a,"final_passed"),count))} из {totals(s,a)}</span>'
                           f'<label>Время, мин: {html.escape(spread(cell(s,a,"elapsed_seconds"),minutes))}</label>{bar(time_median,maxtime,color)}'
                           f'<label>Токены: {html.escape(spread(cell(s,a,"total_tokens"),fmt))}</label>{bar(token_median,maximum,color)}'
                           f'<small>{samples or "нет завершённых повторов"}</small></div>')
        cards.append('<section><h2>'+html.escape(NAMES.get(s,s))+'</h2>'+''.join(content)+'</section>')
    conclusion=html.escape(review.get('conclusion','Результаты требуют ручной проверки дефектов.'))
    subtitle=html.escape(f"Сценариев: {len(scenarios)} · групп: {len(arms)} · повторов: {reps} · "
                         f"свежих сессий: {2*cases} · {protocol['model']} / {protocol['effort']}")
    footer=html.escape(f'Значения: медиана (мин–макс) по повторам; unknown — значения нет хотя бы в одном '
                       f'повторе, нулём оно не заменяется. Повторов на ячейку: {reps}; сравнение описательное, '
                       'без статистической значимости. Кэшированные токены входят в input; денежная цена не измерялась.')
    (out/'report.html').write_text('''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>estafeta — сравнение групп</title><style>body{font:16px/1.5 system-ui;margin:0;background:#f2f4f8;color:#172235}main{max-width:1200px;margin:auto;padding:40px 24px}h1{font-size:36px;line-height:1.15}h2{font-size:23px}article{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}section{background:white;padding:24px;border-radius:18px;border:1px solid #dce1e8}.sample{margin-top:26px}.sample b,.sample label,.sample small{display:block}.sample span{color:#53702b}.sample small{color:#536174}.track{height:12px;background:#eef0f4;border-radius:8px;margin:6px 0 16px}.track.unknown{background:repeating-linear-gradient(45deg,#eef0f4 0 6px,#e1e4ea 6px 12px)}.track i{height:12px;display:block;border-radius:8px}a{color:#315ba9}.note{max-width:1000px;padding:24px;background:white;border-radius:18px;margin-top:24px}footer{color:#536174;margin-top:24px}@media(max-width:850px){article{grid-template-columns:1fr}}</style><main><h1>estafeta: реальная цена управления сессией</h1><p>'''+subtitle+'''</p><article>'''+''.join(cards)+'''</article><div class="note">'''+conclusion+'''</div><footer>'''+footer+'''<p><a href="REPORT.ru.md">Полный отчёт</a> · <a href="results.json">Сырые метрики</a> · <a href="protocol.json">Протокол</a></p></footer></main></html>''')
    print(str(out/'REPORT.ru.md'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();main(Path(a.output))
