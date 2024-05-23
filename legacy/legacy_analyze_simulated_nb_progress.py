import os
import sys
import re
from utils import get_all_file_with_extension_in_dir_recursively
from parsers.nb_parser import NotebookParser
from nb_progress import get_notebook_progress_simulate, NotebookParser, InvalidLogError
from utils import (
    get_all_file_with_extension_in_dir_recursively,
    prettify_str,
    logger
)
from legacy.legacy_common import generate_questions, perform_explain_change_on_nb_parser



if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--notebooks_dir', type=str, default='data/tac_notebooks')
    parser.add_argument('--append_prev_msgs', action='store_true', default=False)
    parser.add_argument('--keep_code_header_comments', action='store_true', default=False)
    args = parser.parse_args()

    # set logger to trace to see all logs
    logger.remove()
    logger.add(sys.stderr, level="TRACE")
    import uuid
    logger_id = str(uuid.uuid4())
    logger.add(f'logs/analyze_nb_logs_{logger_id}.log', level="TRACE")
    logger.info(f'Logger ID: {logger_id}')

    verbose = True # TODO
    notebooks_dir = args.notebooks_dir # TODO
    filter=lambda x: re.match(r'[A-Z]-subject-.+.ipynb', x) # TODO
    if verbose: print(f'Filtering notebooks with filter: {filter.__name__}')

    nb_filename_dict = {
        os.path.basename(nb_filepath): nb_filepath
        for nb_filepath in
        get_all_file_with_extension_in_dir_recursively(notebooks_dir, ".ipynb")
        if filter(os.path.basename(nb_filepath))
    }

    print(f'\nThere are total {len(nb_filename_dict)} notebooks found in {notebooks_dir} directory')


    for i, nb_parser in enumerate(map(NotebookParser, nb_filename_dict.values())):
        # try:
        logger.success(f'{i} Processing notebook: {nb_parser.filepath} with {len(nb_parser)} cells.')
        logger.trace(f'{i} nb_parser:\n{nb_parser}')

        try:
            nb_progress = get_notebook_progress_simulate(nb_parser, keep_code_header_comments=args.keep_code_header_comments)
        except InvalidLogError as e:
            logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath})')
            continue

        logger.info(f'Notebook: {nb_parser.filepath}')
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
                        step.nb_parser_state,
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
        # if input('Continue? (y/n)') == 'n':
        #     break
        breakpoint()
