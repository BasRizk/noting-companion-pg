from textwrap import wrap
from tabulate import tabulate
from langchain_core.prompts import (
    ChatPromptTemplate,
    PromptTemplate
)
from loguru import logger


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
    elif isinstance(_obj, PromptTemplate):
        return prettify_str(vars(_obj), text_width=text_width, percentage=percentage)
    elif _obj is None:
        return "None"
    else:
        raise Exception(f"Type {type(_obj)} not supported for prettify_str")

