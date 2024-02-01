import os
import time
import json
import uuid
import datetime
from tqdm import tqdm
from loguru import logger
from utils import (
    chat_completions_with_backoff,
    count_tokens_in_prompt_messages,
    Tee,
    pprint_msg,
)


def _is_todo_cell(cell):
    _first_line_split = cell['source'][0].lower().split('#')
    if len(_first_line_split) > 1:
        if _first_line_split[1].strip().startswith('todo'):
            return True
    return False

def remove_one_todo(cells, remove_type='code', direction='top', replace=None):
    _cells = cells if direction == 'top' else reversed(cells)
    for cell in _cells:
        if cell['cell_type'] != 'code':
                continue
        if _is_todo_cell(cell):
            if remove_type == 'code':
                if len(cell['source']) > 1:
                    _code = cell['source'][1:]
                    cell['source'] = cell['source'][:1]
                    if replace is not None:
                        cell['source'] += replace
                    return _code
            elif remove_type == 'statement':
                _statement = cell['source'][0]
                cell['source'] = cell['source'][1:]
                if replace is not None:
                    cell['source'] += replace
                return _statement
            else:
                raise Exception('remove_type must be either code or statement')

    return None

with open('code_explain.system_prompt') as f:
    sys_prompt = ''.join(f.readlines())

def prompt(
    cells,
    prev_messages=None,
    # model="gpt-4",
    # model='gpt-3.5-turbo-16k-0613',
    model='gpt-3.5-turbo-16k',
    ):
    if prev_messages is None:
        prev_messages = [{ "role": "system", "content": sys_prompt}]
    _messages = prev_messages + [{ "role": "user", "content": str(cells)}]

    num_tokens = count_tokens_in_prompt_messages(_messages, model_name=model)
    logger.debug(f'num_tokens from prompt: {num_tokens}')
    if num_tokens > 16000:
        logger.error('Too many tokens, splitting into multiple prompts')
        breakpoint()

    response = chat_completions_with_backoff(
        model=model,
        messages=_messages,
        temperature=0,
        max_tokens=num_tokens*3,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
    )

    response_msg = response['choices'][0]['message']
    num_tokens_from_response = count_tokens_in_prompt_messages([response_msg], model_name=model)
    logger.debug(f'num_tokens from response: {num_tokens_from_response}')
    breakpoint()
    return response_msg




if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--notebook_filepath', type=str, default='../knic-notebooks/MT/MT-S-1.ipynb')
    args = parser.parse_args()

    notebook_filepath = args.notebook_filepath
    notebook_filename = os.path.basename(notebook_filepath)
    with open(notebook_filepath) as f:
        notebook = json.load(f)


    unique_log_name = f'{notebook_filename}-{str(datetime.datetime.now())}-{str(uuid.uuid4())}'
    tee = Tee(f'{unique_log_name}.txt')

    def print(*args, **kwargs):
        with tee:
            return __builtins__.print(*args, **kwargs)


    prompt_cells = notebook['cells'].copy()
    todo_code_blocks = []
    while True:
        _todo_code = remove_one_todo(prompt_cells, remove_type='code')
        if _todo_code is not None:
            todo_code_blocks.append(_todo_code)
        else:
            break

    # simplfiy notebook cells
    for idx, cell in enumerate(prompt_cells):
        cell['id'] = idx
        if cell.get('outputs') is not None:
            del cell['outputs']
        if cell.get('execution_count') is not None:
            del cell['execution_count']
        del cell['metadata']

    # no code solved yet
    logger.info('Notebook step by step:')
    assistant_msgs = []
    assistant_msgs.append(prompt(prompt_cells, prev_messages=None))
    pprint_msg(assistant_msgs[-1])
    for i, code in tqdm(enumerate(todo_code_blocks), total=len(todo_code_blocks)):
        # a step by step the code is getting solved; prompt to explain
        remove_one_todo(prompt_cells, remove_type='statement', replace=code)
        assistant_msgs.append(prompt(prompt_cells, prev_messages=None))
        pprint_msg(assistant_msgs[-1])



    logger.info('Notebook progression explanation:')

    assistant_combination = json.loads(assistant_msgs[0]['content'])
    for i in range(len(assistant_combination)):
        assistant_combination[i] = {'iteration_idx': [0], 'iterations_detail': [assistant_combination[i]]}

    for i in range(1, len(assistant_msgs)):
        later_assistant_response = json.loads(assistant_msgs[i]['content'])
        for new_iter, past_iters in zip(later_assistant_response, assistant_combination):
            # filter out explanation if it is the same as the previous one
            if new_iter.get('cell_explanation') is not None:
                if new_iter['cell_explanation'] == past_iters['iterations_detail'][-1]['cell_explanation']:
                    continue
            elif new_iter.get('summary'):
                if new_iter['summary'] == past_iters['iterations_detail'][-1]['summary']:
                    continue

            past_iters['iteration_idx'].append(i)
            past_iters['iterations_detail'].append(new_iter)

    # save combination
    with open(f'{unique_log_name}-combination.json', 'w') as f:
        json.dump(assistant_combination, f, indent=4)

    print(json.dumps(assistant_combination, indent=4))