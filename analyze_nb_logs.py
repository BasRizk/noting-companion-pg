
import os
import sys
import json
import openai
from _log_parser import LogParser
from _nb_progress import get_notebook_progress
from _utils import (
    construct_code_explain_prompt,
    construct_make_questions_prompt,
    prompt,
    pprint_msg,
    get_all_file_with_extension_in_dir_recursively,
    Tee, prettify_str
)
from loguru import logger


def generate_questions(applied_changes_nb_states, assistant_msgs, prev_generated_questions=[]):
    generated_questions = prev_generated_questions
    for i in range(len(applied_changes_nb_states)-1):
        _input = []
        _input.append(f'\nNotebook State 1:\n"""\n{str(applied_changes_nb_states[i])}\n"""\n')
        _input.append(f'\nExplanation of Notebook State 1:\n"""\n{assistant_msgs[i]["content"]}\n"""\n')
        _input.append(f'\nNotebook State 2:\n"""\n{str(applied_changes_nb_states[i+1])}\n"""\n')
        _input.append(f'\nExplanation of Notebook State 2:\n"""\n{assistant_msgs[i+1]["content"]}\n"""\n')

        prev_questions = "\n".join([questions['content'] for questions in generated_questions])
        # prev_questions = []
        _input.append(f'\nFrom previous changes:\n"""\n{prev_questions}\n"""\n')

        _input = "\n".join(_input)

        print('><'*50)
        prompt_msgs = construct_make_questions_prompt(_input)
        logger.trace(f'Generate Questions Prompt messages:\n{prettify_str(prompt_msgs)}')
        generated_questions.append(prompt(prompt_msgs))

        logger.trace(f'Generated Questions:\n {prettify_str(generated_questions[-1])}')

        print('><'*50)
    breakpoint()

    return generated_questions

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--notebooks_dir', type=str, default='tac_notebooks')
    parser.add_argument('--logs_dir', type=str, default='tac_raw_logs')
    parser.add_argument('--log_filepath', type=str, default=None)
    parser.add_argument('--nb_filepath', type=str, default=None)
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

    from _nb_progress import NBStep

    def inject_content(assistant_msg, step: NBStep, change_i: int):
        assistant_msg = assistant_msg.copy()
        try:
            prepared_json_format = json.loads(assistant_msg['content'])
        except:
            try:
                prepared_json_format = eval(assistant_msg['content'])
            except:
                prepared_json_format = assistant_msg['content']

        prepared_json_format[step.cell_id]['content'] = step.entries[change_i].get_formatted_content()
        prepared_json_format[step.cell_id]['action'] = step.get_change_type(change_i)
        return {'content': prepared_json_format}


    for i, (nb_filepath, (nb_log_parser, nb_parser)) in enumerate(log_parser_per_notebook.items()):
        # try:
        logger.success(f'{i} Processing notebook: {nb_filepath} with {len(nb_parser)} cells, using {nb_log_parser.filepath} log')
        logger.trace(f'{i} nb_parser:\n{nb_parser}')
        nb_progress = get_notebook_progress(nb_parser, nb_log_parser)

        # except Exception as e:
        #     logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_filepath}) and nb_log_parser({nb_log_parser.filepath})')
        #     continue

        nb_parser_filename = os.path.basename(nb_parser.filepath)
        nb_log_parser_filename = os.path.basename(nb_log_parser.filepath)
        tee = Tee(f'{nb_parser_filename}_{nb_log_parser_filename}.description_sequence')
        def print(*args, **kwargs):
            with tee:
                return __builtins__.print(*args, **kwargs)

        # TODO check what len(progress) > 0 mean
        nb_progress = [progress for progress in nb_progress if len(progress) > 0]
        print(f'Notebook: {nb_parser.filepath}')
        print(f'Log: {nb_log_parser.filepath}')
        print(f'Number of progress steps: {len(nb_progress)}')
        print(f'Number of progress steps unrolled: {sum([len(step) for step in nb_progress])}')

        assistant_msgs = []
        applied_changes_nb_states = []
        generated_questions = []
        for step_i, step in enumerate(nb_progress):
            step.reset()
            # prev_msgs = [] # TODO should I reset prev_msgs upon each completed step?
            for change_i, nb_parser_with_change_applied in enumerate(step):
                # Use default prompt -- will be appended automatically by code_explain_prompt
                prev_msgs = []
                for prev_change, prev_response in zip(applied_changes_nb_states, assistant_msgs):
                    prev_msgs.append({ "role": "user", "content": str(prev_change)})
                    prev_msgs.append(prev_response)

                print('><'*50)
                # print('prompt_msgs')
                # for i, prompt_msg in enumerate(prompt_msgs):
                #     print(i)
                #     pprint_msg(prompt_msg)

                logger.debug(f'NB Step {step_i} Change({change_i}) {step.get_change_type(change_i)} @ {step.cell_id}, Change Definition:')
                print(step.entries[change_i].print())
                print('><'*50)

                while True:
                    try:
                        if args.append_prev_msgs:
                            prompt_msgs = construct_code_explain_prompt(nb_parser_with_change_applied, prev_messages=prev_msgs)
                        else:
                            prompt_msgs = construct_code_explain_prompt(nb_parser_with_change_applied)

                        logger.trace(f'Code Explain Prompt messages:\n{prettify_str(prompt_msgs)}')
                        assistant_msgs.append(prompt(prompt_msgs))
                        break
                    except openai.error.InvalidRequestError as e:
                        if len(prev_msgs) > 0:
                            logger.warning(f'Error, retrying with fewer prev_msgs: {len(prev_msgs)}')
                            prev_msgs = prev_msgs[-1:]
                        else:
                            raise e

                applied_changes_nb_states.append(nb_parser_with_change_applied)


                print(f'NB Step {step_i} Change({change_i}) Response:')
                injected_content_assistant_msg = inject_content(assistant_msgs[-1], step, change_i)
                pprint_msg(injected_content_assistant_msg)

                if len(assistant_msgs) >= 2:
                    generate_questions(applied_changes_nb_states[-2:], assistant_msgs[-2:], prev_generated_questions=generated_questions)

        print(f'Final notebook state:')
        print(nb_parser)
        # print(f'Final log state:')
        # print(nb_log_parser)
        print(f'Final assistant msgs:')
        for assistant_msg in assistant_msgs:
            pprint_msg(assistant_msg)

        # if input('Continue? (y/n)') == 'n':
        #     break
        breakpoint()

        # generate_questions(applied_changes_nb_states, assistant_msgs)

