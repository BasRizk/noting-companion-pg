import re
from datetime import datetime
from tabulate import tabulate

# from enum import Enum
# class LogEntryType(Enum):
#     CELL_SELECTED = 'CELL_SELECTED'
#     CELL_EXECUTION_BEGIN = 'CELL_EXECUTION_BEGIN'
#     CELL_EXECUTION_END = 'CELL_EXECUTION_END'
#     TGM_QUESTION_ASKED = 'TGM_QUESTION_ASKED'
#     TASK_WHAT_WHY_TIME = 'TASK_WHAT_WHY_TIME'


class LogEntry:
    def __init__(self, _id, entry_type, subject, user, context, notebook, session_type, timestamp, content=None, cell_type=None):
        self.id = _id
        self.entry_type = entry_type
        self.subject = subject
        self.user = user
        self.context = context
        self.notebook = notebook
        self.session_type = session_type
        self.timestamp = timestamp
        self.timestamp_ms = self.convert_to_ms(timestamp)
        self.content = content
        self.cell_type = cell_type

    def __str__(self):
        return f"{self.entry_type}::{self.subject}::{self.user}::{self.context}::{self.notebook}::{self.timestamp}::{self.content}::{self.cell_type}"

    def __repr__(self):
        return self.__str__()

    def get_formatted_content(self, text_width=100):
        _content = self.content.split("\\n")
        # ensure each line of content is below the width of the table, otherwise split it into multiple lines
        for i, line in enumerate(_content):
            if len(line) > text_width:
                # split line over more than one line
                _content[i] = [line[j:j+text_width] for j in range(0, len(line), text_width)]
        # flatten nested lists only if there are any
        _flattened_content = []
        for line in _content:
            if isinstance(line, list):
                _flattened_content += line
            else:
                _flattened_content.append(line)
        _content = _flattened_content
        return _content

    def tabulate(self, text_width=100, compact=True):
        _ptable = [
            ["Entry ID", self.id],
            ["Entry Type", self.entry_type],
            ["Timestamp (ms)", self.timestamp_ms],
        ]
        if self.content:

            _content = self.get_formatted_content(text_width)
            # add line numbers
            for i, line in enumerate(_content):
                _content[i] = f'{i+1} {line}'

            _ptable.append(["Content", _content[0]])
            for line in _content[1:]:
                _ptable.append(["", line])
            _ptable.append(['# of lines', len(_content)])
            if self.cell_type:
                _ptable.append(["Cell Type", self.cell_type])

        if not compact:
            _ptable += [
                ["Timestamp", self.timestamp],
                ["Subject", self.subject],
                ["User", self.user],
                ["Context", self.context],
                ["Notebook", self.notebook],
                ["Session Type", self.session_type]
            ]

        return tabulate(_ptable, tablefmt="fancy_grid", colalign=("right", "left"), stralign="center", numalign="center")

    def set_content(self, content, cell_type):
        self.content = content
        self.cell_type = cell_type

    def convert_to_ms(self, timestamp):
        # Assuming that timestamps are in the format 'YYYY-MM-DDTHH:MM:SS.xxxxxx'
        try:
            timestamp_datetime = datetime.fromisoformat(timestamp)
            timestamp_ms = int(timestamp_datetime.timestamp() * 1000)
            return timestamp_ms
        except ValueError:
            return None

