
import os
import sys
import json
import openai
from parsers.log_parser import LogParser
from nb_progress import get_notebook_progress, NotebookParser, InvalidLogError
from utils import (
    construct_code_explain_prompt,
    construct_make_questions_prompt,
    call_llm,
    pprint_assistant_msg,
    get_all_file_with_extension_in_dir_recursively,
    Tee, prettify_str,
    logger
)

def generate_questions(applied_changes_nb_states, assistant_msgs, prev_generated_questions):
    generated_questions = []
    for i in range(len(applied_changes_nb_states)-1):
        print('><'*50)
        nb_state_i = applied_changes_nb_states[i]
        nb_state_i_plus_1 = applied_changes_nb_states[i+1]
        assistant_msg_i = assistant_msgs[i]
        assistant_msg_i_plus_1 = assistant_msgs[i+1]
        prompt = construct_make_questions_prompt(
            nb_state_i, nb_state_i_plus_1,
            assistant_msg_i, assistant_msg_i_plus_1,
            prev_generated_questions + generated_questions
        )
        logger.trace(f'Generate Questions Prompt messages:\n{prettify_str(prompt)}')
        generated_questions.append(call_llm(prompt))
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

    from nb_progress import NBStep

    def print_aligned_msg_nb_cells(assistant_msg, step: NBStep, change_i: int, nb_parser_with_change_applied: NotebookParser):
        role, content = assistant_msg
        # content = content.copy()
        try:
            content = json.loads(content)
        except:
            try:
                content = eval(content)
            except:
                print('Could not parse content')
                breakpoint()
            # except:
            #     content = assistant_msg['content']

        # nb_parser_with_change_applied

        if change_i is not None:
            content[step.cell_id]['content'] = step.entries[change_i].get_formatted_content()
            content[step.cell_id]['action'] = step.get_change_type(change_i)

        from tabulate import tabulate

        table = [[
            'Cell ID', 'Assitant Msg', 'NB Cell'
        ]]
        for explanation_per_cell, nb_cell in zip(content, nb_parser_with_change_applied):
            table.append([
                explanation_per_cell['cell_id'],
                prettify_str(explanation_per_cell, text_width=30),
                NotebookParser.tabulate_cell(nb_cell, text_width=50, call_tabulate=True),
            ])

        table.append(['', '', ''])
        table.append(['Summary', prettify_str(content[-1], text_width=30)])

        print(tabulate(table, tablefmt="fancy_grid", colalign=("right", "left"), stralign="center", numalign="center"))

    def perform_explain_change_on_nb_parser(
        nb_parser_with_change_applied: NotebookParser,
        step: NBStep,
        step_i: int,
        applied_changes_nb_states: list,
        change_i: int=None
    ):
        # Use default prompt -- will be appended automatically by code_explain_prompt
        prev_msgs = []
        for prev_change, prev_response in zip(applied_changes_nb_states, assistant_msgs):
            prev_msgs.append({ "role": "user", "content": str(prev_change)})
            prev_msgs.append(prev_response)

        print('><'*50)
        if change_i is None:
            logger.debug(f'NB Step {step_i} @ {step.cell_id}, No Change')
        else:
            logger.debug(f'NB Step {step_i} Change({change_i}) {step.get_change_type(change_i)} @ {step.cell_id}, Change Definition:')
            print(step.entries[change_i].print())
        print('><'*50)

        while True:
            try:
                if args.append_prev_msgs:
                    prompt = construct_code_explain_prompt(nb_parser_with_change_applied, prev_messages=prev_msgs)
                else:
                    prompt = construct_code_explain_prompt(nb_parser_with_change_applied)
                logger.trace(f'Code Explain Prompt messages:\n{prettify_str(prompt)}')
                assistant_msg = call_llm(prompt)
                break
            except openai.BadRequestError as e:
                if len(prev_msgs) > 0:
                    logger.warning(f'Error, retrying with fewer prev_msgs: {len(prev_msgs)}')
                    prev_msgs = prev_msgs[-1:]
                else:
                    raise e

        applied_changes_nb_states.append(nb_parser_with_change_applied)

        if change_i is None:
            print(f'NB Step {step_i} (Starter Code - No Change) Response:')
        else:
            print(f'NB Step {step_i} Change({change_i}) Response:')

        print_aligned_msg_nb_cells(assistant_msg, step, change_i, nb_parser_with_change_applied)
        return assistant_msg



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
        tee = Tee(f'{nb_parser_filename}_{nb_log_parser_filename}.description_sequence')
        def print(*args, **kwargs):
            with tee:
                return __builtins__.print(*args, **kwargs)

        print(f'Notebook: {nb_parser.filepath}')
        print(f'Log: {nb_log_parser.filepath}')
        print(f'Number of progress steps: {len(nb_progress)}')
        print(f'Number of progress steps unrolled: {sum([len(step) for step in nb_progress])}')

        assistant_msgs = []
        applied_changes_nb_states = []
        generated_questions = []
        for step_i, step in enumerate(nb_progress):
            step.reset()
            if len(step) == 0:
                assistant_msgs.append(
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
                    assistant_msgs.append(
                        perform_explain_change_on_nb_parser(
                            nb_parser_with_change_applied,
                            step,
                            step_i,
                            applied_changes_nb_states,
                            change_i
                        )
                    )

            if len(assistant_msgs) >= 2:
                _questions = generate_questions(applied_changes_nb_states[-2:], assistant_msgs[-2:], prev_generated_questions=generated_questions)
                assert len(_questions) == 1, f'Expected 1 question, got {_questions}'
                generated_questions.append(_questions[0])

        logger.success(f'Final notebook state:')
        print(nb_parser)
        # print(f'Final log state:')
        # print(nb_log_parser)
        logger.success(f'Final assistant msgs:')
        for assistant_msg in assistant_msgs:
            pprint_assistant_msg(assistant_msg)

        # if input('Continue? (y/n)') == 'n':
        #     break
        breakpoint()

        # generate_questions(applied_changes_nb_states, assistant_msgs)

