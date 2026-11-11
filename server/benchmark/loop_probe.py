"""Diagnostic candidates for task fixation, not a semantic correctness judge."""
import re


def question_sentences(text):
    return [s.strip() for s in re.findall(r'[^。！？!?\n]+[。！？!?]?', text)
            if re.search(r'[?？]|教えて|聞かせ.*(?:ください|くれ)', s)]


def signals(case, index, text):
    spec = case.get('loop_probe')
    mode = case.get('dialogue', [{}])[index].get('loop_probe') if spec else None
    if mode is None:
        return {}
    # A purpose question may omit the old object's name. Restrict this signal to
    # explicitly labelled probes; retain evidence for semantic review.
    sentences = re.findall(r'[^。！？!?\n]+[。！？!?]?', text)
    candidates = [s.strip() for s in sentences
                  if re.search(spec['question_pattern'], s)
                  and re.search(r'[?？]|教えて|教え[てる]|聞かせ|ですか|ますか', s)]
    old = [m.get('content', '') for m in case['messages'] if m['role'] == 'assistant']
    normalize = lambda s: re.sub(r'\s+', '', s).strip('。！？!?')
    old_sentences = {normalize(s) for t in old for s in re.split(r'[。！？!?\n]+', t) if s.strip()}
    return dict(mode=mode, question_candidates=candidates,
                topic_mentioned=bool(re.search(spec['topic_pattern'], text)),
                seed_echoes=sum(normalize(s) in old_sentences for s in candidates))


def metrics(case, row):
    """Only generated responses count; fixed seed history is not model output."""
    if not case.get('loop_probe'):
        return {}, {}
    by_turn, hits, reasked = {}, [], []
    previous_questions = set()
    turns = {t['index']: t for t in row.get('turns', [])}
    for index, spec in enumerate(case['dialogue']):
        turn = turns.get(index)
        text = '\n'.join(m.get('content') or '' for m in (turn or {}).get('response', []))
        valid = turn and turn['status'] == 'ok' and bool(text.strip())
        found = signals(case, index, text)
        if not found:
            continue
        forbidden = found['mode'] == 'forbidden'
        value = int(bool(found['question_candidates'])) if valid else None
        questions = question_sentences(text)
        normalize = lambda s: re.sub(r'\s+', '', s).strip('。！？!?')
        repeats = [s for s in questions if normalize(s) in previous_questions]
        found['reasked_questions'] = repeats
        if valid:
            previous_questions.update(normalize(s) for s in questions)
        by_turn[index] = dict(evidence=found, metrics={
            'loop_question_candidate': (value, 'lower' if forbidden else 'neutral', 'turns'),
            'loop_reasked_question_candidates': (len(repeats) if valid else None,
                                                  'lower' if forbidden else 'neutral', 'sentences'),
            'loop_topic_mention': (int(found['topic_mentioned']) if valid else None, 'neutral', 'turns'),
            'loop_seed_question_echoes': (found['seed_echoes'] if valid else None,
                                          'lower' if forbidden else 'neutral', 'sentences')})
        # Allowed probes break a forbidden run and never count as bad questions.
        hits.append(value if forbidden else 0)
        reasked.append((int(bool(repeats)) if valid else None) if forbidden else 0)
    complete = row['status'] == 'ok' and len(turns) == len(case['dialogue']) and None not in hits
    longest = current = 0
    for hit in hits:
        current = current + 1 if hit else 0
        longest = max(longest, current)
    totals = {
        'loop_candidate_turns': (sum(hits) if complete else None, 'lower', 'turns'),
        'loop_candidate_longest_run': (longest if complete else None, 'lower', 'turns'),
        'loop_reasked_turns': (sum(reasked) if complete else None, 'lower', 'turns'),
    }
    return totals, by_turn