class LogParser:
    def __init__(self, filepath):
        self.filepath = filepath
        self.parse()

    def __len__(self):
        return len(self.entries)

    def __getitem__(self, idx):
        return self.entries[idx]

    # def print(self, text_width=100, compact=True):
    #     print('='*text_width)
    #     print('filepath:', self.filepath)
    #     print('# of entries:', len(self.entries))
    #     print('Notebooks:', self.get_notebooks())
    #     print('Entry types:', self.get_entry_types())
    #     print('Cell types:', self.get_cell_types())
    #     print('Users:', self.get_users())
    #     print('='*text_width)
    #     for entry in self.entries:
    #         entry.print(text_width=text_width, compact=compact)
    #     print('='*text_width)


    def parse(self):
        self.entries = []
        with open(self.filepath, 'r') as file:
            for entry_id, line in enumerate(file):
                parts = line.strip().split(":::")
                if len(parts) >= 7:
                    entry_type = parts[0]
                    subject = parts[1]
                    user = parts[2]
                    context = parts[3]
                    notebook = parts[4]
                    session_type = parts[5]
                    timestamp = parts[6]
                    entry = LogEntry(entry_id, entry_type, subject, user, context, notebook, session_type, timestamp)
                    content = parts[7] if len(parts) >= 8 else None
                    cell_type = parts[8] if len(parts) >= 9 else None
                    entry.set_content(content, cell_type)

                    self.entries.append(entry)
                else:
                    raise Exception(f"Invalid log entry: {line}")
        return self


    def find_first_entry_by_content(self, content):
        for entry in self.entries:
            if entry.content == content:
                return entry
        return None

    def get_only_entries_with_content(self):
        return [entry for entry in self.entries if entry.content is not None]

    def get_only(self, **kwargs):
        filtered = self.entries
        for key, value in kwargs.items():
            if not isinstance(value, list):
                value = [value]
            filtered = [entry for entry in filtered if getattr(entry, key) in value]
        return filtered

    def get_filtered(self, **kwargs):
        filtered = self.entries
        for key, value in kwargs.items():
            if not isinstance(value, list):
                value = [value]
            filtered = [entry for entry in filtered if getattr(entry, key) not in value]
        return filtered

    def get_entry_types(self):
        return set([entry.entry_type for entry in self.entries])

    def get_cell_types(self):
        return set([entry.cell_type for entry in self.entries if entry.cell_type is not None])

    def get_users(self):
        return set([entry.user for entry in self.entries])

    def get_notebooks(self):
        return set([entry.notebook for entry in self.entries])

    def _keep_only_entries_by_filter(self, **kwargs):
        filtered = self.entries
        for key, value in kwargs.items():
            if not isinstance(value, list):
                value = [value]
            filtered = [entry for entry in filtered if getattr(entry, key) in value]
        self.entries = filtered
        return self

    def divide_per_notebook(self, notebooks_names=None):
        from copy import deepcopy
        if notebooks_names is None:
            notebooks = self.get_notebooks()
        log_parsers = {}
        for notebook in notebooks_names:
            log_parsers[notebook] = deepcopy(self)._keep_only_entries_by_filter(notebook=notebook)
        return log_parsers

    def is_one_notebook_log(self):
        return len(self.get_notebooks()) == 1

    def is_continous_notebook_log(self, verbose=False):
        if not self.is_one_notebook_log():
            return False
        for entry_1, entry_2 in zip(self.entries, self.entries[1:]):
            if entry_2.id - entry_1.id != 1:
                if verbose:
                    print('='*20)
                    print('Non consecutive entries:')
                    print(entry_1.id, entry_2.id)
                    right_after_entry = self.get_only(id=entry_1.id+1)[0]
                    print(right_after_entry.id)
                    right_after_entry.print()
                    left_before_entry = self.get_only(id=entry_2.id-1)[0]
                    print(left_before_entry.id)
                    left_before_entry.print()
                    print('='*20)
                return False
        return True

    def of_continous_logs(self, all_training_notebooks_filepathes=None):
        notebooks = self.get_notebooks()
        if all_training_notebooks_filepathes is not None:
            notebooks = notebooks.intersection(all_training_notebooks_filepathes)

        for notebook in sorted(notebooks):
            content_entries = self.get_only(notebook=notebook)
            for entry_1, entry_2 in zip(content_entries[:-1], content_entries[1:]):
                if entry_2.id - entry_1.id != 1:
                    return False
        return True

    # Verification if the logs include a broken session
    # (meaning opened and closed then opened again after some time)
    def debug_noncontinous_logs(self, all_training_notebooks_filepathes=None):

        notebooks = self.get_notebooks()
        if all_training_notebooks_filepathes is not None:
            notebooks = notebooks.intersection(all_training_notebooks_filepathes)

        for notebook in sorted(notebooks):
            print('='*20)
            print('Notebook:', notebook)
            content_entries = self.get_only(notebook=notebook)
            print(f'Number of entries: {len(content_entries)}')
            broken_session = False
            for entry_1, entry_2 in zip(content_entries[:-1], content_entries[1:]):
                if entry_2.id - entry_1.id != 1:
                    broken_session = True
                    print('='*20)
                    print('Non consecutive entries:')
                    print(entry_1.id, entry_2.id)
                    right_after_entry = self.get_only(id=entry_1.id+1)[0]
                    print(right_after_entry.id)
                    right_after_entry.print()
                    left_before_entry = self.get_only(id=entry_2.id-1)[0]
                    print(left_before_entry.id)
                    left_before_entry.print()
                    print('='*20)
            if not broken_session:
                print('All entries are consecutive')

    def attach_notebooks(self,
        notebooks_dir, verbose=False,
        filter=lambda x: re.match(r'[A-Z]-subject-.+.ipynb', x),
        # filter=lambda x: x.startswith('X-subject')
    ):
        import os
        from utils import get_all_file_with_extension_in_dir_recursively
        from parsers.nb_parser import NotebookParser

        if verbose: print(f'Filtering notebooks with filter: {filter.__name__}')

        nb_filepaths_dict = {
            os.path.basename(nb_filepath): nb_filepath
            for nb_filepath in
            get_all_file_with_extension_in_dir_recursively(notebooks_dir, ".ipynb")
            if filter(os.path.basename(nb_filepath))
        }
        print(f'\nThere are total {len(nb_filepaths_dict)} notebooks found in {notebooks_dir} directory')

        linked_notebooks = self.get_notebooks()
        found_related_notebooks = sorted(list(linked_notebooks.intersection(nb_filepaths_dict.keys())))
        if verbose:
            print('Found Related notebooks:')
            for i, nb_filepath in enumerate(found_related_notebooks):
                print(f"{i} {nb_filepath}")

        log_parser_per_notebook = self.divide_per_notebook(found_related_notebooks)

        log_parser_per_notebook = {
            nb_filepaths_dict[nb_filename]: (log_parser, NotebookParser(nb_filepaths_dict[nb_filename]))
            for nb_filename, log_parser in log_parser_per_notebook.items()
        }

        num_notebooks = len(log_parser_per_notebook)
        print(f'There are {num_notebooks} notebooks with logs')

        # filter only continous logs (i.e. logs sections on the same notebook)
        # log_parser_per_notebook = {
        #     nb_filepath: parser
        #     for nb_filepath, parser in log_parser_per_notebook.items()
        #     if parser.is_continous_notebook_log()
        # }
        # print(f'There are {len(log_parser_per_notebook)} out of {num_notebooks} notebooks with continous logs')
        # if verbose:
        #     print('Dropped non continous notebooks:')
        #     for nb_filepath in set(found_related_notebooks) - set(log_parser_per_notebook.keys()):
        #         print(nb_filepath)


        for i, (nb_filepath, (nb_log_parser, nb_parser)) in enumerate(log_parser_per_notebook.items()):
            assert nb_filepath == nb_parser.filepath and nb_filepath != nb_log_parser.filepath

        return log_parser_per_notebook
