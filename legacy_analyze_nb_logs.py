import os
import sys
from parsers.log_parser import LogParser
from nb_progress import get_notebook_progress_using_log, InvalidLogError
from utils import (
    get_all_file_with_extension_in_dir_recursively,
    prettify_str,
    logger
)
from common import generate_questions, perform_explain_change_on_nb_parser

CACHE_DIR = 'data/tac_cache'
os.makedirs(CACHE_DIR, exist_ok=True)

def load_object(object_name, object_nb_filepath, object_log_filepath):
    import pickle
    object_nb_filename = os.path.basename(object_nb_filepath)
    object_log_filename = os.path.basename(object_log_filepath)
    with open(f'{CACHE_DIR}/{object_name}_{object_nb_filename}_{object_log_filename}.pkl', 'rb') as f:
        return pickle.load(f)

def analyze_nb_given_log(nb_log_parser, nb_parser):
    logger.success(f'{i} Processing notebook: {nb_parser.filepath} with {len(nb_parser)} cells, using {nb_log_parser.filepath} log')
    logger.trace(f'{i} nb_parser:\n{nb_parser}')

    try:
        nb_progress = get_notebook_progress_using_log(nb_parser, nb_log_parser)
    except InvalidLogError as e:
        logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath}) and nb_log_parser({nb_log_parser.filepath})')
        return

    # nb_parser_filename = os.path.basename(nb_parser.filepath)
    # nb_log_parser_filename = os.path.basename(nb_log_parser.filepath)

    logger.info(f'Notebook: {nb_parser.filepath}')
    logger.info(f'Log: {nb_log_parser.filepath}')
    logger.info(f'Number of progress steps: {len(nb_progress)}')
    logger.info(f'Number of progress steps unrolled: {sum([len(step) for step in nb_progress])}')

    explanations = []
    prev_applied_changes_nb_states = []
    generated_questions = []
    for step_i, step in enumerate(nb_progress):
        step.reset()
        if len(step) == 0:
            explanations.append(
                perform_explain_change_on_nb_parser(
                    # nb_parser,
                    step.nb_parser_state, # TODO VALIDATE
                    step,
                    step_i,
                    prev_applied_changes_nb_states,
                    explanations,
                    append_prev_msgs=args.append_prev_msgs
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
                        prev_applied_changes_nb_states,
                        explanations,
                        change_i=change_i,
                        append_prev_msgs=args.append_prev_msgs
                    )
                )

        if len(explanations) >= 2:
            _questions = generate_questions(
                prev_applied_changes_nb_states[-2:], explanations[-2:],
                prev_generated_questions=generated_questions
            )
            assert len(_questions) == 1, f'Expected 1 question, got {_questions}'
            generated_questions.append(_questions[0])

    ######################################
    # ======== For Debugging =============
    pickle_object('nb_states', prev_applied_changes_nb_states, nb_parser.filepath, nb_log_parser.filepath)
    pickle_object('explanations', explanations, nb_parser.filepath, nb_log_parser.filepath)
    pickle_object('generated_questions', generated_questions, nb_parser.filepath, nb_log_parser.filepath)
    ######################################

    # TODO print differences rather than just the change
    changes_definitions = []
    for step in nb_progress:
        for change_i in range(len(step.entries)):
            entry_table = step.entries[change_i].tabulate()
            changes_definitions.append(entry_table)

    logger.success(f'All steps completed for {nb_parser.filepath} with {len(nb_progress)} steps getting {len(generated_questions)} sets of questions')
    for change_i, (change_questions, change_definition) in enumerate(zip(generated_questions, changes_definitions)):
        logger.success(
            f'@ Change {change_i}:\n {change_definition}\n Questions: \n{prettify_str(change_questions)}'
        )

    breakpoint()




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
    nb_sublog_dict = log_parser.attach_notebooks(args.notebooks_dir, verbose=False)
    logger.info(
        'Sample:' +\
        f'\nSelected log file: {selected_log_filepath}' +\
        f'\nfetching notebooks from log file: {args.notebooks_dir}' +\
        f'\nLog parser per these notebooks:\n{nb_sublog_dict.keys()}'
    )


    for i, (nb_filepath, (nb_log_parser, nb_parser)) in enumerate(nb_sublog_dict.items()):
        # try:
        assert nb_filepath == nb_parser.filepath
        analyze_nb_given_log(nb_log_parser, nb_parser)

        # if input('Continue? (y/n)') == 'n':
        #     break

