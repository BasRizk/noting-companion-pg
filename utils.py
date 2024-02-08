# import backoff
import traceback
import sys
# import os
# import openai
import tiktoken
import json

from typing import List, Tuple
from textwrap import wrap
from loguru import logger
from tabulate import tabulate
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# openai.api_key = os.getenv("OPENAI_API_KEY")
GPT_MODEL_NAME = 'gpt-3.5-turbo-16k'

def call_llm(prompt):
    llm = ChatOpenAI(
        model=GPT_MODEL_NAME
        # messages=_messages, # TODO check langchain args signature
        # temperature=0,
        # max_tokens=num_tokens*3,
        # top_p=1,
        # frequency_penalty=0,
        # presence_penalty=0,
    )
    output_parser = StrOutputParser()
    chain = prompt | llm | output_parser

    response_msg = ('assistant', chain.invoke({}))
    num_tokens_from_response = count_tokens_in_prompt_messages([response_msg])
    print(f'num_tokens from response: {num_tokens_from_response}')
    return response_msg

def _skip_curly_brackets(content):
    return content.replace('{', '}}').replace('}', '}}')

def construct_code_explain_prompt(cells, prev_messages=[]):
    with open('prompts/code_explain.prompt') as f:
        sys_prompt = ''.join(f.readlines())

    if prev_messages and prev_messages[0].get('role') != 'system':
        raise Exception('First message must be system message')

    _msgs = [("system", sys_prompt)]
    for role, content in prev_messages:
        _msgs += [(role, _skip_curly_brackets(content))]

    if cells is not None:
        _msgs.append(("user", _skip_curly_brackets(str(cells))))

    num_tokens = count_tokens_in_prompt_messages(_msgs)
    print(f'num_tokens from prompt: {num_tokens}')
    if num_tokens > 16000:
        logger.error('Too many tokens, splitting into multiple prompts')
        breakpoint()

    return ChatPromptTemplate.from_messages(_msgs)

def construct_make_questions_prompt(nb_state_i, nb_state_i_plus_1, assistant_msg_i, assistant_msg_i_plus_1, prev_generated_questions: List[Tuple]):
    with open('prompts/make_questions.prompt') as f:
        sys_prompt = ''.join(f.readlines())

    _input = []
    _input.append(f'\nNotebook State 1:\n"""\n{str(nb_state_i)}\n"""\n')
    _input.append(f'\nExplanation of Notebook State 1:\n"""\n{assistant_msg_i[1]}\n"""\n')
    _input.append(f'\nNotebook State 2:\n"""\n{str(nb_state_i_plus_1)}\n"""\n')
    _input.append(f'\nExplanation of Notebook State 2:\n"""\n{assistant_msg_i_plus_1[1]}\n"""\n')

    prev_questions = "\n".join([content for _, content in prev_generated_questions])
    _input.append(f'\nFrom previous changes:\n"""\n{prev_questions}\n"""\n')

    _input = "\n".join(_input)


    _msgs = [("system", sys_prompt)]

    _msgs.append(("user", _skip_curly_brackets(str(_input))))

    num_tokens = count_tokens_in_prompt_messages(_msgs)
    print(f'num_tokens from prompt: {num_tokens}')
    if num_tokens > 16000:
        logger.error('Too many tokens, splitting into multiple prompts')
        breakpoint()

    return ChatPromptTemplate.from_messages(_msgs)


def count_tokens_in_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.encoding_for_model(GPT_MODEL_NAME)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def count_tokens_in_prompt_messages(messages: list) -> int:
    """Returns the number of tokens in a list of prompt messages."""
    num_tokens = 0
    for role, content in messages:
        num_tokens += count_tokens_in_string(content)
    return num_tokens


def pprint_assistant_msg(assistant_msg, width=100):
    print('='*width)
    role, content = assistant_msg
    print(f'{role} message:')
    try:
        prepared_json_format = json.loads(content)
    except:
        try:
            prepared_json_format = eval(content)
        except:
            prepared_json_format = content

    print(json.dumps(prepared_json_format, indent=4))
    print('='*width, '\n')

# Context manager that copies stdout and any exceptions to a log file
class Tee(object):
    def __init__(self, filename):
        self.file = open(filename, 'a+')
        self.filename = filename
        self.stdout = sys.stdout

    def __enter__(self):
        sys.stdout = self
        if self.file.closed:
            self.file = open(self.filename, 'a+')

    def __exit__(self, exc_type, exc_value, tb):
        sys.stdout = self.stdout
        if exc_type is not None:
            self.file.write(traceback.format_exc())
        self.file.close()


    def write(self, data):
        self.file.write(data)
        self.stdout.write(data)

    def flush(self):
        self.file.flush()
        self.stdout.flush()


def get_all_file_with_extension_in_dir_recursively(dir_path, extension):
    import os
    filepaths = []
    for root, dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith(extension):
                filepaths.append(os.path.join(root, file))
    return filepaths


def prettify_str(_obj, text_width=120, percentage=1.0):
    if isinstance(_obj, dict):
        _obj = _obj.copy()
        # tabulate and prettify value
        for k, v in _obj.items():
            _obj[k] = prettify_str(v, text_width=text_width, percentage=percentage*0.8)
        return tabulate(_obj.items(), tablefmt="fancy_grid")
    elif isinstance(_obj, tuple):
        _obj = list(_obj)
        for i, v in enumerate(_obj):
            _obj[i] = prettify_str(v, text_width=text_width, percentage=percentage*0.8)
        return tabulate([_obj], tablefmt="fancy_grid")
    elif isinstance(_obj, str):
        texts = ["\n".join(wrap(s, width=int(text_width*percentage))) for s in _obj.split('\n')]
        return "\n".join(texts)
    elif isinstance(_obj, list):
        _obj = _obj.copy()
        return  '\n'.join([prettify_str(_obj_i, text_width=text_width, percentage=percentage*0.8) for _obj_i in _obj])
    elif isinstance(_obj, bool) or isinstance(_obj, int) or isinstance(_obj, float):
        return str(_obj)
    elif isinstance(_obj, ChatPromptTemplate):
        table = []
        for i, langchain_msg in enumerate(_obj.messages):
            table.append(["[ID]: Role", f"[{i}]: {type(langchain_msg)}"])
            table.append(["input_variables", prettify_str(langchain_msg.prompt.input_variables, text_width=text_width, percentage=percentage*0.8)])
            table.append(["template", prettify_str(str(langchain_msg.prompt.template), text_width=text_width, percentage=percentage*0.8)])
        return tabulate(table, tablefmt="fancy_grid", colalign=("right", "left"), stralign="center", numalign="center")
    else:
        raise Exception(f"Type {type(_obj)} not supported for prettify_str")

