from textwrap import wrap
from tabulate import tabulate
from langchain_core.prompts import (
    ChatPromptTemplate,
    PromptTemplate
)
from loguru import logger
from typing import List
from parsers.nb_parser import NotebookParser
from parsers.log_parser import LogParser
from nb_progress import get_notebook_progress_using_log, InvalidLogError, NotebookStateLogMismatchError


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

def generate_nb_states(nb_progress):
    nb_states: List[NotebookParser] = []
    for step_i, step in enumerate(nb_progress):
        step.reset()
        if len(step) == 0:
            nb_states.append(step.nb_parser_state)
        else:
            # prev_msgs = [] # TODO should I reset prev_msgs upon each completed step?
            for change_i, nb_parser_with_change_applied in enumerate(step):
                nb_states.append(
                    nb_parser_with_change_applied
                )
    return nb_states



def get_selected_logged_sessions(notebooks_dir, logs_dir, min_num_steps=4):
    all_log_filepathes = get_all_file_with_extension_in_dir_recursively(logs_dir, ".log")
    all_log_filepathes.sort()
    # skip files containing baseline
    all_log_filepathes = [log_filepath for log_filepath in all_log_filepathes if "baseline" not in log_filepath]
    logger.success(f'There are {len(all_log_filepathes)} log files in {logs_dir} directory')

    selected_sessions = []
    for selected_log_filepath in all_log_filepathes:
        log_parser = LogParser(selected_log_filepath).parse()
        nb_sublog_dict = log_parser.attach_notebooks(notebooks_dir, verbose=False)
        # logger.debug(
        #     'Sample:' +\
        #     f'\nSelected log file: {selected_log_filepath}' +\
        #     f'\nfetching notebooks from log file: {notebooks_dir}' +\
        #     f'\nLog parser per these notebooks:\n{nb_sublog_dict.keys()}'
        # )

        for i, (nb_filepath, (nb_log_parser, nb_parser)) in enumerate(nb_sublog_dict.items()):
            try:
                nb_progress = get_notebook_progress_using_log(nb_parser, nb_log_parser)
            except InvalidLogError as e:
                # logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath}) and nb_log_parser({nb_log_parser.filepath})')
                continue
            except NotebookStateLogMismatchError as e:
                # logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath}) and nb_log_parser({nb_log_parser.filepath})')
                continue

            nb_states = generate_nb_states(nb_progress)
            num_progress_steps = len(nb_progress)
            if num_progress_steps >= min_num_steps:
                # logger.info(f'Notebook: {nb_parser.filepath}')
                # logger.info(f'Log: {nb_log_parser.filepath}')
                # logger.info(f'Number of progress steps: {num_progress_steps}')
                selected_sessions.append((nb_parser, nb_log_parser, nb_progress, nb_states))


    return selected_sessions

import os
from nb_progress import get_notebook_progress_simulate
def get_selected_simulated_sessions(notebooks_dir, min_num_steps=4):
    nb_filename_dict = {
        os.path.basename(nb_filepath): nb_filepath
        for nb_filepath in
        get_all_file_with_extension_in_dir_recursively(notebooks_dir, ".ipynb")
    }

    logger.success(f'There are {len(nb_filename_dict)} notebooks found in {notebooks_dir} directory')

    selected_sessions = []
    for i, nb_parser in enumerate(map(NotebookParser, nb_filename_dict.values())):
        try:
            nb_progress = get_notebook_progress_simulate(nb_parser)
        except InvalidLogError as e:
            logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath})')
            continue

        nb_states = generate_nb_states(nb_progress)
        num_progress_steps = len(nb_progress)
        if num_progress_steps >= min_num_steps:
            # logger.info(f'Notebook: {nb_parser.filepath}')
            # logger.info(f'Number of progress steps: {num_progress_steps}')
            selected_sessions.append((nb_parser, nb_progress, nb_states))
    return selected_sessions