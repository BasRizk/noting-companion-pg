import os
import sys
import json
import openai
from tabulate import tabulate
from nb_progress import NBStep
from parsers.nb_parser import CellEntry
from parsers.log_parser import LogParser
from nb_progress import get_notebook_progress, NotebookParser, InvalidLogError
from utils import (
    get_all_file_with_extension_in_dir_recursively,
    prettify_str,
    logger
)
from prompts.code_explain import code_explain_prompt
from prompts.generate_questions import make_questions_prompt

def generate_questions(applied_changes_nb_states, explanations, prev_generated_questions):
    generated_questions = []
    for i in range(len(applied_changes_nb_states)-1):
        print('><'*50)
        nb_state_i = applied_changes_nb_states[i]
        nb_state_i_plus_1 = applied_changes_nb_states[i+1]
        explanation_i = explanations[i]
        explanation_i_plus_1 = explanations[i+1]
        generated_questions.append(
            make_questions_prompt(
                nb_state_i, nb_state_i_plus_1,
                explanation_i, explanation_i_plus_1,
                prev_generated_questions + generated_questions
            )
        )
        # logger.trace(f'Generate Questions Prompt messages:\n{prettify_str(prompt)}')
        # generated_questions.append(call_llm(prompt))
        logger.trace(f'Generated Questions:\n {prettify_str(generated_questions[-1])}')
        print('><'*50)

    return generated_questions

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--notebooks_dir', type=str, default='data/tac_notebooks')
    parser.add_argument('--logs_dir', type=str, default='data/tac_raw_logs')
    # parser.add_argument('--log_filepath', type=str, default=None)
    # parser.add_argument('--nb_filepath', type=str, default=None)
    parser.add_argument('--append_prev_msgs', action='store_true', default=False)
    args = parser.parse_args()

    # set logger to trace to see all logs
    logger.remove()
    logger.add(sys.stderr, level="TRACE")
    import uuid
    logger_id = str(uuid.uuid4())
    logger.add(f'logs/analyze_nb_logs_{logger_id}.log', level="TRACE")
    logger.info(f'Logger ID: {logger_id}')

    all_log_filepathes = get_all_file_with_extension_in_dir_recursively(args.logs_dir, ".log")
    all_log_filepathes.sort()
    # skip files containing baseline
    all_log_filepathes = [log_filepath for log_filepath in all_log_filepathes if "baseline" not in log_filepath]
    logger.success(f'There are {len(all_log_filepathes)} log files in {args.logs_dir} directory')

    if len(all_log_filepathes) == 0:
        raise Exception(f'No log files found in {args.logs_dir} directory')
    if len(all_log_filepathes) > 1:
        _indexed_log_filepathes = list(enumerate(all_log_filepathes))
        _input = input(f'More than one log files found in {args.logs_dir} directory. Press Enter to continue, or Pick index from 0 to {len(all_log_filepathes)-1} to select log file of the following list:\n{_indexed_log_filepathes}\n')
        if _input:
            selected_log_filepath = all_log_filepathes[int(_input)]
        else:
            selected_log_filepath = all_log_filepathes[0]


    selected_log_filepath = all_log_filepathes[1]
    log_parser = LogParser(selected_log_filepath).parse()
    log_parser_per_notebook = log_parser.attach_notebooks(args.notebooks_dir, verbose=False)
    logger.info(
        'Sample:' +\
        f'\nSelected log file: {selected_log_filepath}' +\
        f'\nfetching notebooks from log file: {args.notebooks_dir}' +\
        f'\nLog parser per these notebooks:\n{log_parser_per_notebook.keys()}'
    )


    def tabulate_aligned_msg_nb_cells(explanation, step: NBStep, change_i: int, nb_parser_with_change_applied: NotebookParser):
        from copy import deepcopy
        nb_cells_explanation = deepcopy(explanation['cells'])
        nb_summary = explanation['summary']


        # if change_i is not None:
        #     nb_cells_explanation[step.cell_id]['content'] = step.entries[change_i].get_formatted_content()
        #     nb_cells_explanation[step.cell_id]['action'] = step.get_change_type(change_i)


        table = [[
            'Cell ID', 'Assitant Msg', 'NB Cell'
        ]]
        for explanation_per_cell, nb_cell in zip(nb_cells_explanation, nb_parser_with_change_applied):
            nb_cell: CellEntry
            table.append([
                explanation_per_cell['cell_id'],
                prettify_str(explanation_per_cell, text_width=30),
                nb_cell.tabulate(text_width=50)
            ])

        table.append(['', '', ''])
        table.append(['Summary', prettify_str(nb_summary, text_width=30)])

        return tabulate(table, tablefmt="fancy_grid", colalign=("right", "left"), stralign="center", numalign="center")


    def perform_explain_change_on_nb_parser(
        nb_parser_with_change_applied: NotebookParser,
        step: NBStep,
        step_i: int,
        applied_changes_nb_states: list,
        change_i: int=None
    ):
        # Use default prompt -- will be appended automatically by code_explain_prompt
        prev_msgs = []
        for prev_change, prev_response in zip(applied_changes_nb_states, explanations):
            prev_msgs.append({ "role": "user", "content": str(prev_change)})
            prev_msgs.append(prev_response)

        print('><'*50)
        if change_i is None:
            logger.warning(f'NB Step {step_i} @ {step.cell_id}, No Change.')
        else:
            logger.debug(f'NB Step {step_i} Change({change_i}) {step.get_change_type(change_i)} @ {step.cell_id}, '
                         f'Change Definition:\n{step.entries[change_i].tabulate()}')
        print('><'*50)

        while True:
            try:
                if args.append_prev_msgs:
                    explanation = code_explain_prompt(nb_parser_with_change_applied, prev_messages=prev_msgs)
                else:
                    explanation = code_explain_prompt(nb_parser_with_change_applied)
                break
            except openai.BadRequestError as e:
                if len(prev_msgs) > 0:
                    logger.warning(f'Error, retrying with fewer prev_msgs: {len(prev_msgs)}')
                    prev_msgs = prev_msgs[-1:]
                else:
                    raise e

        applied_changes_nb_states.append(nb_parser_with_change_applied)
        table = tabulate_aligned_msg_nb_cells(explanation, step, change_i, nb_parser_with_change_applied)

        if change_i is None:
            logger.info(f'NB Step {step_i} (Starter Code - No Change) Response:\n{table}')
        else:
            logger.info(f'NB Step {step_i} Change({change_i}) Response:\n {table}')

        return explanation



    for i, (nb_filepath, (nb_log_parser, nb_parser)) in enumerate(log_parser_per_notebook.items()):
        # try:
        logger.success(f'{i} Processing notebook: {nb_filepath} with {len(nb_parser)} cells, using {nb_log_parser.filepath} log')
        logger.trace(f'{i} nb_parser:\n{nb_parser}')

        try:
            nb_progress = get_notebook_progress(nb_parser, nb_log_parser)
        except InvalidLogError as e:
            logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_filepath}) and nb_log_parser({nb_log_parser.filepath})')
            continue

        nb_parser_filename = os.path.basename(nb_parser.filepath)
        nb_log_parser_filename = os.path.basename(nb_log_parser.filepath)

        logger.info(f'Notebook: {nb_parser.filepath}')
        logger.info(f'Log: {nb_log_parser.filepath}')
        logger.info(f'Number of progress steps: {len(nb_progress)}')
        logger.info(f'Number of progress steps unrolled: {sum([len(step) for step in nb_progress])}')

        explanations = []
        applied_changes_nb_states = []
        generated_questions = []
        for step_i, step in enumerate(nb_progress):
            step.reset()
            if len(step) == 0:
                explanations.append(
                    perform_explain_change_on_nb_parser(
                        nb_parser,
                        step,
                        step_i,
                        applied_changes_nb_states
                    )
                )
            else:
                # prev_msgs = [] # TODO should I reset prev_msgs upon each completed step?
                for change_i, nb_parser_with_change_applied in enumerate(step):
                    explanations.append(
                        perform_explain_change_on_nb_parser(
                            nb_parser_with_change_applied,
                            step,
                            step_i,
                            applied_changes_nb_states,
                            change_i=change_i
                        )
                    )

            if len(explanations) >= 2:
                _questions = generate_questions(
                    applied_changes_nb_states[-2:], explanations[-2:],
                    prev_generated_questions=generated_questions
                )
                assert len(_questions) == 1, f'Expected 1 question, got {_questions}'
                generated_questions.append(_questions[0])

        # TODO print differences rather than just the change
        changes_definitions = []
        for step in nb_progress:
            for change_i in range(len(step.entries)):
                entry_table = step.entries[change_i].tabulate()
                changes_definitions.append(entry_table)

        logger.success(f'All steps completed for {nb_parser.filepath} with {len(nb_progress)} steps getting {len(generated_questions)} sets of questions')
        for i, (change_questions, change_definition) in enumerate(zip(generated_questions, changes_definitions)):
            logger.success(
                f'@ Change {i}:\n {change_definition}\n Questions: \n{prettify_str(change_questions)}'
            )
        # if input('Continue? (y/n)') == 'n':
        #     break
        breakpoint()

