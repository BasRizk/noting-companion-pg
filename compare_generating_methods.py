import os
from loguru import logger
from typing import List
from parsers.nb_parser import NotebookParser
from legacy_analyze_nb_logs import load_object, get_all_file_with_extension_in_dir_recursively, logger, LogParser


notebooks_dir = 'data/tac_notebooks'
logs_dir = 'data/tac_raw_logs'
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

    from nb_progress import get_notebook_progress_using_log, InvalidLogError, NotebookStateLogMismatchError


    for i, (nb_filepath, (nb_log_parser, nb_parser)) in enumerate(nb_sublog_dict.items()):
        try:
            nb_progress = get_notebook_progress_using_log(nb_parser, nb_log_parser)
        except InvalidLogError as e:
            # logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath}) and nb_log_parser({nb_log_parser.filepath})')
            continue
        except NotebookStateLogMismatchError as e:
            # logger.error(f'@ {i} Exception: {e} with nb_filepath({nb_parser.filepath}) and nb_log_parser({nb_log_parser.filepath})')
            continue


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

        num_progress_steps = len(nb_progress)

        if num_progress_steps >= 4:
            # logger.info(f'Notebook: {nb_parser.filepath}')
            # logger.info(f'Log: {nb_log_parser.filepath}')
            # logger.info(f'Number of progress steps: {num_progress_steps}')
            selected_sessions.append((nb_parser, nb_log_parser, nb_progress, nb_states))


def get_qa_pairs(nb_states, consecutive_only=True, method='offline', num_questions=3):
    from prompts.generate_questions_per_changes import make_questions_prompt
    from prompts.answer_questions_per_change import answer_questions
    from prompts.code_explain_change import get_diff_nb_states


    qa_pairs_dict = {}
    for i in range(len(nb_states)):
        for j in range(i+1, len(nb_states)):
            if consecutive_only and j != i + 1:
                continue
            qa_pairs_dict[(i, j)] = None

    for (t1, t2) in qa_pairs_dict.keys():
        cell_diff = get_diff_nb_states(nb_states[t1], nb_states[t2])
        if consecutive_only:
            assert len(cell_diff) == 1, f'Expected 1 cell diff, got {len(cell_diff)}'
        else:
            raise NotImplementedError

        code_before_modification = '\n'.join(cell_diff[0][0].get_json()['source'])
        code_after_modification = '\n'.join(cell_diff[0][1].get_json()['source'])

        if method == 'offline':
            questions = make_questions_prompt(
                nb_states[t1],
                nb_states[t2],
                max_num_questions_per_update=num_questions,
                # changes_exps_dict[(t1, t2)] # TODO try to use this as hints
            )
            answers, _, _ = answer_questions(
                nb_states[t1],
                nb_states[t2],
                questions,
            )
            question_answers = [
                {
                    'question': question,
                    'answer': answer
                }
                for question, answer in zip(questions, answers)
            ]

        elif method == 'online':
            import requests
            # make request to `https://ckg12.isi.edu/knic-services/generate_questions`
            response_json = requests.post('https://ckg12.isi.edu/knic-services/generate_questions', json={
                'code': code_after_modification,
                'num_questions': num_questions
            }).json()['results']
            assert response_json['code'] == code_after_modification, f'Expected code to be the same, got {qa_pairs_dict[(t1, t2)]["code"]}'
            question_answers = [
                {
                    'question': qa['question'],
                    'answer': qa['answer']
                }
                for qa in response_json['question_answers']
            ]
        else:
            raise ValueError(f'Invalid method: {method}')

        qa_pairs_dict[(t1, t2)] = {
            'code': f'> Before Modification\n{code_before_modification}\n\n > After Modification\n{code_after_modification}',
            'question_answers': question_answers
        }

    return qa_pairs_dict



output_dir = 'data/qa_pairs'
os.makedirs(output_dir, exist_ok=True)

for nb_parser, nb_log_parser, nb_progress, nb_states in selected_sessions:
    logger.info(f'Notebook: {nb_parser.filepath}')
    logger.info(f'Log: {nb_log_parser.filepath}')
    logger.info(f'Number of progress steps: {len(nb_progress)}')

    qa_pairs_online = get_qa_pairs(nb_states, consecutive_only=True, method='online')
    qa_pairs_offline = get_qa_pairs(nb_states, consecutive_only=True, method='offline')

    qa_pairs_from_methods = [
        ('offline', qa_pairs_offline),
        ('online', qa_pairs_online),
    ]
    # shuffle the order of methods
    import random
    random.shuffle(qa_pairs_from_methods)
    qa_pairs_method_1_method_name, qa_pairs_method_1 = qa_pairs_from_methods[0]
    qa_pairs_method_2_method_name, qa_pairs_method_2 = qa_pairs_from_methods[1]

    import csv

    # csv_filename including name of the notebook and log file
    csv_filename = f'{output_dir}/qa_pairs_{nb_parser.filepath.replace("/", "_")}_{nb_log_parser.filepath.replace("/", "_")}.xlsx'

    # with open(csv_filename, mode='w') as qa_pairs_file:
    #     qa_pairs_writer = csv.writer(qa_pairs_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
    #     qa_pairs_writer.writerow(['code', 'question_method_1', 'answer_method_1', 'question_method_2', 'answer_method_2'])
    #     for (t1, t2) in qa_pairs_method_1.keys():
    #         max_num_questions = max(len(qa_pairs_method_1[(t1, t2)]['question_answers']), len(qa_pairs_method_2[(t1, t2)]['question_answers']))
    #         for i in range(max_num_questions):
    #             qa_pairs_writer.writerow([
    #                 qa_pairs_method_1[(t1, t2)]['code'] if i == 0 else '',
    #                 qa_pairs_method_1[(t1, t2)]['question_answers'][i]['question'] if i < len(qa_pairs_method_1[(t1, t2)]['question_answers']) else '',
    #                 qa_pairs_method_1[(t1, t2)]['question_answers'][i]['answer'] if i < len(qa_pairs_method_1[(t1, t2)]['question_answers']) else '',
    #                 qa_pairs_method_2[(t1, t2)]['question_answers'][i]['question'] if i < len(qa_pairs_method_2[(t1, t2)]['question_answers']) else '',
    #                 qa_pairs_method_2[(t1, t2)]['question_answers'][i]['answer'] if i < len(qa_pairs_method_2[(t1, t2)]['question_answers']) else '',
    #             ])

    # write excel file with maximum width for each column
    import xlsxwriter
    workbook = xlsxwriter.Workbook(csv_filename)
    worksheet = workbook.add_worksheet()
    width = 45
    worksheet.set_column('A:A', width)
    worksheet.set_column('B:B', width)
    worksheet.set_column('C:C', width)
    worksheet.set_column('D:D', width)
    worksheet.set_column('E:E', width)
    worksheet.write('A1', 'code')
    worksheet.write('B1', f'question_method_1')
    worksheet.write('C1', f'answer_method_1')
    worksheet.write('D1', f'question_method_2')
    worksheet.write('E1', f'answer_method_2')

    # wrap text
    wrap_format = workbook.add_format({'text_wrap': True})

    row = 1
    for (t1, t2) in qa_pairs_method_1.keys():
        max_num_questions = max(len(qa_pairs_method_1[(t1, t2)]['question_answers']), len(qa_pairs_method_2[(t1, t2)]['question_answers']))
        for i in range(max_num_questions):
            worksheet.write(row, 0, qa_pairs_method_1[(t1, t2)]['code'] if i == 0 else '', wrap_format)
            worksheet.write(row, 1, qa_pairs_method_1[(t1, t2)]['question_answers'][i]['question'] if i < len(qa_pairs_method_1[(t1, t2)]['question_answers']) else '', wrap_format)
            worksheet.write(row, 2, qa_pairs_method_1[(t1, t2)]['question_answers'][i]['answer'] if i < len(qa_pairs_method_1[(t1, t2)]['question_answers']) else '', wrap_format)
            worksheet.write(row, 3, qa_pairs_method_2[(t1, t2)]['question_answers'][i]['question'] if i < len(qa_pairs_method_2[(t1, t2)]['question_answers']) else '', wrap_format)
            worksheet.write(row, 4, qa_pairs_method_2[(t1, t2)]['question_answers'][i]['answer'] if i < len(qa_pairs_method_2[(t1, t2)]['question_answers']) else '', wrap_format)
            row += 1
    workbook.close()

    logger.info(f'Wrote to {csv_filename}')

    # write text file including which method correspond to which column
    txt_filename = f'{output_dir}/qa_pairs_{nb_parser.filepath.replace("/", "_")}_{nb_log_parser.filepath.replace("/", "_")}.txt'
    with open(txt_filename, mode='w') as txt_file:
        txt_file.write(f'Column 1: modified_code\n')
        txt_file.write(f'Column 2: question_{qa_pairs_method_1_method_name}\n')
        txt_file.write(f'Column 3: answer_{qa_pairs_method_1_method_name}\n')
        txt_file.write(f'Column 4: question_{qa_pairs_method_2_method_name}\n')
        txt_file.write(f'Column 5: answer_{qa_pairs_method_2_method_name}\n')

    # write notebook first and last states
    first_state = nb_states[0]
    last_state = nb_states[-1]
    qa_states_dir= f'{output_dir}/qa_pairs_{nb_parser.filepath.replace("/", "_")}_{nb_log_parser.filepath.replace("/", "_")}'
    os.makedirs(qa_states_dir, exist_ok=True)
    first_state.to_notebook(directory=qa_states_dir, filepath_postfix='_first_state')
    last_state.to_notebook(directory=qa_states_dir, filepath_postfix='_last_state')
    logger.info(f'Wrote to {qa_states_dir} the method names for each column in the csv file')
